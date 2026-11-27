import os, json, sqlite3, time, hmac, logging, re, urllib.request, urllib.error
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import contextmanager
from bershka_probe import probe, identity, canonical
from monitor import Engine, reset, money, MIN_INTERVAL

VERSION = '0.10'
from adapters import supported_stores
LOG = logging.getLogger('shopping')
MENU = [[{'text':'Ürün ekle','callback_data':'add'},{'text':'Takip listesi','callback_data':'list:0'}],[{'text':'Bildirimler','callback_data':'events'},{'text':'Ayarlar','callback_data':'settings'}]]
COLORS=['Siyah','Beyaz','Ekru','Bordo','Kahverengi','Gri','Bej','Mavi','Tek renk']
SIZES=['XS','S','M','L','XL','XXL','32','34','36','38','40','42','Tek beden']
STORES = {'bershka.com':'Bershka','zara.com':'Zara','stradivarius.com':'Stradivarius','pullandbear.com':'Pull&Bear','trendyol.com':'Trendyol','ty.gl':'Trendyol (kısa link)','mango.com':'Mango','hm.com':'H&M','oysho.com':'Oysho','massimodutti.com':'Massimo Dutti','boyner.com.tr':'Boyner','mavi.com':'Mavi','hepsiburada.com':'Hepsiburada','amazon.com.tr':'Amazon','amzn.eu':'Amazon (kısa link)','gratis.com':'Gratis','watsons.com.tr':'Watsons','sephora.com.tr':'Sephora'}

def load_env():
    path=Path('.env')
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k,v=line.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))

def product_url(raw):
    raw=raw.strip()
    matches=re.findall(r'https://[^\s<>]+',raw)
    if len(matches)==1 and not raw.startswith('https://') and raw.endswith(matches[0]): raw=matches[0]
    if len(raw)>1800 or any(c.isspace() for c in raw): raise ValueError('Yalnızca ürün paylaşım bağlantısını gönder.')
    try:
        u=urlsplit(raw); host=(u.hostname or '').lower(); port=u.port
    except ValueError: raise ValueError('Geçersiz bağlantı.') from None
    if u.scheme!='https' or not host or '.' not in host or u.username or u.password or port not in (None,443): raise ValueError('https:// ile başlayan bir ürün linki gönder.')
    store=next((name for domain,name in STORES.items() if host==domain or host.endswith('.'+domain)), 'Diğer mağaza')
    url=u._replace(fragment='').geturl()
    if store=='Bershka':
        try: url=canonical(url)
        except ValueError: pass
    return url,store

def fallback_name(url,store):
    # Identifier, not a claim about the product title.
    if store=='Bershka':
        try: return 'Ürün '+identity(url)[0]
        except ValueError: pass
    import hashlib
    return 'Ürün '+hashlib.sha256(url.encode()).hexdigest()[:8].upper()

def clean(s,limit=120):
    s=' '.join(s.split())
    if not s or len(s)>limit: raise ValueError(f'1–{limit} karakter arası bilgi gir.')
    return s

def button(text,data): return {'text':text,'callback_data':data}
def keyboard(*rows): return {'inline_keyboard':list(rows)}
def home(): return [button('Ana menü','home')]
def split_values(s):
    s=clean(s,180)
    return ', '.join(dict.fromkeys(x.strip() for x in s.split(',') if x.strip())) or 'Belirtilmedi'

