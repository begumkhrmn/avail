import unittest, json, tempfile, pathlib
from main import DB, Bot
from test_main import FakeTG
from monitor import extract, Engine, record, amount, reset
URL='https://www.bershka.com/tr/c0p243093353.html?colorId=800'
def page(status='OutOfStock',price='2890',size='S',color='Siyah',url=URL):
    p={'@type':'Product','name':'Blazer','size':size,'color':color,'offers':{'@type':'Offer','url':url,'availability':'https://schema.org/'+status,'price':price,'priceCurrency':'TRY'}}
    return '<html><script type="application/ld+json">'+json.dumps(p)+'</script></html>'
class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=DB(pathlib.Path(self.tmp.name)/'test.db');self.engine=Engine(self.db);self.db.put('owner',42)
        self.i=self.db.add(dict(url=URL,store='Bershka',name='Blazer',color='Siyah',size='S'));self.p=self.db.product(self.i)
    def tearDown(self): self.db.c.close();self.tmp.cleanup()
    def count(self,table): return self.db.c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
    def test_variant(self): self.assertEqual(extract(page(),URL)[0]['status'],'out')
    def test_wrong_color_id(self): self.assertEqual(extract(page(url=URL.replace('800','900')),URL),[])
    def test_no_size(self): self.assertEqual(extract(page(size=None),URL),[])
    def test_invalid_price(self): self.assertIsNone(amount({'priceCurrency':'USD','price':'10'}));self.assertIsNone(amount({'priceCurrency':'TRY','price':'NaN'}))
    def test_wrong_size(self): self.assertFalse(record(self.db,self.p,extract(page(size='M'),URL),1));self.assertEqual(self.count('outbox'),0)
    def test_first_observation(self): record(self.db,self.p,extract(page('InStock'),URL),1);self.assertEqual(self.count('outbox'),0);self.assertEqual(self.count('prices'),1)
    def test_stock_and_price(self):
        record(self.db,self.p,extract(page(),URL),1);record(self.db,self.p,extract(page('InStock','1990'),URL),2);self.assertEqual(self.count('outbox'),2);self.assertEqual(self.count('prices'),2)
        record(self.db,self.p,extract(page('InStock','1990'),URL),3);self.assertEqual(self.count('outbox'),2)
    def test_failure_unknown(self):
        record(self.db,self.p,extract(page(),URL),1);self.engine.source.check=lambda _: [];self.assertEqual(self.engine.check_one(self.p,2),'Doğrulanamadı');self.assertIsNone(self.db.c.execute('SELECT stock_state FROM variant_state').fetchone()[0]);record(self.db,self.p,extract(page('InStock'),URL),3);self.assertEqual(self.count('outbox'),1)
    def test_scheduler_disabled(self): self.engine.source.check=lambda _: self.fail('network when disabled');self.engine.tick()
    def test_delivery(self):
        record(self.db,self.p,extract(page(),URL),1);record(self.db,self.p,extract(page('InStock'),URL),2);tg=FakeTG();self.engine.deliver(tg);self.assertEqual(tg.sent,0);self.db.put('monitor_enabled',1); self.db.put('verified_stores','["Bershka"]');self.engine.deliver(tg);self.assertEqual(tg.sent,1);self.assertEqual(self.count('outbox'),0)
    def test_reset(self): record(self.db,self.p,extract(page(),URL),1);reset(self.db,self.i);self.assertEqual(self.count('variant_state'),0);self.assertEqual(self.count('prices'),0)
    def test_share_title(self):
        tg=FakeTG();b=Bot(self.db,tg,'example-secret');b.engine.source.discover=lambda _: [];b.message(42,42,'Düğmeli kruvaze blazer - Bershka '+URL);step,d=self.db.draft(42);self.assertEqual(step,'unverified');self.assertEqual(d['name'],'Düğmeli kruvaze blazer')
    def test_verified_name_replaces_placeholder(self):
        self.db.update(self.i,'name','Ürün 243093353'); p=self.db.product(self.i)
        record(self.db,p,extract(page(),URL),1)
        self.assertEqual(self.db.product(self.i)['name'],'Blazer')
    def test_manual_name_preserved(self):
        self.db.update(self.i,'name','İş ceketi'); p=self.db.product(self.i)
        record(self.db,p,extract(page(),URL),1)
        self.assertEqual(self.db.product(self.i)['name'],'İş ceketi')
    def test_live_options(self):
        self.db.put('monitor_enabled',1);tg=FakeTG();b=Bot(self.db,tg,'example-secret');b.engine.source.discover=lambda _: extract(page(),URL,discover=True);b.message(42,42,URL);step,d=self.db.draft(42);self.assertEqual(step,'color');self.assertEqual(d['picked'],['Siyah']);b.callback(42,42,'pickdone:color');step,d=self.db.draft(42);self.assertEqual(step,'size');self.assertEqual(d['choices_size'],['S'])

    def test_discover_alt_color(self):
        alt=URL.replace('800','400');html=page()+page(color='Mavi',url=alt)+page(color='Yeşil',url=alt.replace('243093353','99999'))
        self.assertEqual({r['color'] for r in extract(html,URL,discover=True)},{'Siyah','Mavi'})
        self.assertEqual({r['color'] for r in extract(html,URL)},{'Siyah'})
        tg=FakeTG();b=Bot(self.db,tg,'example-secret');b.engine.source.discover=lambda _:extract(html,URL,discover=True)
        b.message(42,42,URL);b.callback(42,42,'pick:color:1');b.callback(42,42,'pickdone:color');b.callback(42,42,'pick:size:0');b.callback(42,42,'pickdone:size')
        self.assertEqual(self.db.product(2)['url'],alt)

    def test_scheduler_groups_same_url_and_throttles(self):
        from unittest.mock import patch
        self.db.add(dict(url=URL,store='Bershka',name='Blazer',color='Siyah',size='M'))
        self.db.put('monitor_enabled',1); self.db.put('verified_stores','["Bershka"]')
        calls=[]
        def source(url):
            calls.append(url)
            return extract(page()+page(size='M'),url)
        self.engine.source.check=source
        with patch('monitor.time.time',return_value=1000): self.engine.tick()
        self.assertEqual(calls,[URL]); self.assertEqual(self.count('check_state'),2)
        self.assertEqual(self.db.get('next_store_request'),'1060')
        with patch('monitor.time.time',return_value=1059): self.engine.tick()
        self.assertEqual(len(calls),1)
        with patch('monitor.time.time',return_value=1060): self.engine.tick()
        self.assertEqual(len(calls),2)
    def test_scheduler_failure_no_duplicate_request(self):
        from unittest.mock import patch
        self.db.put('monitor_enabled',1); self.db.put('verified_stores','["Bershka"]'); calls=[]
        def source(url):
            calls.append(url); raise OSError('test')
        self.engine.source.check=source
        with patch('monitor.time.time',return_value=1000): self.engine.tick()
        self.assertEqual(calls,[URL]); self.assertEqual(self.count('check_state'),1)

    def test_price_drop_after_failed_check(self):
        record(self.db,self.p,extract(page(),URL),1)
        self.engine.check_one(self.p,2,rows=OSError('offline'))
        self.assertIsNone(self.db.c.execute('SELECT amount FROM variant_state').fetchone()[0])
        record(self.db,self.p,extract(page(price='1990'),URL),3)
        self.assertEqual(self.count('outbox'),1)
        self.assertEqual(self.count('prices'),2)
    def test_confirmed_reset(self):
        record(self.db,self.p,extract(page(),URL),1)
        reset(self.db,self.i)
        self.assertEqual(self.count('confirmed_state'),0)
