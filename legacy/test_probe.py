import unittest
from bershka_probe import identity,canonical,analyze
from main import product_url
class ProbeTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(identity('https://www.bershka.com/tr/c0p243093353.html?colorId=800'),('243093353','800'))
        self.assertEqual(canonical('https://www.bershka.com/tr/blazer-c0p243093353.html?colorId=800&utm_source=app'),'https://www.bershka.com/tr/c0p243093353.html?colorId=800')
    def test_share_text(self):
        self.assertEqual(product_url('Düğmeli kruvaze blazer - Bershka https://www.bershka.com/tr/c0p243093353.html?colorId=800')[1],'Bershka')
    def test_invalid(self):
        for url in ('https://bershka.com.evil.test/tr/c0p1.html','https://www.bershka.com/tr/c0p1.html?colorId=800&colorId=900','https://www.bershka.com/es/c0p1.html'):
            with self.assertRaises(ValueError): identity(url)
    def test_structured(self):
        r=analyze('<h1>Blazer</h1><script type="application/ld+json">{"@type":"Product","image":"x","offers":{"price":123,"availability":"https://schema.org/InStock"}}</script>')
        self.assertEqual(r['products'],1);self.assertEqual(r['offers'],1);self.assertTrue(r['price'])
    def test_no_stock_inference(self):
        r=analyze('<h1>Blazer</h1><button>S</button><button>Sepete ekle</button>')
        self.assertEqual(r['offers'],0);self.assertFalse(r['price'])