class DB:
    def __init__(self,path):
        self.c=sqlite3.connect(path); self.c.row_factory=sqlite3.Row
        self.c.execute('PRAGMA foreign_keys=ON'); self.c.execute('PRAGMA journal_mode=WAL')
        self.c.executescript('''CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,url TEXT NOT NULL,store TEXT NOT NULL,name TEXT NOT NULL,color TEXT NOT NULL,size TEXT NOT NULL,stock INTEGER NOT NULL DEFAULT 1,price INTEGER NOT NULL DEFAULT 1,paused INTEGER NOT NULL DEFAULT 0,created INTEGER NOT NULL, UNIQUE(url,color,size));
        CREATE TABLE IF NOT EXISTS drafts(owner INTEGER PRIMARY KEY,step TEXT NOT NULL,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,body TEXT NOT NULL,created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS prices(id INTEGER PRIMARY KEY AUTOINCREMENT,product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,variant_key TEXT NOT NULL,amount_minor INTEGER NOT NULL,currency TEXT NOT NULL,observed INTEGER NOT NULL);'''); self.c.commit()
    def get(self,k,default=None):
        r=self.c.execute('SELECT v FROM settings WHERE k=?',(k,)).fetchone(); return r[0] if r else default
    def put(self,k,v):
        with self.c: self.c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v',(k,str(v)))
    def draft(self,owner,step=None,data=None):
        if step is None:
            r=self.c.execute('SELECT * FROM drafts WHERE owner=?',(owner,)).fetchone(); return (r['step'],json.loads(r['data'])) if r else (None,{})
        with self.c: self.c.execute('INSERT INTO drafts VALUES(?,?,?) ON CONFLICT(owner) DO UPDATE SET step=excluded.step,data=excluded.data',(owner,step,json.dumps(data,ensure_ascii=False)))
    def clear(self,owner):
        with self.c: self.c.execute('DELETE FROM drafts WHERE owner=?',(owner,))
    def add(self,d):
        with self.c:
            cur=self.c.execute('INSERT INTO products(url,store,name,color,size,created) VALUES(?,?,?,?,?,?)',(*(d[k] for k in ('url','store','name','color','size')),int(time.time())))
        return cur.lastrowid
    def product(self,i): return self.c.execute('SELECT * FROM products WHERE id=?',(i,)).fetchone()
    def list(self,page,store=None):
        where=' WHERE store=?' if store else ''; args=(store,) if store else ()
        return self.c.execute('SELECT * FROM products'+where+' ORDER BY id DESC LIMIT 8 OFFSET ?',args+(max(0,page)*8,)).fetchall()
    def count(self,store=None):
        return self.c.execute('SELECT COUNT(*) FROM products WHERE store=?',(store,)).fetchone()[0] if store else self.c.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    def update(self,i,field,value):
        if field not in ('name','color','size','stock','price','paused'): raise ValueError('Geçersiz alan')
        with self.c: self.c.execute(f'UPDATE products SET {field}=? WHERE id=?',(value,i))
    def delete(self,i):
        with self.c: self.c.execute('DELETE FROM products WHERE id=?',(i,))
    def event(self,body):
        with self.c: self.c.execute('INSERT INTO events(body,created) VALUES(?,?)',(body,int(time.time())))
    def events(self): return self.c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 10').fetchall()

class TelegramError(RuntimeError):
    def __init__(self,code,description,method='unknown'):
        super().__init__(f'Telegram HTTP {code}'); self.code=code; self.description=description.lower(); self.method=method
    def diagnostic(self):
        reasons={401:'token yetkilendirmesi başarısız',403:'erişim engellendi',409:'başka bot süreci veya webhook çakışması',429:'istek sınırı'}
        reason=reasons.get(self.code,'API isteği başarısız')
        for fragment in ('message is not modified','message to edit not found',"message can't be edited",'chat not found','message identifier is not specified','query is too old','terminated by other getupdates request','webhook is active','bot was blocked'):
            if fragment in self.description: reason=fragment; break
        return f'{self.method}: HTTP {self.code} ({reason})'

class Telegram:
    def __init__(self,token): self.token=token
    def call(self,method,**args):
        req=urllib.request.Request('https://api.telegram.org/bot'+self.token+'/'+method,data=json.dumps(args).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=40) as r: obj=json.load(r)
        except urllib.error.HTTPError as e:
            try: detail=json.loads(e.read()); retry=detail.get('parameters',{}).get('retry_after',0)
            except Exception: retry=0; detail={}
            if retry: time.sleep(min(int(retry),120))
            raise TelegramError(e.code, str(detail.get('description','')) if isinstance(detail,dict) else '', method) from None
        except (OSError,ValueError) as e: raise RuntimeError(f'{method}: bağlantı/veri hatası ({type(e).__name__})') from None
        if not obj.get('ok'): raise TelegramError(obj.get('error_code',0),str(obj.get('description','')),method)
        return obj['result']
    def payload(self,chat,text,markup=None):
        heading, sep, body = text.partition('\n')
        formatted = '<b>'+escape(heading)+'</b>'+sep+escape(body)
        return dict(chat_id=chat,text=formatted,parse_mode='HTML',reply_markup=markup or keyboard(home()),link_preview_options={'is_disabled':True})
    def send(self,chat,text,markup=None):
        return self.call('sendMessage',**self.payload(chat,text,markup))
    def render(self,chat,text,markup=None,message_id=None):
        if message_id:
            try:
                self.call('editMessageText',message_id=message_id,**self.payload(chat,text,markup))
                return message_id
            except TelegramError as e:
                if e.code==400 and 'message is not modified' in e.description: return message_id
                if e.code!=400 or not any(x in e.description for x in ('message to edit not found',"message can't be edited",'message identifier is not specified')): raise
        result=self.send(chat,text,markup)
        return result['message_id']

