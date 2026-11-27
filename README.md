# avail

Kişisel alışveriş takibi.

Ürünlerin renk, beden, stok ve fiyat bilgilerini Telegram üzerinden takip etmek için geliştirilmektedir.

## Durum

Bağımsız proje. Önce Bershka Türkiye üzerinden canlı bağlantı doğrulanır. Stok bilgisi alınamaması, ürünün tükendiği anlamına gelmez. Canlı erişim ve mağaza koşulları doğrulanmadan otomatik takip açılmaz.

## Kullanım hedefi

- Telegram üzerinden ürün bağlantısı ekleme.
- Ürün adı, fotoğrafı, renk ve beden seçenekleri.
- Stok dönüşü ve fiyat düşüşü bildirimleri.
- Fiyat geçmişi, mağaza filtresi ve takip yönetimi.

## Bağlantı testi

GitHub Actions üzerindeki bağlantı testi, iki herkese açık Bershka ürün sayfasını normal bir Chromium tarayıcısıyla açar ve ürün kimliği, renk, fiyat ve beden durumunu kontrol eder. Satın alma veya otomatik takip yapmaz. Erişim reddedilirse test durur.

## Altyapı

GitHub Actions canlı bağlantı ve yazılım testleri içindir; sürekli çalışan Telegram botunun yerini tutmaz. Telegram arayüzü için kalıcı çalışma ortamı ve SQLite veritabanı gerekir.

Gizli değerler kaynak koduna yazılmaz. Bu depo herkese açıktır; kişisel takip listesi ve veritabanı burada tutulmaz.

