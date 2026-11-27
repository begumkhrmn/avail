"""Conservative structured-data adapter and durable notification engine.
No browser, hidden APIs, bypasses or guessing missing variant availability.
"""
from decimal import Decimal, InvalidOperation
from adapters import supported_stores
from provider import ApifyPilot
from urllib.parse import urlsplit
import urllib.request, urllib.error, urllib.robotparser, time, re, json
from bershka_probe import Page, nodes, identity, canonical, SafeRedirect, analyze

UA='avail-personal-stock/0.7'
MAX_BYTES=1_000_000
MIN_INTERVAL=60
DAILY_BYTES=80_000_000

def norm(s): return ' '.join(str(s).replace('İ','i').replace('I','ı').casefold().split())
def types(obj):
    t=obj.get('@type',[]); return [t] if isinstance(t,str) else t if isinstance(t,list) else []
def amount(o):
    if o.get('priceCurrency')!='TRY': return None
    try:
        n=Decimal(str(o.get('price')))*100
        if not n.is_finite() or not 0<n<=100_000_000 or n!=n.to_integral_value(): return None
        return int(n)
    except (InvalidOperation, ValueError): return None

def extract(html,url,discover=False):
    if analyze(html)['challenge_hint']: return []
    p=Page();p.feed(html); out={}; conflicts=set(); target=identity(url)
    if target[1] is None and not discover: return []
    for root in p.ld:
        for n in nodes(root):
            if 'Product' not in types(n): continue
            color=n.get('color'); size=n.get('size'); name=n.get('name')
            # A missing size is NOT proof of one-size status.
            if not all(isinstance(x,str) and 0<len(x)<=160 for x in (color,size,name)): continue
            offers=n.get('offers'); offers=offers if isinstance(offers,list) else [offers]
            for o in offers:
                if not isinstance(o,dict) or 'Offer' not in types(o): continue
                link=o.get('url') or n.get('url')
                if not isinstance(link,str): continue
                try:
                    candidate=identity(link)
                    if candidate[1] is None or (candidate[0]!=target[0] if discover else candidate!=target): continue
                except (ValueError,TypeError): continue
                av=o.get('availability')
                statuses={'https://schema.org/InStock':'in','http://schema.org/InStock':'in','https://schema.org/OutOfStock':'out','http://schema.org/OutOfStock':'out','https://schema.org/SoldOut':'out','http://schema.org/SoldOut':'out'}
                status=statuses.get(av) if isinstance(av,str) else None
                price=amount(o)
                if status is None and price is None: continue
                k=(candidate[1],norm(color),norm(size))
                row={'name':name,'color':color,'size':size,'status':status,'price':price,'url':canonical(link),'color_id':candidate[1]}
                if k in out and (out[k]['price'],out[k]['status'])!=(price,status): conflicts.add(k)
                out[k]=row
    return [v for k,v in out.items() if k not in conflicts]

