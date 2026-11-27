# Sürekli çalışma

Linux / VPS için systemd hizmet şablonu. GitHub Actions'tan bağımsızdır. Mevcut Telegram arayüzünü çalıştırır; canlı stok kaynağı henüz etkin değildir.

## Önkoşullar

Python 3.10 veya üstü, systemd ve sürekli açık Linux makinesi. Kurulum için yönetici erişimi gerekir. Bu şablon bir makine sağlamaz; henüz canlı sunucuya kurulmamıştır.

1. Depoyu /opt/avail dizinine klonlayın.
2. Ayrı, giriş yapamayan avail sistem kullanıcısı oluşturun.
3. avail.env.example dosyasını /etc/avail/avail.env olarak kopyalayın ve root sahipliğinde 0600 izin verin. BOT_TOKEN ve en az 12 karakterli yeni PAIR_CODE girin. AVAIL_DATA_SOURCE=disabled kalsın.
4. Aynı Telegram botunu kullanan önceki süreci durdurun. İki ayrı getUpdates süreci çakışır.
5. Hizmet dosyasını /etc/systemd/system/avail.service olarak kopyalayın; sudo systemctl daemon-reload ve sudo systemctl enable --now avail komutlarını çalıştırın.
6. sudo systemctl status avail ve sudo journalctl -u avail -n 50 ile kontrol edin.

SQLite verisi /var/lib/avail içinde kalır. Mevcut kişisel veritabanı kendiliğinden taşınmaz. Kaynak koduna veya GitHub deposuna veritabanını yüklemeyin.

## Bağlantı durumu

GitHub Actions'taki Selenium denemesi mağazadan Access Denied aldı. FadeHost doğrudan HTTP denemeleri de 403 döndürdü. Hizmet kurulumu bu engeli çözmez. Mağaza tarafından izin verilen ve canlı testle doğrulanmış bir kaynak olmadan otomatik stok takibi açılmaz.

Yerel tek seferlik tanılama için, normal tarayıcı erişiminin ve mağaza koşullarının uygun olduğu bir bilgisayarda Python sanal ortamına selenium kurup repo kökünden python connection_test.py çalıştırılabilir. Erişim reddedilirse durur; ikinci yönteme otomatik geçmez.
