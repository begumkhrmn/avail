import unittest,tempfile,pathlib,json
from main import DB,Bot
from test_main import FakeTG
from adapters import supported_stores
class Filters(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=DB(pathlib.Path(self.tmp.name)/'db'); self.db.put('owner',42)
        self.tg=FakeTG();self.bot=Bot(self.db,self.tg,'fake-secret-123')
        for store,n in [('Bershka',10),('Zara',2)]:
            for i in range(n):self.db.add(dict(url=f'https://example.com/{store}/{i}',store=store,name=f'{store} {i}',color='Siyah',size='S'))
    def tearDown(self): self.db.c.close();self.tmp.cleanup()
    def cb(self,x):self.bot.callback(42,42,x)
    def approve(self):self.db.put('verified_stores',json.dumps(['Bershka','Zara']))
    def text(self):return self.tg.messages[-1][1]
    def keys(self):return str(self.tg.messages[-1][2])
    def test_empty_support(self):
        self.cb('stores');self.assertIn('Henüz etkin mağaza yok',self.text());self.cb('filters');self.assertNotIn('Bershka',self.keys());self.assertNotIn('Zara',self.keys())
    def test_only_implemented_and_approved(self):
        self.approve();self.assertEqual(supported_stores(self.db),['Bershka']);self.cb('filters');self.assertIn('Bershka',self.keys());self.assertNotIn('Zara',self.keys());self.cb('stores');self.assertIn('Bershka',self.text());self.assertNotIn('Zara',self.text())
    def test_filtered_pagination(self):
        self.approve();self.cb('filter:Bershka');self.assertIn('10 ürün',self.text());self.assertNotIn('Zara',self.keys());self.assertIn('1 / 2',self.text());self.cb('list:1');self.assertIn('2 / 2',self.text());self.assertNotIn('Zara',self.keys());self.cb('filter:all');self.assertIn('12 ürün',self.text())
    def test_unsupported_callback(self):
        self.approve();self.cb('filter:Zara');self.assertIn('12 ürün',self.text());self.assertEqual(self.db.get('list_store'),'')
    def test_filter_survives_detail(self):
        self.approve();self.cb('filter:Bershka');self.cb('p:1');self.cb('list:0');self.assertIn('10 ürün',self.text());self.assertNotIn('Zara',self.keys())
    def test_removed_approval_clears_filter(self):
        self.approve();self.cb('filter:Bershka');self.db.put('verified_stores','[]');self.cb('list:0');self.assertIn('12 ürün',self.text())
    def test_scheduler_no_approval(self):
        self.db.put('monitor_enabled',1);self.bot.engine.source.check=lambda _:self.fail('unexpected network request');self.bot.engine.tick()
    def test_invalid_registry(self):
        self.db.put('verified_stores','not-json');self.assertEqual(supported_stores(self.db),[])
    def test_filter_empty_products(self):
        self.approve();self.db.c.execute("DELETE FROM products WHERE store='Bershka'");self.db.c.commit();self.cb('filter:Bershka');self.assertIn('0 ürün',self.text());self.assertIn('Henüz ürün yok.',self.text())