class Bot:
    def __init__(self,db,tg,code): self.db=db;self.tg=tg;self.code=code;self.engine=Engine(db)
    def render(self,chat,text,markup=None):
        if str(chat)!=self.db.get('owner'): return self.tg.send(chat,text,markup)
        key='screen_message'; old=self.db.get(key)
        mid=self.tg.render(chat,text,markup,int(old) if old else None)
        self.db.put(key,mid)
    def fresh_screen(self,chat):
        # A text reply puts the old inline menu above the user's message.
        # Retire only the bot's old UI, never the user's messages or alerts.
        old=self.db.get('screen_message')
        if old:
            try: self.tg.call('deleteMessage',chat_id=chat,message_id=int(old))
            except RuntimeError:
                try: self.tg.call('editMessageReplyMarkup',chat_id=chat,message_id=int(old),reply_markup={'inline_keyboard':[]})
                except RuntimeError: pass
        self.db.put('screen_message','')
    def menu(self,chat,notice=None):
        total=self.db.count()
        summary=f'{total} ürün' if total else 'Takip listen boş.'
        self.render(chat,f'avail\n\n'+((notice+'\n\n') if notice else '')+summary,{'inline_keyboard':MENU})
    def listing(self,chat,page):
        store=self.db.get('list_store','')
        if store not in supported_stores(self.db): store=''; self.db.put('list_store','')
        total=self.db.count(store); page=max(0,min(page,max(0,(total-1)//8))); rows=self.db.list(page,store)
        keys=[[button('Mağaza: '+(store or 'Tümü'),'filters')]]
        keys.extend([[button(f"{p['name'][:42] if store else p['store']+' / '+p['name'][:35]}{' (duraklatıldı)' if p['paused'] else ''}",f"p:{p['id']}")] for p in rows])
        nav=[]
        if page: nav.append(button('‹ Önceki',f'list:{page-1}'))
        if (page+1)*8<total: nav.append(button('Sonraki ›',f'list:{page+1}'))
        if nav: keys.append(nav)
        keys.extend([[button('Ürün ekle','add')],home()]);self.render(chat,f'Takip listesi · {total} ürün' + (f'\n{page+1} / {(total+7)//8}' if total>8 else ('\n\nHenüz ürün yok.' if not total else '')),keyboard(*keys))
    def filters(self,chat):
        current=self.db.get('list_store',''); names=supported_stores(self.db)
        keys=[[button(('✓ ' if not current else '')+'Tümü','filter:all')]]
        keys.extend([[button(('✓ ' if name==current else '')+name,f'filter:{name}')] for name in names])
        keys.append([button('Geri','list:0')]); self.render(chat,'Mağaza seç',keyboard(*keys))
    def stores(self,chat):
        names=supported_stores(self.db)
        return self.render(chat,'Desteklenen mağazalar\n\n'+('\n'.join(names) if names else 'Henüz etkin mağaza yok.'),keyboard([button('Geri','settings')],home()))
    def detail(self,chat,i):
        p=self.db.product(i)
        if not p: return self.listing(chat,0)
        state=self.db.c.execute('SELECT * FROM check_state WHERE product_id=?',(i,)).fetchone()
        variants=self.db.c.execute('SELECT * FROM variant_state WHERE product_id=? ORDER BY variant_key',(i,)).fetchall()
        status='Duraklatıldı' if p['paused'] else state['status'] if state else 'Stok bilinmiyor · Takip etkin değil'
        lines=[]
        if (not state or state['status']=='Veri alındı') and variants:
            for v in variants:
                label={'in':'Stokta','out':'Stokta yok'}.get(v['stock_state'],'Stok bilinmiyor')
                lines.append(f"{v['variant_key']} — {label}"+(f" · {money(v['amount'])}" if v['amount'] is not None else ''))
        text=f"{p['name']}\n{p['store'].upper()}\n{p['color']} / {p['size']}\n\n{status}"+('\n'+ '\n'.join(lines[:20]) if lines else '')
        if state: text+='\nSon kontrol: '+time.strftime('%d.%m %H:%M',time.gmtime(state['checked']+10800))
        if p['store'] not in supported_stores(self.db) and not p['paused']: text+='\nCanlı takip henüz desteklenmiyor.'
        elif (self.db.get('monitor_enabled')!='1' or self.engine.source.pilot.selected()) and not p['paused']: text+='\nOtomatik takip kapalı.'
        elif state and not p['paused'] and p['store']=='Bershka': text+='\nSonraki kontrol en erken: '+time.strftime('%d.%m %H:%M',time.gmtime(max(state['next_due'],int(self.db.get('next_store_request','0')),int(self.db.get('store_pause_until','0')))+10800))
        if p['store']=='Bershka':
            checkrow=[button('Kontrol et',f'check:{i}')]
        else: checkrow=[button('Mağaza desteği','stores')]
        self.render(chat,text,keyboard([{'text':'Ürünü aç','url':p['url']}],checkrow,[button('Düzenle',f'edit:{i}'),button('Fiyat geçmişi',f'hist:{i}')],[button('Başlat' if p['paused'] else 'Duraklat',f'toggle:{i}:paused'),button('Sil',f'del:{i}')],[button('Takip listesi','list:0')],home()))
    def edit(self,chat,i):
        p=self.db.product(i)
        if not p: return self.listing(chat,0)
        self.render(chat,'Takip ayarları',keyboard([button('Ürün adı',f'field:{i}:name')],[button('Renk',f'field:{i}:color'),button('Beden',f'field:{i}:size')],[button('Stok: '+('Açık' if p['stock'] else 'Kapalı'),f'toggle:{i}:stock')],[button('Fiyat: '+('Açık' if p['price'] else 'Kapalı'),f'toggle:{i}:price')],[button('Geri',f'p:{i}')],home()))
    def options(self,chat,user,step,d):
        choices=d.get('choices_'+step) or []
        picked=d.get('picked',[])
        def label_for(x):
            prefix='✓ ' if x in picked else ''
            if step=='size' and d.get('source_rows'):
                from monitor import norm
                rows=[r for r in d['source_rows'] if norm(r['color'])==norm(d.get('color','')) and r['size']==x]
                states={r['status'] for r in rows}
                if states=={'out'}: return prefix+x+' · Tükendi'
                if states=={'in'}: return prefix+x+' · Stokta'
            return prefix+x
        width=2 if step=='size' and d.get('source_rows') else 3
        keys=[[button(label_for(x),f'pick:{step}:{j}') for j,x in enumerate(choices[k:k+width],k)] for k in range(0,len(choices),width)]
        keys.append([button('Kaydet' if 'edit_id' in d or step=='size' else 'Devam','pickdone:'+step)])
        keys.append([button('Vazgeç','home')])
        label='Seç.' if choices else 'Mağaza seçenekleri doğrulanamadı. İstersen elle yaz.'
        context=(d.get('name','')+'\n'+(d.get('color','')+'\n' if step=='size' and d.get('color') else '')+'\n') if d.get('name') else ''
        self.render(chat,('Renk' if step=='color' else 'Beden')+'\n\n'+context+label+('\nSeçilen: '+', '.join(picked) if picked else ''),keyboard(*keys))
    def finish_pick(self,chat,user,step,d,value):
        if 'edit_id' in d:
            try:
                self.db.update(d['edit_id'],step,value); reset(self.db,d['edit_id'])
            except sqlite3.IntegrityError:
                return self.render(chat,'Bu ürün zaten kayıtlı.',keyboard([button('Geri',f"p:{d['edit_id']}")],home()))
            self.db.clear(user);return self.detail(chat,d['edit_id'])
        choices=d.get('choices_'+step)
        if step=='color' and d.get('source_rows') and len(value.split(','))!=1: return self.options(chat,user,step,d)
        if choices and any(x.strip() not in choices for x in value.split(',')):
            return self.options(chat,user,step,d)
        if step=='color':
            d['color']=value; d.pop('picked',None)
            if d.get('source_rows'):
                from monitor import norm
                selected={norm(x) for x in value.split(',')}
                matched=[r for r in d['source_rows'] if norm(r['color']) in selected]
                links={r['url'] for r in matched}
