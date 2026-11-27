"""One-shot public-page diagnostic; no stock claims, bypasses or polling."""
import json, re, urllib.request, urllib.error
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs, urlencode


def identity(raw):
    u=urlsplit(raw)
    if u.scheme!='https' or u.hostname not in ('bershka.com','www.bershka.com') or u.username or u.password or u.port not in (None,443):
        raise ValueError('Bershka Türkiye ürün bağlantısı gerekli.')
    m=re.fullmatch(r'/tr/[^/]*c\d+p(\d+)\.html',u.path)
    if not m: raise ValueError('Bershka ürün bağlantısı gerekli.')
    q=parse_qs(u.query,keep_blank_values=True); colors=q.get('colorId',[])
    if len(colors)>1 or (colors and not re.fullmatch(r'\d{1,8}',colors[0])): raise ValueError('Renk kodu geçersiz.')
    color=colors[0] if colors else None
    return m[1],color

def canonical(raw):
    pid,color=identity(raw)
    return f'https://www.bershka.com/tr/c0p{pid}.html'+('?' + urlencode({'colorId':color}) if color else '')

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if identity(newurl)!=identity(req.full_url): raise ValueError('Ürün veya renk yönlendirmede değişti.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.capture=None; self.chunks=[]; self.title=''; self.h1=[]; self.ld=[]; self.meta={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('title','h1') and not self.capture: self.capture=tag;self.chunks=[]
        elif tag=='script' and a.get('type','').lower()=='application/ld+json' and not self.capture: self.capture='script'; self.chunks=[]
        elif tag=='meta':
            key=a.get('property') or a.get('name'); value=a.get('content','')
            if key in ('og:title','og:image','product:price:amount','product:price:currency'): self.meta[key]=value
    def handle_data(self,data):
        if self.capture: self.chunks.append(data)
    def handle_endtag(self,tag):
        if tag!=self.capture: return
        data=''.join(self.chunks).strip()
        if tag=='title': self.title=data
        elif tag=='h1': self.h1.append(data)
        else:
            try: self.ld.append(json.loads(data))
            except (ValueError,RecursionError): pass
        self.capture=None;self.chunks=[]

def nodes(obj,depth=0):
    if depth>12: return
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from nodes(v,depth+1)
    elif isinstance(obj,list):
        for v in obj: yield from nodes(v,depth+1)

def analyze(html):
    page=Page();page.feed(html)
    records=[n for obj in page.ld for n in nodes(obj)]
    products=[n for n in records if 'Product' in ([n.get('@type')] if isinstance(n.get('@type'),str) else n.get('@type',[]) if isinstance(n.get('@type'),list) else [])]
    offers=[n for n in records if 'availability' in n]
    return {'title':(page.h1[0] if page.h1 else page.meta.get('og:title') or page.title)[:180], 'products':len(products), 'offers':len(offers), 'image':bool(page.meta.get('og:image') or any(n.get('image') for n in products)), 'price':bool(page.meta.get('product:price:amount') or any(n.get('price') is not None for n in records)), 'variant_hint':bool(re.search(r'"(?:sku|size|colorId|availability)"\s*:',html,re.I)), 'challenge_hint':bool(re.search(r'access denied|verify you are human|captcha|request blocked',page.title,re.I))}

def probe(raw):
    url=canonical(raw); pid,color=identity(url)
    try:
        opener=urllib.request.build_opener(SafeRedirect())
        req=urllib.request.Request(url,headers={'User-Agent':'avail-personal-stock-diagnostic/0.3','Accept':'text/html'})
        with opener.open(req,timeout=8) as r:
            if identity(r.url)!=(pid,color): raise ValueError('Ürün veya renk değişti.')
            if r.headers.get_content_type()!='text/html': return 'Beklenmeyen içerik türü.'
            data=r.read(2_000_001)
            if len(data)>2_000_000: return 'Sayfa tanılama boyutu sınırını aştı.'
            result=analyze(data.decode(r.headers.get_content_charset() or 'utf-8',errors='replace'))
            yes=lambda b:'var' if b else 'yok'
            return '\n'.join([f'HTTP {r.status}',f'Ürün / renk: {pid} / {color or "belirtilmedi"}',f'Başlık: {result["title"] or "yok"}',f'Yapısal ürün: {result["products"]}',f'Yapısal stok alanı: {result["offers"]}',f'Fiyat alanı: {yes(result["price"])} · Fotoğraf: {yes(result["image"])}',f'Varyant alanı işareti: {yes(result["variant_hint"])}',f'Erişim engeli işareti: {yes(result["challenge_hint"])}','Beden stoku henüz doğrulanmadı.'])
    except urllib.error.HTTPError as e: return f'HTTP {e.code} · mağaza verisi doğrulanamadı.'
    except (OSError,ValueError,LookupError,RecursionError) as e: return f'Bağlantı doğrulanamadı ({type(e).__name__}).'
