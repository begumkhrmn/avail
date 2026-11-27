import os, json, tempfile, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
from main import DB, Bot
from monitor import Engine, record
from provider import parse_dataset, ApifyPilot, ACTOR
from test_main import FakeTG

URL='https://www.bershka.com/tr/c0p243093353.html?colorId=800'
def data(stock=False,price=2890):
    return [dict(brand='bershka',country='TR',currency='TRY',url_id=243093353,product_id=999,url=URL,name='Düğmeli kruvaze blazer',variants=[dict(sku=10,color_id=800,color='Siyah',size='S',is_buyable=stock,price=price),dict(sku=11,color_id=800,color='Siyah',size='M',is_buyable=True,price=2890),dict(sku=12,color_id=400,color='Mavi',size='S',is_buyable=True,price=2890)])]
class Response:
    def __init__(self,x): self.x=x
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def read(self,n): return self.x[:n]
class PilotTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.db=DB(Path(self.t.name)/'db');self.db.put('owner',42);self.e=Engine(self.db);self.p=ApifyPilot(self.db)
    def tearDown(self): self.db.c.close();self.t.cleanup()
    def test_selected_color(self): self.assertEqual([(r['size'],r['status']) for r in parse_dataset(data(),URL)],[('S','out'),('M','in')])
    def test_discovery(self): self.assertEqual({r['color'] for r in parse_dataset(data(),URL,True)},{'Siyah','Mavi'})
    def test_wrong_market(self):
        d=data();d[0]['country']='DE';self.assertEqual(parse_dataset(d,URL),[])
    def test_wrong_currency(self):
        d=data();d[0]['currency']='EUR';self.assertEqual(parse_dataset(d,URL),[])
    def test_wrong_product(self):
        d=data();d[0]['url_id']=123;self.assertEqual(parse_dataset(d,URL),[])
    def test_missing_stock_is_unknown(self):
        d=data();d[0]['variants'][0]['is_buyable']='false';self.assertIsNone(parse_dataset(d,URL)[0]['status'])
    def test_missing_size_is_not_one_size(self):
        d=data();d[0]['variants'][0].pop('size');self.assertEqual([r['size'] for r in parse_dataset(d,URL)],['M'])
    def test_bad_price(self): self.assertIsNone(parse_dataset(data(price='NaN'),URL)[0]['price'])
    def test_conflicting_variant_rejected(self):
        d=data();d[0]['variants'].append(dict(d[0]['variants'][0],is_buyable=True));self.assertEqual([r['size'] for r in parse_dataset(d,URL)],['M'])
    def test_no_token_no_requests(self):
        with patch.dict(os.environ,{},clear=True),patch('provider.urllib.request.build_opener') as call:
            with self.assertRaises(ValueError): self.p.check(URL)
            call.assert_not_called()
    def test_request_and_budget(self):
        with patch.dict(os.environ,{'AVAIL_DATA_SOURCE':'apify','APIFY_TOKEN':'test-only'},clear=True),patch('provider.urllib.request.build_opener') as op:
            op.return_value.open.return_value=Response(json.dumps(data()).encode())
            self.assertEqual(len(self.p.check(URL)),2)
            req=op.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url,ACTOR);self.assertEqual(req.get_header('Authorization'),'Bearer test-only')
            self.assertEqual(json.loads(req.data)['productUrls'],[URL]);self.assertNotIn('test-only',req.full_url)
            key=next(r[0] for r in self.db.c.execute("select k from settings where k like 'apify_attempts:%'"));self.db.put(key,100)
            with self.assertRaises(ValueError): self.p.check(URL)
            self.assertEqual(op.return_value.open.call_count,1)
    def test_pilot_no_scheduled_requests(self):
        self.db.put('monitor_enabled',1);self.db.put('verified_stores','["Bershka"]');self.db.add(dict(url=URL,store='Bershka',name='Blazer',color='Siyah',size='S'))
        with patch.dict(os.environ,{'AVAIL_DATA_SOURCE':'apify','APIFY_TOKEN':'test-only'},clear=True),patch.object(self.e.source,'check') as c:
            self.e.tick();c.assert_not_called()
    def test_end_to_end_ui_and_durable_stock_price(self):
        tg=FakeTG();b=Bot(self.db,tg,'test-secret-123');b.engine.source.discover=lambda url:parse_dataset(data(),url,True)
        b.message(42,42,URL);self.assertEqual(self.db.draft(42)[1]['picked'],['Siyah']);b.callback(42,42,'pickdone:color')
        self.assertIn('S · Tükendi',str(tg.messages[-1][2]));self.assertIn('M · Stokta',str(tg.messages[-1][2]));b.callback(42,42,'pick:size:0');b.callback(42,42,'pickdone:size')
        self.assertIn('Ürün listeye eklendi',tg.messages[-1][1]);p=self.db.product(1);self.assertEqual(p['size'],'S')
        b.engine.check_one(p,123,rows=urllib.error.HTTPError(URL,403,'Forbidden',{},None))
        self.assertEqual(self.db.c.execute('select count(*) from outbox').fetchone()[0],0)
        record(self.db,p,parse_dataset(data(True,1990),URL),124);record(self.db,p,parse_dataset(data(True,1990),URL),125)
        self.assertEqual(self.db.c.execute('select count(*) from outbox').fetchone()[0],2)
        self.db.put('monitor_enabled',1);self.db.put('verified_stores','["Bershka"]');b.engine.deliver(tg);b.engine.deliver(tg)
        self.assertEqual(self.db.c.execute('select count(*) from outbox').fetchone()[0],0)
        self.assertIn('Fiyat düştü',tg.messages[-1][1]);self.assertIn('1.990,00 TL',tg.messages[-1][1])

    def test_selected_without_token_does_not_fall_back(self):
        with patch.dict(os.environ,{'AVAIL_DATA_SOURCE':'apify'},clear=True),patch.object(self.e.source,'fetch') as direct:
            with self.assertRaises(ValueError): self.e.source.check(URL)
            direct.assert_not_called()
    def test_default_direct_source_disabled(self):
        with patch.dict(os.environ,{},clear=True),patch.object(self.e.source,'fetch') as direct:
            with self.assertRaises(ValueError): self.e.source.check(URL)
            direct.assert_not_called()
