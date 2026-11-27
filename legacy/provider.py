"""Optional documented Apify API pilot; no direct-store access bypass.
No requests unless explicitly enabled. Monthly cap counts attempts, not just successes.
"""
import json, os, re, time, urllib.request, urllib.error
from decimal import Decimal, InvalidOperation
from bershka_probe import identity, canonical

ACTOR='https://api.apify.com/v2/acts/sian.agency~bershka-product-scraper/run-sync-get-dataset-items?maxTotalChargeUsd=0.02&timeout=35'

def minor(value):
    try:
        v=Decimal(str(value))*100
        if not v.is_finite() or not 0<v<=100_000_000 or v!=v.to_integral_value(): return None
        return int(v)
    except (InvalidOperation, ValueError): return None

def text(value):
    return ' '.join(value.split()) if isinstance(value,str) and 0<len(value)<=160 else ''

def parse_dataset(data,url,discover=False):
    pid,color=identity(url); rows={}; conflicts=set()
    if not isinstance(data,list): raise ValueError('Veri yanıtı geçersiz.')
    for product in data:
        if not isinstance(product,dict): continue
        if product.get('brand')!='bershka' or product.get('country')!='TR' or product.get('currency')!='TRY': continue
        # url_id is the URL identifier, which can differ from catalogue product_id.
        if str(product.get('url_id') or product.get('product_id'))!=pid: continue
        try:
            if identity(product.get('url',''))[0]!=pid: continue
        except (ValueError,TypeError,AttributeError): continue
        name=text(product.get('name'))
        if not name or not isinstance(product.get('variants'),list): continue
        for v in product['variants']:
            if not isinstance(v,dict): continue
            cid=str(v.get('color_id','')); c=text(v.get('color')); s=text(v.get('size')); sku=str(v.get('sku',''))
            if not re.fullmatch(r'\d{1,8}',cid) or not c or not s or not re.fullmatch(r'\d{1,24}',sku): continue
            if not discover and color!=cid: continue
            status={True:'in',False:'out'}.get(v.get('is_buyable')) if type(v.get('is_buyable')) is bool else None
            price=minor(v.get('price'))
            if status is None and price is None: continue
            link=canonical(f'https://www.bershka.com/tr/c0p{pid}.html?colorId={cid}')
            key=(cid,s.casefold()); row=dict(name=name,color=c,size=s,color_id=cid,url=link,status=status,price=price,sku=sku)
            if key in rows and rows[key]!=row: conflicts.add(key)
            rows[key]=row
    return [v for k,v in rows.items() if k not in conflicts]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class ApifyPilot:
    def __init__(self,db): self.db=db
    def selected(self): return os.environ.get('AVAIL_DATA_SOURCE')=='apify'
    def enabled(self): return self.selected() and bool(os.environ.get('APIFY_TOKEN','').strip())
    def check(self,url,discover=False):
        pid,_=identity(url)
        if not self.enabled(): raise ValueError('Veri servisi etkin değil.')
        # Do not allow a billing configuration to turn this into unbounded polling.
        # $0.02 run cap x 100 attempts = $2 cap on charged events, not a guarantee of overall platform cost.
        key='apify_attempts:'+time.strftime('%Y-%m',time.gmtime())
        with self.db.c:
            attempts=int(self.db.get(key,'0'))
            if attempts>=100: raise ValueError('Aylık deneme kotası doldu.')
            self.db.c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v',(key,str(attempts+1)))
        body={'mode':'detail','country':'TR','productUrls':[canonical(url)],'maxItems':1}
        req=urllib.request.Request(ACTOR,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['APIFY_TOKEN'].strip(),'Accept':'application/json'})
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=50) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise ValueError('Veri yanıtı çok büyük.')
            result=json.loads(raw)
        return parse_dataset(result,url,discover)
