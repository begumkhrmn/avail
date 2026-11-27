import unittest, tempfile, pathlib, sqlite3
from main import Bot, DB, product_url, Telegram, TelegramError
class FakeTG:
    def __init__(self): self.messages=[];self.renders=[];self.sent=0
    def send(self,chat,text,markup=None): self.messages.append((chat,text,markup));self.sent+=1;return {"message_id":self.sent}
    def render(self,chat,text,markup=None,message_id=None):
        self.renders.append(message_id)
        if message_id is None: return self.send(chat,text,markup)["message_id"]
        self.messages.append((chat,text,markup));return message_id
    def call(self,*a,**k): pass
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.tmp.name)/'test.db';self.db=DB(self.path);self.tg=FakeTG();self.bot=Bot(self.db,self.tg,'test-secret-123');self.bot.engine.source.discover=lambda _: []
    def tearDown(self): self.db.c.close();self.tmp.cleanup()
    def msg(self,t,user=42): self.bot.handle({'message':{'chat':{'id':user,'type':'private'},'from':{'id':user},'text':t}})
    def cb(self,t,user=42): self.bot.handle({'callback_query':{'id':'x','from':{'id':user},'data':t,'message':{'chat':{'id':user,'type':'private'}}}})
    def add(self):
        self.msg('/baglan test-secret-123');self.cb('add');self.msg('Ceket - Bershka https://www.bershka.com/tr/urun');self.cb('manualadd');self.msg('Bordo');self.msg('XS, S')
    def test_pair_and_access(self):
        self.msg('/baglan test-secret-123');self.assertEqual(self.db.get('owner'),'42');n=len(self.tg.messages);self.msg('/start',99);self.assertEqual(n,len(self.tg.messages))
    def test_product_crud(self):
        self.add();self.assertEqual(self.db.count(),1);self.assertEqual(self.db.product(1)['size'],'XS, S');self.cb('field:1:size');self.msg('M');self.assertEqual(self.db.product(1)['size'],'M');self.cb('toggle:1:paused');self.assertEqual(self.db.product(1)['paused'],1);self.cb('yesdel:1');self.assertEqual(self.db.count(),0)
    def test_persistence(self):
        self.add();other=DB(self.path);self.assertEqual(other.count(),1);self.assertEqual(other.get('owner'),'42');other.c.close()
    def test_test_notification(self):
        self.msg('/baglan test-secret-123');self.cb('test');self.assertEqual(len(self.db.events()),0);self.assertIn('Test bildirimi gönderildi',self.tg.messages[-1][1]);self.assertEqual(self.tg.sent,2)
    def test_domains(self):
        self.assertEqual(product_url('https://ty.gl/abc')[1],'Trendyol (kısa link)');self.assertEqual(product_url('https://bershka.com.evil.example/a')[1],'Diğer mağaza')
        for url in ['http://example.com/a','https://user:pass@example.com','https://example.com:bad/a','https://example.com/a b']:
            with self.assertRaises(ValueError): product_url(url)
    def test_duplicate(self):
        self.add();self.cb('add');self.msg('Ceket - Bershka https://www.bershka.com/tr/urun');self.cb('manualadd');self.msg('Bordo');self.msg('XS, S');self.assertEqual(self.db.count(),1)
    def test_unknown_stock(self):
        self.add();self.cb('p:1');self.assertIn('stok bilinmiyor',self.tg.messages[-1][1].lower())
    def test_wrong_code(self):
        self.msg('/baglan wrong');self.assertIsNone(self.db.get('owner'))
    def test_single_screen(self):
        self.msg('/baglan test-secret-123');self.cb('list:0');self.cb('home');self.cb('settings')
        self.assertEqual(self.tg.sent,1);self.assertEqual(self.tg.renders,[None,1,1,1]);self.assertNotIn('Sürüm',self.tg.messages[-1][1])
    def test_button_selection(self):
        from test_monitor import page, URL
        from monitor import extract
        self.bot.engine.source.discover=lambda _: extract(page(),URL,discover=True)+extract(page(size='XS'),URL,discover=True)
        self.msg('/baglan test-secret-123');self.msg(URL)
        self.assertEqual(self.db.draft(42)[0],'color');self.assertEqual(self.db.draft(42)[1]['picked'],['Siyah'])
        self.cb('pickdone:color');self.cb('pick:size:0');self.cb('pick:size:1');self.cb('pickdone:size')
        self.assertEqual(self.db.product(1)['color'],'Siyah');self.assertEqual(self.db.product(1)['size'],'S, XS');self.assertIn('Ürün listeye eklendi',self.tg.messages[-1][1]);self.assertEqual(self.tg.sent,2)
    def test_unverified_no_invented_choices(self):
        self.msg('/baglan test-secret-123');self.msg('https://www.bershka.com/tr/c0p243093353.html?colorId=800');self.cb('manualadd')
        self.assertNotIn('Siyah',str(self.tg.messages[-1][2]));self.assertIn('doğrulanamadı',self.tg.messages[-1][1])
    def test_edit_api(self):
        tg=Telegram('fake');calls=[]
        def call(method,**kw):
            calls.append(method)
            if method=='editMessageText': raise TelegramError(400,'message is not modified')
            return {'message_id':42}
        tg.call=call;self.assertEqual(tg.render(1,'avail',message_id=10),10);self.assertEqual(calls,['editMessageText'])
        def missing(method,**kw):
            calls.append(method)
            if method=='editMessageText': raise TelegramError(400,'message to edit not found')
            return {'message_id':42}
        tg.call=missing;self.assertEqual(tg.render(1,'avail',message_id=10),42);self.assertEqual(calls[-2:],['editMessageText','sendMessage'])
    def test_start_creates_fresh_screen(self):
        self.msg('/baglan test-secret-123');self.msg('/start');self.assertEqual(self.tg.sent,2);self.assertEqual(self.db.get('screen_message'),'2');self.cb('list:0');self.assertEqual(self.tg.sent,2)
    def test_url_only(self):
        self.msg('/baglan test-secret-123');self.msg('https://www.bershka.com/tr/c0p243093353.html?colorId=800')
        self.assertEqual(self.db.draft(42)[0],'unverified');self.cb('manualadd')
        self.msg('Siyah');self.msg('S');self.assertEqual(self.db.product(1)['name'],'Ürün 243093353')
    def test_shared_title_optional(self):
        self.msg('/baglan test-secret-123');self.msg('Düğmeli kruvaze blazer - Bershka https://www.bershka.com/tr/c0p243093353.html?colorId=800')
        self.cb('manualadd');self.msg('Siyah');self.msg('S');self.assertEqual(self.db.product(1)['name'],'Düğmeli kruvaze blazer')
    def test_safe_diagnostic(self):
        e=TelegramError(409,'Conflict: terminated by other getUpdates request secret-token','getUpdates');self.assertIn('409',e.diagnostic());self.assertNotIn('secret-token',e.diagnostic())
if __name__=='__main__': unittest.main()
