# Pardus Paket Oluşturucu

**Pardus için, izole Docker konteynerleri kullanarak reçete (recipe) tabanlı ve otomatikleştirilmiş bir `.deb` paket oluşturma aracı.**

> ⚠️ **Geliştirme aşamasında (Work in Progress).** Bu proje henüz kararsızdır, `main` dalına force push yapılmaktadır ve Git geçmişi herhangi bir anda yeniden yazılabilir.

[🇬🇧 Click for English README](README.md)

![Status](https://img.shields.io/badge/durum-geli%C5%9Ftirme%20a%C5%9Famas%C4%B1nda-red.svg)
![License](https://img.shields.io/badge/lisans-GPL--3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Docker](https://img.shields.io/badge/build%20motoru-Docker-2496ED.svg)
![Platform](https://img.shields.io/badge/platform-Pardus%20%2F%20Debian%20t%C3%BCrevleri-orange.svg)

---

## Hakkında

**Pardus Paket Oluşturucu**, basit bir JSON **reçete (recipe)** dosyasını takip ederek kaynak koddan `.deb` paketleri oluşturan bir komut satırı aracıdır — kavramsal olarak AUR'daki `PKGBUILD`lara veya Gentoo'daki `ebuild`lara benzer, ancak Debian/Pardus paketlemesini hedefler ve her build adımını izolasyon ve tekrarlanabilirlik için tek kullanımlık bir **Docker konteyneri** içinde çalıştırır.

Build bağımlılıklarını ana sisteminize kurmak yerine, araç (varsayılan olarak bir Pardus imajı tabanlı) bir konteyner başlatır, kaynağı indirip doğrular, varsa yamaları (patch) uygular, sadece o reçetenin ihtiyaç duyduğu bağımlılıkları kurar, build komutunu çalıştırır ve sonunda size kuruma hazır bir `.deb` dosyası teslim eder — tüm bu süreç boyunca ana sisteminiz temiz kalır.

## Nasıl Çalışır

Belirli bir reçete için araç şu adımları takip eder:

1. **Reçeteyi ayrıştırma** — neyin nasıl build edileceğini tanımlayan JSON dosyasını okur.
2. **Kaynağı indirme** — reçetedeki URL'den kaynak arşivini/dosyasını indirir.
3. **Bütünlük doğrulama** — indirilen dosyanın SHA-256 hash'ini reçetede belirtilenle karşılaştırır.
4. **Önbellekleme (cache)** — başarılı indirmeler `~/.cache/pardus-package-builder` altında önbelleğe alınır, böylece aynı build'i tekrar çalıştırdığınızda değişmeyen kaynaklar yeniden indirilmez.
5. **Yamaları uygulama** (isteğe bağlı) — reçetede listelenen yamaları indirip doğrular, ardından `patch -p1` ile uygular.
6. **Kaynağı gözden geçirme** (isteğe bağlı, etkileşimli) — build'den önce çıkarılan kaynak dizinini dosya yöneticinizde açmayı teklif eder, böylece build öncesi inceleme veya küçük düzenlemeler yapabilirsiniz.
7. **Docker konteynerini başlatma** — belirtilen imajdan (varsayılan `pardus/yirmibes`) kaynak dizini bir volume olarak bağlanmış şekilde bir konteyner başlatır.
8. **Build bağımlılıklarını kurma** — reçetede listelenen paketler için konteyner içinde `apt-get install` çalıştırır.
9. **Build komutunu çalıştırma** — reçetenin `build_cmd`'sini konteyner içinde çalıştırır ve çıktıyı terminalinize akıtır.
10. **Temizlik** — varsa `clean_cmd`'yi çalıştırır, ardından konteyneri durdurup kaldırır.
11. **Kurma veya dışa aktarma** — ya oluşan `.deb` dosyasını doğrudan kurulum için açar ya da nereye kaydetmek istediğinizi sorar.

## Reçete Formatı

Bir reçete, bir build'i yeniden üretmek için gereken her şeyi tanımlayan bir JSON dosyasıdır:

```json
{
    "name": "Pardus System Services Manager",
    "version": "1.0.0",
    "build_deps": [
        "make", "binutils", "python3", "python3-venv", "dpkg",
        "libglib2.0-0", "libfontconfig1", "libfreetype6",
        "libxkbcommon0", "libx11-6", "libdbus-1-3",
        "libgssapi-krb5-2", "libbrotli1"
    ],
    "env_vars": [],
    "install": {
        "name": "pardus-system-services-manager.tar.gz",
        "url": "https://github.com/V6lhost/pardus-system-services-manager/tarball/2d00076",
        "sha256": "90dbe23cccd45c9fefbb59c831e50da626fbf9e210c9aa449c6fe28695e5a827",
        "type": "archive",
        "subdir": "V6lhost-pardus-system-services-manager-2d00076",
        "patches": [
            {
                "name": "patch1.patch",
                "url": "https://github.com/V6lhost/pardus-system-services-manager/commit/030e8c4d83ae9c1c75674b2b11ff88f550460791.patch",
                "sha256": "10ef27bd99238cdc199967891c3e68014c8a33552e80d2aece02f31c5d10dab0"
            }
        ]
    },
    "build_cmd": "make build",
    "clean_cmd": "make clean",
    "export_file": "output_deb/pardus-system-services-manager-1.0.0.deb"
}
```

| Alan | Açıklama |
|---|---|
| `name` | İnsan tarafından okunabilir paket/proje adı |
| `version` | Build edilen sürüm |
| `build_deps` | Build öncesi konteyner içine kurulacak Debian/Pardus paketlerinin listesi |
| `env_vars` | Build için ayarlanacak, isteğe bağlı ortam değişkenleri listesi |
| `install.name` | İndirilen kaynağın kaydedileceği dosya adı |
| `install.url` | Kaynağın indirileceği URL |
| `install.sha256` | İndirilen kaynağın beklenen SHA-256 checksum'ı |
| `install.type` | `"archive"` (otomatik olarak çıkarılır) veya düz bir dosya |
| `install.subdir` | Çıkarılan arşiv içinde build'in yapılacağı alt dizin (üst klasör altında içerik barındıran GitHub tarball'ları için kullanışlıdır) |
| `install.patches` | Build öncesi uygulanan, her biri kendi `url` ve `sha256`'sına sahip isteğe bağlı yama listesi |
| `build_cmd` | Paketi build etmek için konteyner içinde çalıştırılan shell komutu |
| `clean_cmd` | Build sonrası temizlik için isteğe bağlı shell komutu |
| `export_file` | Oluşan `.deb` dosyasının yolu (build dizinine göre göreceli) |

Depo içinde [`examples/test-pardus-system-services-manager.json`](examples/test-pardus-system-services-manager.json) altında örnek bir reçete bulunuyor — güzel bir tesadüf olarak bu reçete, aynı geliştiricinin başka bir projesi olan [pardus-system-services-manager](https://github.com/V6lhost/pardus-system-services-manager)'ı build ediyor.

## Gereksinimler

- Python **3.11+**
- **Docker** (`docker.io`) — build konteyner motoru
- `python3-docker`, `python3-rich` (`requirements.txt` üzerinden veya `.deb` paketiyle otomatik kurulur)
- `xdg-user-dir` / `xdg-utils` — İndirilenler klasörünü bulmak ve dosya/klasörleri açmak için kullanılır
- Konteyner içinde `patch` aracı (reçetenizin buna ihtiyacı varsa `build_deps`'e ekleyin)

## Kurulum

### Yöntem 1 — `.deb` paketi oluşturup kurma (önerilen)

```bash
git clone https://github.com/V6lhost/pardus-package-builder.git
cd pardus-package-builder
make build
sudo dpkg -i output_deb/pardus-package-builder-*.deb
```

Paketin kurulum sonrası (postinst) betiği, `sudo`'yu çalıştıran kullanıcıyı (eğer `docker` grubu mevcutsa) otomatik olarak `docker` grubuna ekler, böylece araç ekstra bir ayara gerek kalmadan Docker daemon'ı ile konuşabilir. **Grup değişikliğinin etkili olması için oturumu kapatıp tekrar açmanız (veya yeni bir kabuk oturumu başlatmanız) gerekir.**

### Yöntem 2 — Kaynak koddan doğrudan çalıştırma (geliştirme için)

```bash
git clone https://github.com/V6lhost/pardus-package-builder.git
cd pardus-package-builder
pip install -r requirements.txt
make run
```

### Build dosyalarını temizleme

```bash
make clean
```

## Kullanım

```bash
pardus-package-builder <recipe.json> [SEÇENEKLER]
```

| Seçenek | Açıklama |
|---|---|
| `recipe` | Build'i tanımlayan JSON reçete dosyasının yolu (zorunlu) |
| `-p`, `--no-prompt` | Etkileşimli sorular olmadan doğrudan build eder (hata durumunda sormak yerine hemen durur) |
| `-i`, `--install-directly` | Sormadan oluşan paketi otomatik olarak kurar |

**Örnek:**

```bash
pardus-package-builder examples/test-pardus-system-services-manager.json
```

Varsayılan olarak araç, build öncesi kaynağı incelemek isteyip istemediğinizi ve sonrasında oluşan paketi kurmak mı yoksa özel bir konuma dışa aktarmak mı istediğinizi etkileşimli olarak sorar.

## Proje Yapısı

```
pardus-package-builder/
├── debian/          # Debian paketleme metadata'sı, control dosyası, postinst betiği, launcher
├── examples/         # Örnek reçete dosyaları
├── src/              # Uygulama kaynak kodu (package-builder.py)
├── Makefile           # Build, çalıştırma ve paketleme otomasyonu
├── requirements.txt
└── LICENSE
```

## Güvenlik Notları

- Bir reçetenin `build_cmd`, `clean_cmd` ve `build_deps` alanları, build konteyneri **içinde gerçek shell komutları olarak çalıştırılır** — reçete dosyalarına, güvenilmeyen bir kaynaktan gelen shell betiğine yaklaştığınız gibi yaklaşın ve yalnızca güvendiğiniz reçeteleri çalıştırın.
- Kaynak arşivleri ve yamalar, reçetede belirtilen SHA-256 hash'i ile bütünlük kontrolünden geçirilir; ancak bu yalnızca dosyanın reçete *yazarının* belirttiğiyle eşleştiğini garanti eder — reçete yazarının niyetini garanti etmez.
- Build'ler tek kullanımlık bir konteyner içinde çalışarak build bağımlılıklarını ana sisteminizden izole eder, fakat build konteynerinin kaynak dizininize okuma/yazma erişimiyle bağlı olduğunu unutmayın.

## Katkıda Bulunma

Katkılar, hata bildirimleri ve özellik önerileri her zaman memnuniyetle karşılanır — ancak bu projenin erken aşamada olduğunu ve hızla değiştiğini göz önünde bulundurun.

1. Depoyu fork'layın
2. Bir özellik dalı oluşturun (`git checkout -b feature/ozelligim`)
3. Değişikliklerinizi commit'leyin
4. Ne değiştirdiğinizi ve nedenini açıklayan bir pull request açın

## Lisans

Bu proje **GNU General Public License v3.0** lisansı ile lisanslanmıştır. Tam metin için [`LICENSE`](LICENSE) dosyasına bakınız.

## Sorumluluk Reddi

Bu araç, bağımsız olarak geliştirilmiş, **resmi olmayan ve geliştirme aşamasında** bir projedir; TÜBİTAK veya resmi Pardus projesi tarafından geliştirilmemekte, sürdürülmemekte veya onaylanmamaktadır. `main` dalına haber verilmeksizin force push yapılabilir ve geçmişi yeniden yazılabilir. Kendi sorumluluğunuzda kullanınız.

## Teşekkürler
- [Furkan Çolak](https://github.com/furkanclk3180) - Testler
- [topraklanbudev](https://github.com/Topraklanbudev) - Testler ve motivasyon
- [ilgilenmek](https://github.com/keenon63) - Motivasyon