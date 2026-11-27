# avail

Kişisel alışveriş takibi.

Ürünlerin renk, beden, stok ve fiyat değişikliklerini Telegram üzerinden takip etmek için geliştirilmektedir.

## Durum

Bağımsız proje. Önceki avail uygulamasının Python kaynakları ve 65 yerel testi `legacy/` altında korunmaktadır. Bu kaynaklar yeni canlı bağlantıya henüz entegre edilmemiştir.

27 Kasım 2026: GitHub Actions üzerinde Python 3.12, Selenium ve Chrome başarıyla çalıştı. Bershka Türkiye ürün sayfası Access Denied döndürdü. [Gerçek çalışma kaydı](https://github.com/begumkhrmn/avail/actions/runs/45992871133).

Otomatik mağaza sorgusu ve stok bildirimi etkin değildir. Bağlantı hatası ürünün tükendiği anlamına gelmez.

## Hedef

- Telegram üzerinden ürün bağlantısı ekleme, ürün adı ve fotoğrafı.
- Renk ve beden seçimi.
- Stok dönüşü ve fiyat düşüşü bildirimi.
- Fiyat geçmişi, mağaza filtresi ve takip yönetimi.

## Dosyalar

- `connection_test.py`: manuel, salt okunur tarayıcı teşhisi. Erişim reddedilirse durur.
- `legacy/`: önceki test adayının Telegram arayüzü, SQLite veritabanı kodu, izleme motoru ve testleri. Eski isteğe bağlı Apify denemesi yalnızca arşivdir; etkinleştirilmez.
- `.github/workflows/`: bağlantı teşhisi ve ağ kullanmayan regresyon testleri.

## Altyapı

GitHub Actions sürekli çalışan Telegram botunun yerine geçmez. Ürün kayıtları kalıcı bir çalışma ortamında saklanır; açık repoya yazılmaz.

Gizli değerler yalnızca ortam değişkenleri ve GitHub Secrets ile yönetilir. Mağaza erişim kurallarına uyulur. Firecrawl veya Apify bu yeni bağlantı testinin parçası değildir.