class Source:
    def __init__(self,db): self.db=db; self.robots=None;self.robots_until=0;self.pilot=ApifyPilot(db)
    def charge(self,n):
        day=time.strftime('%Y-%m-%d',time.gmtime()); key='traffic:'+day
        self.db.put(key,int(self.db.get(key,'0'))+n)
    def fetch(self,url,robots=False):
        day=time.strftime('%Y-%m-%d',time.gmtime())
        if int(self.db.get('traffic:'+day,'0'))+MAX_BYTES>DAILY_BYTES: raise ValueError('Günlük kontrol kotası doldu.')
        # No redirect for robots; product redirects must preserve exact identity.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a,**k): return None
        opener=urllib.request.build_opener(NoRedirect() if robots else SafeRedirect())
        req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/plain' if robots else 'text/html','Accept-Encoding':'identity','Cache-Control':'no-cache'})
        with opener.open(req,timeout=8) as r:
            if not robots and identity(r.url)!=identity(url): raise ValueError('Ürün kimliği değişti.')
            if r.headers.get('Content-Encoding','identity')!='identity': raise ValueError('İçerik kodlaması desteklenmiyor.')
            if not robots and r.headers.get_content_type()!='text/html': raise ValueError('Beklenmeyen içerik.')
            data=r.read(MAX_BYTES+1); self.charge(len(data))
            if len(data)>MAX_BYTES: raise ValueError('Sayfa boyutu sınırı aşıldı.')
            return data.decode(r.headers.get_content_charset() or 'utf-8',errors='replace')
    def check(self,url,discover=False):
        url=canonical(url)
        if self.pilot.selected(): return self.pilot.check(url,discover)
        # The direct HTML route has already returned 403 in the actual deployment.
        # No implicit fallback or automated reattempt without a verified source.
        if __import__('os').environ.get('AVAIL_DATA_SOURCE')!='html' or 'Bershka' not in supported_stores(self.db):
            raise ValueError('Doğrulanmış veri kaynağı etkin değil.')
        if time.time()>self.robots_until:
            raw=self.fetch('https://www.bershka.com/robots.txt',True)
            if 'user-agent:' not in raw.lower(): raise ValueError('Erişim kuralları doğrulanamadı.')
            self.robots=urllib.robotparser.RobotFileParser();self.robots.parse(raw.splitlines());self.robots_until=time.time()+3600
        if not self.robots.can_fetch(UA,url): raise ValueError('Mağaza erişim kuralları izin vermiyor.')
        # Respect any more restrictive published delay/request rate.
        delay=self.robots.crawl_delay(UA) or 0
        rate=self.robots.request_rate(UA)
        if rate and rate.requests>0: delay=max(delay,(rate.seconds+rate.requests-1)//rate.requests)
        if delay>MIN_INTERVAL:
            self.db.put('next_store_request',max(int(self.db.get('next_store_request','0')),int(time.time())+delay))
        return extract(self.fetch(url),url,discover=discover)
    def discover(self,url): return self.check(url,discover=True)

def install(db):
    db.c.executescript('''CREATE TABLE IF NOT EXISTS variant_state(product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,variant_key TEXT,stock_state TEXT,amount INTEGER,observed INTEGER,PRIMARY KEY(product_id,variant_key));
    CREATE TABLE IF NOT EXISTS check_state(product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,checked INTEGER NOT NULL,next_due INTEGER NOT NULL,status TEXT NOT NULL,failures INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS confirmed_state(product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,variant_key TEXT,stock_state TEXT,amount INTEGER,PRIMARY KEY(product_id,variant_key));
    CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,body TEXT NOT NULL,url TEXT NOT NULL,created INTEGER NOT NULL);''');
    # Migrate known prior observations without overwriting durable references.
    db.c.execute('INSERT OR IGNORE INTO confirmed_state SELECT product_id,variant_key,stock_state,amount FROM variant_state WHERE stock_state IS NOT NULL OR amount IS NOT NULL'); db.c.commit()

def reset(db,i):
    with db.c:
        for tab in ('variant_state','confirmed_state','check_state','prices','outbox'):
            db.c.execute(f'DELETE FROM {tab} WHERE product_id=?',(i,))

def money(x): return f'{x/100:,.2f}'.replace(',','_').replace('.',',').replace('_','.')+' TL'
def matches(p,r):
    return norm(r['color']) in {norm(x) for x in p['color'].split(',')} and norm(r['size']) in {norm(x) for x in p['size'].split(',')}

def record(db,p,rows,now):
    """First observation is baseline, unknown is never interpreted as out-of-stock."""
    valid=[r for r in rows if matches(p,r)]
    if not valid: return False
    with db.c:
        names={r['name'] for r in valid if isinstance(r.get('name'),str) and 0<len(r['name'])<=160}
        name=p['name']
        if re.fullmatch(r'Ürün (?:[0-9]+|[A-F0-9]{8})',name) and len(names)==1:
            name=next(iter(names)); db.c.execute('UPDATE products SET name=? WHERE id=?',(name,p['id']))
        seen={norm(r['color'])+' / '+norm(r['size']) for r in valid}
        for old in db.c.execute('SELECT variant_key FROM variant_state WHERE product_id=?',(p['id'],)).fetchall():
            if old['variant_key'] not in seen: db.c.execute('UPDATE variant_state SET stock_state=NULL,amount=NULL WHERE product_id=? AND variant_key=?',(p['id'],old['variant_key']))
        for r in valid:
            k=norm(r['color'])+' / '+norm(r['size']); i=p['id']; stock=r['status']; price=r['price']
            old=db.c.execute('SELECT * FROM confirmed_state WHERE product_id=? AND variant_key=?',(i,k)).fetchone()
            def event(head,detail):
                body=f"{head}\n{name}\n{r['color']} / {r['size']}\n{detail}"
                db.c.execute('INSERT INTO outbox(product_id,body,url,created) VALUES(?,?,?,?)',(i,body,p['url'],now))
                db.c.execute('INSERT INTO events(body,created) VALUES(?,?)',(body,now))
            if old and old['stock_state']=='out' and stock=='in' and p['stock']: event('Stokta',money(price) if price else '')
            if old and price is not None and old['amount'] is not None and price<old['amount'] and p['price']: event('Fiyat düştü',money(old['amount'])+' → '+money(price))
            if price is not None and (not old or old['amount']!=price): db.c.execute('INSERT INTO prices(product_id,variant_key,amount_minor,currency,observed) VALUES(?,?,?,?,?)',(i,k,price,'TRY',now))
            # Keep last confirmed values separately for comparison; current values remain unknown on failure.
            db.c.execute('INSERT INTO confirmed_state VALUES(?,?,?,?) ON CONFLICT(product_id,variant_key) DO UPDATE SET stock_state=coalesce(excluded.stock_state,confirmed_state.stock_state),amount=coalesce(excluded.amount,confirmed_state.amount)',(i,k,stock,price))
            db.c.execute('INSERT INTO variant_state VALUES(?,?,?,?,?) ON CONFLICT(product_id,variant_key) DO UPDATE SET stock_state=excluded.stock_state,amount=excluded.amount,observed=excluded.observed',(i,k,stock,price,now))
    return True

class Engine:
    def __init__(self,db): self.db=db; install(db);self.source=Source(db)
    def check_one(self,p,now=None,rows=None):
        now=int(time.time()) if now is None else now; i=p['id']; old=self.db.c.execute('SELECT * FROM check_state WHERE product_id=?',(i,)).fetchone();fail=0;delay=MIN_INTERVAL;status='Doğrulanamadı'
        try:
            if isinstance(rows,Exception): raise rows
            if rows is None: rows=self.source.check(p['url'])
            ok=record(self.db,p,rows,now)
            if ok: status='Veri alındı'
            else: delay=900;fail=(old['failures'] if old else 0)+1
        except (OSError,ValueError,LookupError,RecursionError) as e:
            fail=(old['failures'] if old else 0)+1; delay=min(3600,300*2**min(fail,4));status='Bağlantı yok'
            if isinstance(e,urllib.error.HTTPError) and e.code in (401,403,429):
                delay=3600; self.db.put('store_pause_until',now+delay);status='Mağaza erişimi sınırladı'
        if status!='Veri alındı':
            with self.db.c: self.db.c.execute('UPDATE variant_state SET stock_state=NULL,amount=NULL WHERE product_id=?',(i,))
        with self.db.c: self.db.c.execute('INSERT INTO check_state VALUES(?,?,?,?,?) ON CONFLICT(product_id) DO UPDATE SET checked=excluded.checked,next_due=excluded.next_due,status=excluded.status,failures=excluded.failures',(i,now,now+delay,status,fail))
        return status
    def tick(self):
        if self.db.get('monitor_enabled')!='1' or 'Bershka' not in supported_stores(self.db) or self.source.pilot.selected(): return
        now=int(time.time())
        if now<int(self.db.get('store_pause_until','0')) or now<int(self.db.get('next_store_request','0')): return
        p=self.db.c.execute("SELECT p.* FROM products p LEFT JOIN check_state c ON c.product_id=p.id WHERE p.store='Bershka' AND p.paused=0 AND (p.stock=1 OR p.price=1) AND coalesce(c.next_due,0)<=? ORDER BY coalesce(c.next_due,0),p.id LIMIT 1",(now,)).fetchone()
        if p:
            self.db.put('next_store_request',now+MIN_INTERVAL)
            # One page response is sufficient for all selected sizes of this URL.
            try: rows=self.source.check(p['url'])
            except (OSError,ValueError,LookupError,RecursionError) as e:
                # Reuse the error without making another network request.
                self.check_one(p,now,rows=e); return
            siblings=self.db.c.execute("SELECT * FROM products WHERE store=? AND url=? AND paused=0 AND (stock=1 OR price=1)",(p['store'],p['url'])).fetchall()
            for sibling in siblings: self.check_one(sibling,now,rows=rows)
    def deliver(self,tg):
        owner=self.db.get('owner')
        if not owner or self.db.get('monitor_enabled')!='1' or 'Bershka' not in supported_stores(self.db): return
        r=self.db.c.execute("SELECT o.* FROM outbox o JOIN products p ON p.id=o.product_id WHERE p.paused=0 AND p.store='Bershka' ORDER BY o.id LIMIT 1").fetchone()
        if not r: return
        tg.send(int(owner),r['body'],{'inline_keyboard':[[{'text':'Ürünü aç','url':r['url']}]]})
        with self.db.c: self.db.c.execute('DELETE FROM outbox WHERE id=?',(r['id'],))
