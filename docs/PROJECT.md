# Aile Hikâyecisi — Proje Belgesi

Oct 13, 2026 · @Zeynep Sude

## Bu belge nasıl kullanılır

Bu belge projenin **tek doğru kaynağı.** Kod, veri tipi veya akış hakkında bir şüphe olduğunda cevap burada aranır; burada yoksa önce buraya yazılır, sonra kodlanır.

- **Değişiklik kuralı:** Bir karar değişirse ilgili bölüm güncellenir ve en alttaki *Karar günlüğü* tablosuna bir satır eklenir. Sohbette ya da mesajda verilen kararlar buraya taşınmadan geçerli sayılmaz.
- **İsimlendirme kuralı:** Belgede Türkçe kavramlar kullanılır, kodda ise İngilizce karşılıkları. Hangi kavramın hangi isimle yazılacağı *Kavramlar sözlüğü* bölümünde sabittir. Jüri kodu İngilizce okuyacak.
- **Kapsam etiketleri:** **Çekirdek** mutlaka yapılır. **Sonra** çekirdek bitince yapılır. **Zaman kalırsa** isteğe bağlıdır. **Vizyon** hackathon'da yapılmaz, sadece sunumda anılır.
- **Akışın görsel hali:** Adım adım senaryo simülasyonu ayrı bir sayfada duruyor ([Aile Hikâyecisi Akışı](https://claude.ai/artifact/Np4EXRHUGjsc2W3TbSNeLz)). İkisi çelişirse bu belge geçerlidir.
- **Teslim:** 23 Ekim 2026, 12:00 PDT, yani Türkiye saatiyle **22:00.** Hedefimiz 18:00'de göndermek.

## Proje özeti

**Teknolojiden uzak bir büyüğün sadece konuşarak hikâyelerini anlattığı; ailenin hem uzaktan sorularla hem de bir araya geldiğinde birlikte hatırlayarak katıldığı bir sesli aile hafızası.** Çalışma adı *Aile Hikâyecisi*; İngilizce ürün adı henüz seçilmedi (bkz. Açık kararlar).

**Problem**

- Büyüklerin hikâyeleri yazıya geçmeden kayboluyor. Telefonda anlatılan hikâye sadece dinleyenin aklında kalıyor.
- Hikâye bire bir anlatılıyor; geniş aile o hikâyeyi hiç duymuyor.
- Mevcut çözümler (Remento gibi) büyüğün telefon ve link kullanmasını gerektiriyor ve tek yönlü çalışıyor: soru gider, cevap gelir, kitap çıkar.
- Aile bir araya geldiğinde ortaya çıkan toplu hatırlama anları hiç kaydedilmiyor.

**Kullanıcılar**

- **Merkez kişi** (anneanne, dede): Sadece konuşur. Telefon veya ekran kullanmaz.
- **Aile üyeleri** (çocuklar, torunlar, kuzenler): Web panelinden soru sorar, dinler, tepki verir, kendi anısını kaydeder.
- **Yönetici** (bir aile üyesi): Kurulumu yapar, üye davet eder, hassas konuları belirler.

**Mevcut ürünlerden farkı**

|  | Remento | Alexa Podcasts | Telefon | Aile Hikâyecisi |
| --- | --- | --- | --- | --- |
| Büyük telefon kullanmak zorunda mı? | Evet | Yok | Evet | Hayır |
| Etkileşim | Soruya kayıt (monolog) | Yapay sunucular | Anlık konuşma | Takip sorulu sohbet |
| Sorular | Soru bankası ve aile soruları | Yok | Anlık | Aile soruları, takip ve boşluk soruları |
| Kim duyar? | Kitabı okuyan | Dinleyen | Sadece arayan | Bütün aile, erişim kurallarıyla |
| Toplu hatırlama | Yok | Yok | Yok | Buluşma modu |
| Kimin sesi? | Gerçek ses | Yapay ses | Gerçek ses | Gerçek ses |
| Kalıcı mı? | Evet (kitap) | Evet | Hayır | Evet (sürekli büyüyen arşiv) |

En önemli üç fark: **toplu hatırlama**, **tek yönlü değil döngü** (cevap soruyu sorana döner, aile tepki verir, yeni soru gelir) ve **ekransız sohbet.** Sunumda Remento açıkça anılacak: *Remento bu ihtiyacın gerçek olduğunu kanıtladı; biz bunu bir kitaptan ailenin birlikte yaşadığı bir sohbete dönüştürüyoruz.*

**Yarışma stratejisi**

- **Ana kategori: Alexa+.** Gerçek Alexa'ya bağlanılamıyor (araçları seçili partnerlere kapalı). Alexa'yı kendi web sayfamızda simüle ediyoruz; arka planda kendi MCP sunucumuz çalışıyor. Bu yol SSS'de açıkça kabul ediliyor.
- **Mini yarışma: AWS Builder.** Kurallar "tek başına yeterli" ifadesini sadece \*\*Kiro Crew\*\* için kullanıyor; düz Kiro IDE'nin tek başına sayılıp sayılmadığı net değil. Kesin yol: çalışma anında bir AWS servisi kullanmak (Amazon Polly ile seslendirme ve/veya Amazon Transcribe ile döküm) ve bunu README'de belgelemek. Kiro kullanımı bunun üstüne ek artı. Bedrock'a bağımlı olmayacağız (yeni hesaplarda kota sorunu var).
- **Sunum çerçevesi:** "Thanksgiving, bayram ve yılbaşı gibi aile buluşmaları için." Demo bayramla çekilir: *Bizim için bu bayram, sizin için Thanksgiving.*
- **Jüri kriterleri** (eşit ağırlık): teknik uygulama, tasarım, potansiyel etki, fikrin kalitesi. Friction log puana %10'a kadar bonus ekler.

## Kavramlar sözlüğü

Her kavramın tek bir anlamı ve koddaki tek bir adı var. "Anlatmak" ile "merkez kişi olmak" farklı şeylerdir: herkes hikâye anlatabilir, ama bir çemberin merkezi tek kişidir.

| Kavram | Koddaki adı | Anlamı |
| --- | --- | --- |
| Kişi | `Person` | Ailedeki herhangi biri. Herkesin kendi hayat çizgisi vardır. |
| Hayat çizgisi | `Lifeline` (saklanmaz, hesaplanır) | Bir kişinin hayatı **hakkında** anlatılan hikâyelerin dönemlere göre görünümü. Kimseye devredilmez. |
| Hayat dönemi | `LifePeriod` | Kesin yıl yerine kullanılan dönem: çocukluk, gençlik vb. Liste *Veri modeli*nde. |
| Aile çemberi | `Circle` | Bir merkez kişinin etrafındaki grup. Hackathon'da tek çember var. |
| Üyelik / rol | `Membership.role` | Kişinin bir çemberdeki görevi: `center`, `admin`, `member`. Rol kişiye değil çembere göre belirlenir. |
| Merkez kişi | `role = center` | Çemberin büyüğü. Cihazı var, davet alır, sorular ona yönelir, ajan onunla sesli sohbet eder. |
| Oturum | `Session` | Bir sohbet. Tekli (büyük + ajan) veya buluşma (büyük + aile). Aynı motor, farklı katılımcı sayısı. |
| Konuşma parçası | `Segment` | Oturumda tek kişinin kesintisiz konuştuğu bölüm; ses aralığı ve dökümüyle. |
| Hikâye | `Story` | Anlamlı bir anı birimi. Bir veya daha fazla ses parçasına dayanır. |
| Anlatım | `Story.kind = retelling` | Aynı hikâyenin başka bir zamanda ya da başka biri tarafından anlatılması. Ana hikâyeye bağlanır, onu değiştirmez. |
| Hakkında | `StorySubject` | Hikâyenin kimin hayatı hakkında olduğu; her kişi için ayrı dönemle. Hikâye bu kişilerin çizgilerine yerleşir. |
| Anlatan | `Story.teller_id` | Hikâyeyi kimin anlattığı. Hikâyenin hangi çizgide görüneceğini **belirlemez.** |
| Bağlantı | `StoryLink` | İki hikâye arasındaki ilişki (aynı yer, aynı olay, devamı). Ajan önerir, aile kaldırabilir. |
| Soru | `Question` | Merkez kişiye sorulmayı bekleyen soru. Kaynağı aile, takip veya boşluk olabilir. |
| Boşluk | (hesaplanır) | Merkez kişinin hiç hikâyesi olmayan hayat dönemi. |
| Davet | `Invitation` | Sohbet saatinde cihazın ışığının yanması. Hatırlatmadır, sohbetin tek kapısı değildir. |
| Erişim | `Story.access` | Hikâyeyi kimin görebileceği: `circle`, `selected`, `private`, `all_family`. |
| Hassas konu | `SensitiveTopic` | Yöneticinin belirlediği, büyüğe sorulmayacak konu. |
| Tepki | `Reaction` | Aile üyesinin hikâyeye bıraktığı emoji. Büyüğe sözle iletilir. |
| Buluşma modu | `Session.kind = gathering` | Aile bir aradayken telefonların mikrofon olduğu oturum. |

## Kullanıcı akışları

Ürünün kalbi bir döngü: aile soru bırakır, büyük anlatır, cevap soruyu sorana kendi sesiyle döner, aile tepki verir ve yeni sorular sorar. Aşağıdaki akışlar bu döngünün parçaları.

**A1. Büyük kendiliğinden anlatır** (Çekirdek)

1. Büyük istediği an "Alexa, aklıma bir şey geldi" der. Sohbet başlar.
2. Ajan dinler, kısa kalırsa takip sorusu sorar. Uygun bir an olursa bekleyen bir soruyu araya sokar.
3. Oturum biter; konuşma parçaları kaydedilir, ajan hikâyeleri ayıklar ve kaydeder (A6).

**A2. Davet** (Çekirdek)

1. Sohbet saatinde (ör. 10:00) cihazın ışığı yanar. Cihaz kendiliğinden konuşmaz.
2. Büyük "Alexa, ne var?" der. Ajan sebebiyle davet eder: "Elif'in size bir sorusu var, sohbet etmek ister misiniz?"
3. Önce bekleyen tepkiler sözle iletilir: "Elif şemsiye hikâyenize çok gülmüş."
4. Büyük "evet", "sonra" veya "bugün değil" der. Evet ise A1'in 2. adımından devam edilir.

**A3. Soru döngüsü** (Çekirdek)

1. Aile üyesi panelden soru yazar.
2. Soru hassas konu kontrolünden geçer. Takılırsa listeye girmez; soran kişiye nazik bir açıklama gider.
3. Soru bekleyen listeye girer. Sıra: aile soruları önce, sonra takip, sonra boşluk soruları.
4. Ajan soruyu sohbete kendi cümlesiyle, doğal bir anda yerleştirir.
5. Oturum sonunda ajan, sohbetin hangi aralığının bu soruya cevap olduğunu kelime zaman damgalarıyla bulur.
6. O ses aralığı, dökümü ve etiketli yapay zekâ özetiyle soran kişiye bildirim olarak gider. Altında: "Belki onu aramak istersin."

**A4. Aile üyesinin kendi anısı** (Çekirdek)

1. Aile üyesi panelden sesli kayıt yapar.
2. Ajan anlatanı ve hakkında olduğu kişileri ayrı ayrı belirler; her kişi için dönem tahmin eder.
3. Hikâye ilgili herkesin hayat çizgisine yerleşir. Mevcut kartlar yeniden sıralanmaz.
4. Ajan ilgili hikâyelere bağlantı önerir (aynı yer, aynı olay).

**A5. Tepkiler ve baştan dinleme** (Çekirdek)

- Aile üyesi hikâyeye ❤️ 😂 😢 🙏 bırakır. Sayaç gösterilmez. Tepkiler bir sonraki davette büyüğe sözle iletilir.
- Hikâye sayfasındaki **Baştan dinle** düğmesi, hikâyeyi ve doğrudan bağlı hikâyeleri sırayla çalar. Sıra yaşandığı döneme göredir. Kişinin erişemediği kayıtlar sessizce atlanır. Büyük aynı şeyi sesle ister: "Köydeki evle ilgili ne varsa dinlet."

**A6. Kayıt ve yapılandırma** (Çekirdek, her oturumdan sonra)

1. Ses kaydı saklanır (asla değişmez).
2. Döküm kelime zaman damgalarıyla çıkarılır.
3. Ajan hikâyeleri ayıklar: başlık, özet, anlatan, hakkında olanlar ve dönemleri, yer, varsa söylenen yıl.
4. "Bunu kimse duymasın" denen aralık gizli işaretlenir (üç katmanda).
5. Hikâye 24 saat bekleme durumunda başlar, sonra erişimine göre açılır.

**A7. Buluşma modu** (Sonra)

1. Ekranda bir QR kod belirir. Katılanlar okutur; telefonları kendi mikrofonları olur. Uzaktakiler de aynı yolla katılır.
2. Büyük odadaki cihazla konuşur, telefon kullanmaz.
3. Ajan bir fotoğraf ya da hikâye açar ve sorar: "Bu fotoğraf hangi yıl çekildi? Kim hatırlıyor?"
4. Her konuşma parçası konuşan kişiyle kaydedilir. Aynı olayın farklı anlatımları çelişse bile saklanır.

## Kurallar ve tasarım ilkeleri

Bu kurallar kodda zorunlu kontrollerdir; demo veya zaman baskısı yüzünden atlanmaz.

**Tasarım ilkeleri**

1. **Yapay zekâ büyüğü taklit etmez.** Onun yerine konuşmaz, sesini klonlamaz. Sadece gerçek sözlerini bulup getirir.
2. **Ses kaydı asıl kaynaktır.** Döküm ve özet ondan türer; çelişirse ses kaydı geçerlidir.
3. **Asla yeniden yazmaz, asla uydurmaz.** Söylenmemiş yılı tahmin etmez. Yapay zekânın ürettiği her şey "yapay zekâ özeti" veya "tahmini" etiketi taşır.
4. **Büyüğün kontrolü.** Neyin paylaşılacağına o karar verir; davetleri reddedebilir.
5. **İzleme aracı değildir.** Sağlık, ruh hali veya kullanım sıklığı hakkında aileye bildirim gitmez.

**Davet kuralları**

- Günde en fazla bir davet.
- Büyük o gün kendiliğinden konuştuysa davet atlanır.
- "Bugün değil" dendiğinde o gün ısrar edilmez. Reddedilen davetler aileye raporlanmaz.
- Davetin sebebi bekleyen en anlamlı şeydir: önce aile tepkileri, sonra aile soruları, sonra ajanın soruları.

**Erişim kuralları**

| Seviye | Kod değeri | Kim görür? | Kapsam |
| --- | --- | --- | --- |
| Bu çember (varsayılan) | `circle` | Hikâyenin çemberindeki herkes | Çekirdek |
| Gizli | `private` | Sadece anlatan | Çekirdek |
| Seçili kişiler | `selected` | Anlatanın seçtikleri | Sonra |
| Tüm ailem | `all_family` | Anlatanın tüm çemberleri | Vizyon |

- Erişimi **anlatan** belirler. Hakkında anlatılan kişi her zaman daraltabilir (gizleyebilir), genişletemez.
- Merkez kişi seviyeyi sesle seçer: "Bunu kimse duymasın" → `private`; "Bunu sadece Ayşe bilsin" → `selected`.
- Erişimi olmayan kişi gizli bir kaydın **varlığını bile görmez.** "Burada gizli kısım var" uyarısı sadece anlatana görünür.
- **Filtre LLM'den önce uygulanır.** Her MCP aracı, sonuçları ajana vermeden önce oturumdaki kişinin erişimine göre süzer. Böylece ajan sohbette gizli bir şeyi kazara söyleyemez.
- Bir sorunun cevabı soranın erişemeyeceği şekilde işaretlenirse cevap ona iletilmez.

**Yayın ve gizlilik**

- Yeni hikâye 24 saat `pending` durumunda bekler; bu sürede merkez kişi veya yönetici gizleyebilir. Sonra otomatik `published` olur.
- "Bunu kimse duymasın" denen aralık ses, döküm ve özette birlikte gizlenir.
- Yönetici bir kaydı gizleyebilir ama **değiştiremez.** Kalıcı silme sadece merkez kişinin isteğiyle olur.

**Tahminler ve düzeltmeler**

- Dönemler ve bağlantılar yapay zekâ tahminidir; arayüzde "tahmini" etiketiyle görünür.
- Aile tek tıkla düzeltir. Ailenin düzeltmesi tahminden önceliklidir ve yeniden hesaplamada ezilmez.
- Hayat çizgisi saklanmaz; her istekte hikâyelerden hesaplanır. Yeni bilgi eski kaydı bozmaz.
- Aynı hikâyenin farklı anlatımları çelişse bile saklanır; sistem hangisinin doğru olduğuna karar vermez.

**Hassas konular**

- Yönetici konu ekler (ör. "1977 trafik kazası").
- Aile sorusu eklenirken ve ajan soru seçerken kontrol edilir. Kontrol LLM ile anlamsal yapılır; şüphede soru sorulmaz.
- Takılan soru silinmez, `filtered` durumunda kalır.

## Kapsam

Çekirdek, buluşma modu olmadan da tek başına gösterilebilir bir ürün olmalı. Gönderimde ve videoda sadece gerçekten çalışan özellikler "var" diye anlatılır; geri kalanı "yol haritası" başlığı altında.

**Çekirdek** (mutlaka)

- Tek çember, üç rol (`center`, `admin`, `member`), aile kimliği
- Kendiliğinden başlayan ve davetle başlayan sesli oturum, oturumlar arası hafıza
- Takip soruları
- Üç katmanlı kayıt: ses, kelime zaman damgalı döküm, yapılandırılmış özet
- Aile sorusu ekleme, hassas konu kontrolü, sohbete yerleştirme
- Cevap eşleştirme ve ses parçasıyla soruyu sorana iletme
- Hayat dönemi tahmini ve ailenin düzeltmesi
- Boşluk tespiti ve boşluk soruları
- Aile üyesinin telefondan kendi anısını kaydetmesi
- Emoji tepkileri ve büyüğe sözle iletilmesi
- Bağlantı önerisi ve hikâye sayfasında **Baştan dinle**
- Erişim: `circle` ve `private`; LLM öncesi filtre; 24 saat bekleme
- Hikâye sayfası: ana oynatıcı, tıklanabilir döküm, diğer anlatımlar, bağlı hikâyeler
- Hayat çizgisi görünümü (basit liste/sütun hali yeterli)

**Sonra** (çekirdek bitince)

- Buluşma modu: QR ile telefonların mikrofon olması, uzaktan katılım, fotoğrafla soru
- Farklı anlatımların hikâye sayfasında yan yana gösterimi (veri modeli baştan destekler)
- `selected` erişim seviyesi

**Zaman kalırsa**

- Görsel, cilalı zaman çizelgesi ekranı
- Buluşma öncesi kişiye özel soru kartları
- Gelemeyenlere gerçek seslerden kısa özet
- Hikâyelere fotoğraf ekleme
- 10 saniyelik sesli tepki
- Çocuk modu (sadece "çocuklara uygun" işaretli gerçek ses parçaları)

**Vizyon** (yapılmaz, sunumda bir cümle)

- Birden fazla çember, kuşaktan kuşağa merkez kişi (veri modeli hazır)
- `all_family` erişimi
- Merkez kişi vefat ettiğinde çemberin hatıra arşivine dönüşmesi; gizli kısımların sonsuza kadar gizli kalması

**Bilerek çıkarılanlar**

| Fikir | Sebep |
| --- | --- |
| Fire TV uygulaması | İkinci platform ve yeni teknoloji; döngüye bir şey katmıyor |
| Animasyon / yapay video | Pahalı; uydurma görüntü gerçeklik ilkesine aykırı |
| Anı kitabı (PDF) | Remento'nun ana ürünü; bizi o karşılaştırmaya iter |
| Yapay sunuculu podcast | Amazon'un Alexa Podcasts özelliğiyle çakışıyor |
| Çelişki tespit edip büyüğe sorma | Teknik olarak ağır; anlatımlar sadece saklanıyor |
| Kesin yıl tahmini | Hataya açık; hayat dönemleri kullanılıyor |
| Ses klonlama, duygu analizi | Etik sorun ve güvenilmezlik |
| Otomatik soy ağacı, oyunlaştırma | Hata riski; aile ilişkisini ucuzlatır |
| Sağlık / ruh hali izleme | Ürünü izleme aracına çevirir |
| Herkese açık paylaşım | Aile ürünü; gereksiz mahremiyet riski |
| Ayrıntılı onay kuyruğu | Döngüyü durdurur; yerine 24 saat bekleme |

## Mimari ve teknoloji kararları

Sistem yedi parçadan oluşur; ajan backend içinde çalışan bir **MCP istemcisidir** ve tüm iş mantığına MCP sunucumuzun araçları üzerinden erişir. Bu, Alexa+'ın gerçekte nasıl çalıştığının (asistan + üçüncü taraf MCP sunucusu) birebir modeli; jüriye bunu böyle anlatacağız.

**Bileşenler**

| # | Bileşen | Görevi |
| --- | --- | --- |
| 1 | Web istemci: Cihaz ekranı | Echo Show / Fire TV'deki Alexa+'ı simüle eder. Büyük burada konuşur. |
| 2 | Web istemci: Aile paneli | Telefon genişliğinde. Soru, bildirim, hikâye sayfası, hayat çizgisi, kayıt, tepki. |
| 3 | Web istemci: Buluşma ekranı | QR, fotoğraf, çok konuşmacı (Sonra). |
| 4 | Backend API | Panelin REST uçları, cihaz oturumu, ses yükleme, ajan döngüsü (LLM + MCP istemcisi). |
| 5 | MCP sunucusu | Projenin beyni. Araçlar + erişim filtresi. Streamable HTTP, spec 2025-11-25. |
| 6 | Ses servisleri | Konuşmadan metne (kelime zaman damgalı) ve metinden konuşmaya. |
| 7 | Veri | Veritabanı + ses dosyaları. Arka plan işleri: davet zamanlayıcı, 24 saat yayınlama, oturum sonrası işleme. |

&#91;embedded content: bileşenler · iki ajan, bir MCP sunucusu\]

Web istemciler sadece backend ile konuşur; ajanlar veriye doğrudan değil, erişim filtresinden geçen MCP araçlarıyla ulaşır.

**Platform: tek bir web uygulaması, mobil uygulama yok**

- **Cihaz ekranı:** Bilgisayar veya tablet tarayıcısında açılır; Echo Show'u taklit eden yatay, büyük yazılı bir ekran.
- **Aile paneli:** Telefon tarayıcısına göre tasarlanmış (mobil öncelikli) web sayfaları. Uygulama mağazası gerekmez; isterseniz ana ekrana eklenebilir (PWA).
- **Buluşma ekranı:** Bilgisayar veya televizyona yansıtılmış tarayıcı; katılanlar telefon tarayıcısıyla QR'ı okutur.
- **Önemli:** Tarayıcılar mikrofona sadece güvenli bağlantıda (HTTPS) izin verir. Bilgisayarda `localhost` yeterli, ama telefonla bağlanmak için sunucu HTTPS ile erişilebilir olmalı (bir tünel servisi veya küçük bir bulut sunucusu). Hakemler için README'de yerel çalıştırma da anlatılır.

**Cihaz ekranında bir konuşma turu**

1. Büyük ekrandaki büyük düğmeye basıp konuşur (simülasyonda uyandırma kelimesi yerine *bas-konuş*; demoda daha güvenilir). Tarayıcı sesi kaydeder.
2. Ses backend'e yüklenir; konuşmadan metne çevrilir; parça (`Segment`) olarak saklanır.
3. Ajan, oturum bağlamı ve MCP araçlarıyla bir cevap üretir (ör. `get_pending_questions`).
4. Cevap metinden konuşmaya çevrilir ve ekranda çalınır. Ekranda ajanın yazısı ve ilgili kartlar da görünür.
5. Oturum kapanınca arka planda A6 (kayıt ve yapılandırma) çalışır.

**Önerilen teknolojiler** (ilk gün onaylanacak)

| Alan | Öneri | Not |
| --- | --- | --- |
| Backend + MCP | Python, FastAPI, resmi MCP Python SDK (FastMCP) | Profilimize uygun. SDK'nın 2025-11-25 spec sürümünü desteklediği **ilk gün doğrulanmalı.** |
| Web istemci | React + Vite (veya sade HTML/JS) | Bağımlılığı az tutun; 3 ekran. |
| LLM | Araç çağırmayı iyi yapan bir model API'si | Bedrock kota riski var; sağlayıcı ilk gün seçilir. |
| Konuşmadan metne | Amazon Transcribe veya Whisper (`word_timestamps`) | İngilizce ve kelime zaman damgası şart. İkisi de ilk gün 1 dakikalık İngilizce kayıtla denenir. |
| Metinden konuşmaya | Amazon Polly veya tarayıcı sesi | Polly, AWS Builder anlatımını da güçlendirir. |
| Veri | SQLite (+ yerel dosya), istenirse Postgres + S3 | Hackathon için SQLite yeterli. |
| Geliştirme aracı | Kiro | AWS Builder mini yarışması için; kullanım README'de belgelenir. |

**Repo düzeni** (öneri): `server/` (FastAPI + ajan), `mcp_server/` (araçlar, erişim filtresi), `web/` (üç ekran), `docs/` (mimari diyagram, friction log), kökte `README.md` ve `LICENSE`. Gizli anahtarlar `.env` içinde, `.gitignore`'da.

## Veri modeli

Aşağıdaki tipler backend, MCP sunucusu ve web istemcinin ortak sözleşmesi. Alan adı veya enum değeri değişecekse önce burası güncellenir. Tüm kimlikler UUID metni, tüm zamanlar UTC ISO 8601 metni, ses aralıkları milisaniye tamsayı.

**Enumlar**

```python
Role          = "center" | "admin" | "member"
CircleStatus  = "active" | "memorial"            # memorial = Vizyon
LifePeriod    = "childhood" | "youth" | "marriage_early_years"
              | "raising_children" | "midlife" | "retirement"
PeriodSource  = "ai" | "family"                  # family her zaman önceliklidir
SessionKind   = "solo" | "gathering"
SessionStart  = "invitation" | "spontaneous" | "panel_recording"
StoryKind     = "original" | "retelling"
StoryStatus   = "pending" | "published" | "hidden"
AccessType    = "circle" | "private" | "selected" | "all_family"
LinkReason    = "same_place" | "same_event" | "continuation" | "answer_to"
LinkSource    = "ai" | "family"
LinkStatus    = "suggested" | "confirmed" | "removed"
QuestionSource = "family" | "follow_up" | "gap"
QuestionStatus = "waiting" | "asked" | "answered" | "filtered"
InvitationStatus = "sent" | "accepted" | "postponed" | "declined" | "skipped"
Emoji         = "heart" | "laugh" | "sad" | "pray"
```

**Varlıklar**

```python
Person:
  id, name, birth_year: int | None, language: "tr" | "en", created_at

Circle:
  id, name, center_person_id, status: CircleStatus,
  chat_time: "HH:MM", timezone: str            # ör. "Europe/Istanbul"

Membership:                                     # PK (person_id, circle_id)
  person_id, circle_id, role: Role

Session:
  id, circle_id, kind: SessionKind, started_by: SessionStart,
  participant_ids: [person_id], audio_path, started_at, ended_at | None

Segment:                                        # tek kişinin kesintisiz konuşması
  id, session_id, speaker_id | None,            # None = ajan
  start_ms, end_ms, transcript,
  words: [{w, start_ms, end_ms}],
  is_private: bool

Story:
  id, circle_id, teller_id, kind: StoryKind,
  original_story_id | None,                     # kind = retelling ise ana hikâye
  title, ai_summary,                            # arayüzde "yapay zekâ özeti" etiketiyle
  sources: [{session_id, start_ms, end_ms}],    # ses aralıkları, gizli aralıklar hariç
  place | None,
  stated_year: int | None,                      # sadece anlatan açıkça söylediyse
  access: {type: AccessType, person_ids: [id]},
  status: StoryStatus, publish_at,              # created_at + 24 saat
  created_at

StorySubject:                                   # PK (story_id, person_id)
  story_id, person_id, period: LifePeriod,
  period_source: PeriodSource, corrected_by | None

StoryLink:
  id, from_story_id, to_story_id, reason: LinkReason,
  source: LinkSource, status: LinkStatus

Question:
  id, circle_id, target_person_id, asker_id | None,   # None = ajan
  text, source: QuestionSource, period: LifePeriod | None,
  status: QuestionStatus,
  answer: {story_id, session_id, start_ms, end_ms} | None,
  created_at

SensitiveTopic:
  id, circle_id, text, added_by, created_at

Reaction:                                       # PK (story_id, person_id, emoji)
  story_id, person_id, emoji: Emoji,
  delivered_to_center: bool, created_at

Invitation:
  id, circle_id, person_id, date: "YYYY-MM-DD",
  reason: str, status: InvitationStatus
```

**Hesaplanan görünümler** (saklanmaz)

- `lifeline(person_id, viewer_id)` → dönem başına, `viewer_id`'nin görebildiği hikâyeler. Dönem: `period_source = family` varsa o, yoksa `ai`.
- `gaps(person_id)` → `lifeline` içinde boş kalan dönemler (sadece merkez kişi için kullanılır).

**Erişim kontrolü** (tek fonksiyon; her araç ve her REST ucu bunu kullanır)

```python
def can_see(viewer_id, story) -> bool:
    if story.status == "hidden" and viewer_id != story.teller_id: return False
    if story.status == "pending" and role(viewer_id) not in ("center", "admin") \
       and viewer_id != story.teller_id: return False
    t = story.access.type
    if t == "private":  return viewer_id == story.teller_id
    if t == "selected": return viewer_id == story.teller_id or viewer_id in story.access.person_ids
    if t == "circle":   return is_member(viewer_id, story.circle_id)
    if t == "all_family": return shares_any_circle(viewer_id, story.teller_id)
    return False
```

Gizli `Segment`'ler (`is_private = true`) hiçbir hikâyenin `sources` alanına, hiçbir dökümün paylaşılan haline ve hiçbir LLM bağlamına girmez.

## MCP araçları ve web API sözleşmesi

İşler üç kanaldan yürür: **MCP araçlarını sadece ajan** çağırır, **REST uçlarını web istemci** çağırır, **arka plan işleri** zamanlayıcıyla çalışır. Aynı iş mantığı (ör. soru ekleme) bir servis fonksiyonunda yazılır, iki kanal da onu çağırır.

**Güvenlik kuralı:** Araçların hangi kişi adına çalıştığı (`viewer_id`, `circle_id`) LLM'in verdiği argümanlardan **alınmaz**; MCP oturumunun başlığından (backend'in açtığı bağlantı) okunur. LLM sadece içerik argümanlarını verir.

**MCP araçları** (ajan çağırır)

| Araç | Kim çağırır | Girdi | Çıktı | Not |
| --- | --- | --- | --- | --- |
| `get_session_context` | Sohbet ajanı | – | merkez kişi, davet nedeni, iletilmemiş tepkiler, son 3 oturumun özeti | Oturum başında bir kez; hafıza buradan gelir |
| `get_pending_questions` | Sohbet ajanı | `limit?` | sıralı soru listesi | Hassas konu ve erişim süzülmüş; sıra: aile → takip → boşluk |
| `mark_question_asked` | Sohbet ajanı | `question_id` | ok | Ajan soruyu sorduğunda |
| `add_question` | İki ajan | `text, source: follow_up\|gap, period?` | `question_id` | Hassas konu kontrolü burada da |
| `search_archive` | Sohbet ajanı | `query, person_id?, period?` | hikâye listesi (başlık, özet, ses aralığı) | "Dedem askerliği nerede yaptı?" |
| `get_linked_playlist` | Sohbet ajanı | `story_id` | sıralı ses aralıkları + anlatanlar | Baştan dinle; derinlik 1, yaşandığı döneme göre |
| `mark_private` | Sohbet ajanı | `start_ms, end_ms` | ok | "Bunu kimse duymasın" |
| `set_story_access` | Sohbet ajanı | `story_id, type, person_ids?` | ok | Sesle erişim seçimi |
| `mark_reactions_delivered` | Sohbet ajanı | `story_ids` | ok | Tepkiler söylendikten sonra |
| `get_session_transcript` | Arşivci ajan | `session_id` | gizli olmayan parçalar + kelime zamanları | İşlemenin girdisi |
| `save_story` | Arşivci ajan | `title, summary, teller_id, subjects: [{person_id, period}], sources, place?, stated_year?, original_story_id?` | `story_id` | `status = pending`, erişim varsayılan `circle` |
| `record_answer` | Arşivci ajan | `question_id, story_id, start_ms, end_ms` | ok | Soru `answered` olur, cevap iletimi tetiklenir |
| `link_stories` | Arşivci ajan | `from_story_id, to_story_id, reason` | `link_id` | `source = ai, status = suggested` |
| `find_gaps` | Arşivci ajan | `person_id` | boş dönemler | Sonra `add_question(source = gap)` |

**İki ajan, bir MCP sunucusu.** *Sohbet ajanı* büyükle canlı konuşur. *Arşivci ajan* oturum kapanınca arka planda çalışır ve şu sırayı izler:

1. `get_session_transcript` ile oturumu okur.
2. Hikâyeleri ayıklar; her biri için `save_story` (mevcut bir hikâyenin yeniden anlatımıysa `original_story_id` ile).
3. Sorulan her soru için cevap aralığını bulur; `record_answer`.
4. İlgili hikâyeler için `link_stories` (aynı yer, aynı olay, devamı).
5. `find_gaps` ve gerekirse `add_question(source = gap)`.

Cevap iletimi (bildirim) `record_answer`'ın yan etkisidir; ajan doğrudan bildirim göndermez.

**REST uçları** (web istemci çağırır; hepsi `can_see` ile süzer)

| Uç | Kim | Ne yapar |
| --- | --- | --- |
| `POST /api/device/turn` | Cihaz ekranı | Ses yükler; cevap metni + TTS sesi + gösterilecek kartlar döner |
| `POST /api/device/session/end` | Cihaz ekranı | Oturumu kapatır, işlemeyi başlatır |
| `GET /api/device/invitation` | Cihaz ekranı | Işık yansın mı? |
| `POST /api/questions` | Aile paneli | Aile sorusu ekler; filtrelenirse açıklama döner |
| `GET /api/feed` | Aile paneli | Bildirimler: cevaplar, yeni hikâyeler |
| `GET /api/lifeline/{person_id}` | Aile paneli | Hesaplanmış hayat çizgisi |
| `GET /api/stories/{id}` | Aile paneli | Hikâye sayfası: ses aralıkları, döküm, anlatımlar, bağlantılar |
| `GET /api/stories/{id}/playlist` | Aile paneli | Baştan dinle sırası |
| `POST /api/recordings` | Aile paneli | Aile üyesinin kendi anısı (tek kişilik `panel_recording` oturumu) |
| `POST /api/stories/{id}/reactions` | Aile paneli | Emoji ekler/kaldırır |
| `PATCH /api/stories/{id}/subjects/{person_id}` | Aile paneli | Dönem düzeltme (`period_source = family`) |
| `PATCH /api/stories/{id}` | Anlatan, yönetici | Erişim değiştirir veya gizler |
| `DELETE /api/links/{id}` | Aile paneli | Yanlış bağlantıyı kaldırır (`status = removed`) |
| `POST /api/admin/members`, `/sensitive-topics`, `PATCH /api/admin/circle` | Yönetici | Üye, hassas konu, sohbet saati |
| `GET /api/audio/{session_id}?start=&end=` | Herkes | Ses aralığını akıtır; erişim kontrolü burada da yapılır |

**Arka plan işleri**

- **Davet zamanlayıcı** (dakikada bir): sohbet saati geldiyse ve bugün oturum ya da davet yoksa `Invitation(status = sent)`.
- **Yayınlayıcı** (dakikada bir): `publish_at` geçen `pending` hikâyeleri `published` yapar ve bildirim üretir.
- **Boşluk denetimi** (yayından sonra): `gaps()` boş dönem bulursa `add_question(source = gap)`.

Demoda zaman ileri sarılabilmeli: bir **demo saati** (`DEMO_NOW` ayarı) davet ve 24 saat beklemeyi test etmeyi ve videoyu çekmeyi kolaylaştırır.

## Takvim ve iş bölümü

Çekirdek 18 Ekim akşamı donar; buluşma modu ancak o gün çekirdek eksiksizse başlar. 21 Ekim'den sonra yeni özellik yazılmaz, sadece belge, video ve gönderim.

**İş bölümü** (grubun diğer üyeleri iki tarafa da destek verir)

| Rol | Kim | Sorumluluk |
| --- | --- | --- |
| Kişi A: backend ve yapay zekâ | Zeynep Sude | FastAPI, MCP sunucusu ve araçlar, iki ajan, veri modeli, erişim filtresi, ses servisleri, arka plan işleri |
| Kişi B: web istemci ve deneyim | Aleyna | Cihaz ekranı, aile paneli, buluşma ekranı, ses kayıt ve oynatma, görsel tasarım, demo verisi |
| Ortak | İkiniz | Bu belge, kullanıcı görüşmeleri, uçtan uca test, README, friction log, video, gönderim |

İkinizin buluştuğu yer *Veri modeli* ve *REST uçları* bölümleri. B, A'yı beklemeden sahte (mock) verilerle çalışabilsin diye A ilk gün örnek JSON cevaplarını `docs/api-samples/` altına koyar.

**Günlük plan** (Türkiye saati)

**13 Ekim Salı · Kurulum ve doğrulama**

- [ ] Ortak: bu belgeyi okuyup itirazları karar günlüğüne yazmak; isim ve demo dili kararı
- [ ] Ortak: akşam 4-5 kişiyle kısa kullanıcı görüşmesi
- [ ] A: repo, lisans, FastAPI + MCP sunucusu "merhaba" aracı Streamable HTTP üzerinden; SDK'nın spec 2025-11-25 desteğini doğrulamak
- [ ] A: 1 dakikalık Türkçe kayıtla iki STT seçeneğini kelime zaman damgasıyla denemek; LLM sağlayıcısını seçip araç çağırma testi
- [ ] B: web iskeleti; cihaz ekranında bas-konuş kayıt ve ses çalma

**14 Ekim Çarşamba · İlk uçtan uca konuşma**

- [ ] A: veri modeli, veritabanı, `can_see`, demo ailesi tohum verisi (Fatma, Ayşe, Elif, Can)
- [ ] A: sohbet ajanı döngüsü; `get_session_context`, `get_pending_questions`, `mark_question_asked`
- [ ] B: cihaz ekranı ↔ `POST /api/device/turn`: konuş, cevabı duy

**15 Ekim Perşembe · Arşiv**

- [ ] A: arşivci ajan; `get_session_transcript`, `save_story`, dönem tahmini; TTS
- [ ] B: hayat çizgisi ve hikâye sayfası (önce sahte veriyle), ses aralığı oynatıcı

**16 Ekim Cuma · Soru döngüsü** (karar noktası)

- [ ] A: `add_question`, hassas konu kontrolü, `record_answer`, ses aralığı akıtma ucu
- [ ] B: soru formu, bildirim akışı, cevap kartı
- [ ] Ortak: **Döngü uçtan uca çalışıyor mu?** Elif soru sorar → Fatma cevaplar → Elif kendi sesiyle duyar. Çalışmıyorsa 17 Ekim'in tamamı buna.

**17 Ekim Cumartesi · Ritim ve aile katılımı**

- [ ] A: davet zamanlayıcı, yayınlayıcı, `DEMO_NOW`, `find_gaps`, `mark_private`, tepkilerin büyüğe iletilmesi
- [ ] B: panelden kendi anını kaydetme, emoji tepki, dönem düzeltme, bağlantı kaldırma, Baştan dinle

**18 Ekim Pazar · Çekirdek donar** (karar noktası)

- [ ] Ortak: çekirdek listesinin tamamını uçtan uca test; hata düzeltme
- [ ] Ortak: **Buluşma moduna geçilsin mi?** Sadece çekirdek eksiksizse evet.

**19 Ekim Pazartesi · Buluşma modu veya cila**

- [ ] A + B: QR ile telefon bağlama, konuşmacı başına kayıt, fotoğrafla soru (ya da çekirdeği cilalamak)
- [ ] Ortak: 19:00 Amazon ofis saati; soruları önceden yazın

**20 Ekim Salı · Demo verisi**

- [ ] Ortak: gerçek anlatıcıyla demo kayıtları; demo ailesinin arşivini doldurmak
- [ ] Buluşma modu bitirme ya da kesip çıkarma kararı

**21 Ekim Çarşamba · Belgeler** (akşam kod donar)

- [ ] README (kurulum, çalıştırma, mimari diyagram, Kiro kullanımı), `LICENSE`
- [ ] Friction log ve ürün geri bildirimi metinleri
- [ ] Video senaryosu provası

**22 Ekim Perşembe · Video**

- [ ] Çekim, kurgu, İngilizce altyazı; YouTube'a herkese açık yükleme

**23 Ekim Cuma · Gönderim**

- [ ] Devpost formu; kontrol listesinin tamamı; **18:00'de gönder** (son saat 22:00)

**Sürekli:** Bir araçta 30 dakikadan fazla takılınca 3 satırlık friction log notu düşün (ne denendi, ne bekleniyordu, ne oldu, çözüm). Bu notlar %10 bonusun kaynağı.

## Demo videosu senaryosu

Video bir eğitim değil, bir sunum: ilk 20 saniyede problem, ilk dakikada çalışan döngü. Jüri 3 dakikadan sonrasını izlemek zorunda değil.

| Zaman | Sahne | Ekranda | Mesaj |
| --- | --- | --- | --- |
| 0:00–0:20 | Problem | Gerçek bir büyük, eski bir fotoğraf | "Her aile büyüklerinin hikâyelerini kaybediyor. Bir telefon konuşmasında anlatılan hikâye sadece dinleyende kalıyor." |
| 0:20–0:35 | Ürün | Cihaz ekranı + aile paneli yan yana | Tek cümlelik tanım. Alexa+ araçları partnerlere kapalı olduğu için Alexa'yı simüle ettiğimizi, MCP sunucusunun gerçek olduğunu açıkça söylemek. |
| 0:35–1:20 | Döngü | Elif soru yazar → sabah ışık yanar → "Alexa, ne var?" → ajan soruyu sorar → büyük anlatır → Elif'in telefonuna büyüğün kendi sesi gelir → Elif büyüğünü arar | Ürünün kalbi. Cevabın **gerçek sesle** döndüğü an ve aramaya teşvik eden satır net görünmeli. |
| 1:20–1:45 | Aile katılır | Elif kendi anısını kaydeder → iki hayat çizgisine yerleşir, boşluk dolar → ertesi gün büyüğe "Elif hikâyenize gülmüş" denir | Tek yönlü değil, döngü. |
| 1:45–2:20 | Buluşma | Bayram sofrası, QR, uzaktaki kuzen bağlanır, fotoğraf, iki farklı anlatım | Toplu hatırlama. Yetişmezse yerine: Baştan dinle + "bunu kimse duymasın" + hassas konu filtresi. |
| 2:20–2:45 | Altyapı | MCP araç çağrıları paneli, mimari diyagram | İki ajan, bir MCP sunucusu; erişim filtresi LLM'den önce; geliştirmede Kiro. |
| 2:45–3:00 | Vizyon ve kapanış | Aile fotoğrafı | "Bizim için bayram, sizin için Thanksgiving." Ürün kuşaktan kuşağa devam eder. |

**Çekim kuralları**

- Bütün konuşmalar ve anlatım İngilizce. Anlatıcının sesi yapay olarak üretilirse videoda bir kez yazılı olarak belirtilir: "Demo voice is synthesized; in the product, families hear their elder's real voice."
- Telifli müzik ve izinsiz üçüncü taraf markası yok. Amazon logolarını veya Echo görüntülerini kullanmadan önce kurallara tekrar bakılır.
- Simülasyon olduğu ekranda bir kez yazılı olarak belirtilir.
- Demo saati (`DEMO_NOW`) ile 24 saat bekleme ve sabah daveti saniyeler içinde gösterilir; video bunu "ertesi sabah" geçişiyle verir.
- Görünen her özellik gerçekten çalışan koddan çekilir; maket ekran gösterilmez.

## Gönderim kontrol listesi

Kuralların istediği her şey burada; 23 Ekim'de tek tek işaretlenir. Kaynak: [resmi kurallar](https://amazonappdev2026.devpost.com/rules) ve [SSS](https://amazonappdev2026.devpost.com/details/faqs).

**Kod deposu**

- [ ] GitHub'da (GitLab kabul edilmiyor)
- [ ] Açık depo + üst kısımda görünen açık kaynak lisansı **veya** özel depo + işbirlikçiler: chris-trag, knmeiss, giolaq, anishamalde, mosesroth, emersonsklar ve Devpost adresi (davetler 7 günde düşer; gönderimden hemen önce ekleyin)
- [ ] Kurulum ve çalıştırma talimatları eksiksiz; temiz bir makinede denendi
- [ ] MCP sunucusu kodda gerçekten içe aktarılıp çağrılıyor (README'de anılması yetmez); spec 2025-11-25, Streamable HTTP
- [ ] API anahtarları kodda yok; `.env` `.gitignore`'da
- [ ] Mimari diyagram README'de

* [ ] Türkçe `docs/PROJECT.md` depodan çıkarıldı; yerine İngilizce `README.md` ve `docs/ARCHITECTURE.md` (kurallar tüm dokümantasyonu İngilizce istiyor)
* [ ] Depodaki tek kural dosyası `.kiro/steering/evoca-rules.md` İngilizce ve yeni dokümana işaret ediyor

**Video**

- [ ] 3 dakikadan kısa, YouTube veya Vimeo'da herkese açık
- [ ] Ürün simülasyonda çalışırken gösteriliyor
- [ ] İngilizce (veya İngilizce altyazılı); telifli müzik ve izinsiz marka yok

**Devpost formu**

- [ ] Akılda kalan bir isim ve İngilizce metin açıklaması: problem, kimin için, nasıl çalışır, Alexa+/MCP'yi nasıl kullanır
- [ ] Built With: MCP, Alexa+ (simüle), Kiro, kullanılan AWS servisleri
- [ ] Ana kategori: **Alexa+**
- [ ] Mini yarışma: **AWS Builder** (Kiro ve kullanılan AWS servisleri ürün geri bildirimi cevabında anlatılır)
- [ ] Her araç/SDK için ürün geri bildirimi: ne için kullanıldı, ne iyi çalıştı, ne geliştirilmeli, sıfırdan "merhaba dünya"ya geçiş nasıldı, tekrar kullanır mıydınız ve neden
- [ ] Friction log girdileri: denenen görev, adımlar, beklenen ve gerçekleşen, önem, geçici çözüm, öneri (%10 bonus)
- [ ] İsteğe bağlı özellik istekleri: ne, neden önemli, öncelik
- [ ] Bu proje yarışma süresi içinde sıfırdan yapıldı (önceki proje güncelleme açıklaması gerekmez)
- [ ] Test: Hakemler sistemi kendi makinelerinde çalıştırabilir; gerekiyorsa demo hesap bilgileri test talimatlarında

## Açık kararlar ve riskler

Kalan üç karar (ürün adı, LLM, konuşmadan metne servisi) 13 Ekim akşamına kadar verilmeli; her biri verildiğinde karar günlüğüne yazılır.

**Açık kararlar**

| Karar | Durum | Son tarih |
| --- | --- | --- |
| İngilizce ürün adı | Aday: *Evoca*. Alt başlıkta "Echo" kelimesi olmamalı (Amazon markası) | 13 Ekim |
| Demo dili | **Karar verildi:** her şey İngilizce | – |
| Demo anlatıcısı | Ertelendi. Seçenekler: gerçek bir büyük, bir oyuncu, açıkça etiketlenmiş yapay ses | 18 Ekim |
| LLM sağlayıcısı | Araç çağırma testi sonucuna göre | 13 Ekim |
| Konuşmadan metne servisi | İngilizce + kelime zaman damgası testine göre | 13 Ekim |
| Kim A, kim B? | **Karar verildi:** A Zeynep Sude, B Aleyna | – |
| Buluşma modu yapılsın mı? | **Karar verildi:** çekirdek eksiksizse evet; kontrol 18 Ekim | 18 Ekim |

**Riskler**

| Risk | Etkisi | Önlem |
| --- | --- | --- |
| "Bu sadece LLM sohbeti" eleştirisi | Fikir ve teknik puanı düşer | İki ajan ve 14 araçlı MCP sunucusu; boşluk tespiti; videoda araç çağrıları paneli |
| "Neden telefon etmiyorum?" itirazı | Etki puanı düşer | Bire çok paylaşım, kalıcılık, toplu hatırlama, aramaya teşvik eden bildirim; görüşmelerden alıntılar |
| MCP SDK spec 2025-11-25'i desteklemiyor | İlk eleme riski | İlk gün doğrulama; gerekirse SDK sürümü veya elle uyumluluk |
| Yaşlı konuşmasında tanıma hatası | Döküm ve eşleştirme bozulur | Ses asıl kaynak; döküm düzeltilebilir; demo kayıtları önceden denenir |
| Cevap eşleştirmede yanlış aralık | Torun yanlış parçayı duyar | Eşleştirmeye birkaç saniye pay; demo öncesi elle kontrol |
| LLM'in gizli içeriği sızdırması | Güven kaybı | Filtre LLM'den önce; gizli parçalar bağlama hiç girmez |
| Yeni AWS hesabında kota veya kredi sorunu | Servis çalışmaz | Bedrock'a bağımlı değiliz; AWS Builder için Polly/Transcribe + Kiro |
| Alexa'nın Türkçe desteklememesi | Jüri sorusu | Ürün ve demo İngilizce; risk kalktı |
| Zaman | Çekirdek yetişmez | Karar noktaları (16 ve 18 Ekim); buluşma modu kesilebilir |

**Ürün olarak çözülmemiş soru:** Çoklu çemberde bir kişi hakkındaki hikâyeyi, o kişinin farklı çemberlerindeki akrabaları görebilmeli mi? Hackathon kapsamında değil; erişim modeli ileride buna göre genişletilecek.

## Karar günlüğü

Yeni kararlar tablonun en üstüne eklenir. Bir karar geri alınırsa satır silinmez; yeni bir satır eklenir.

| Tarih | Karar | Gerekçe |
| --- | --- | --- |
| 13 Ekim | Geliştirme ortamı: Kiro (ana), bu sohbet planlama ve belge için; AWS Builder için çalışma anında Polly/Transcribe | Kurallar "tek başına yeterli" ifadesini sadece Kiro Crew için kullanıyor |
| 13 Ekim | Platform: tek web uygulaması; aile paneli mobil öncelikli, native uygulama yok | Kapsam; telefonda tarayıcı yeterli |
| 13 Ekim | Ürün ve demo tamamen İngilizce | Alexa Türkçe desteklemiyor; yarışma İngilizce |
| 13 Ekim | Rol dağılımı: A Zeynep Sude, B Aleyna; grup iki tarafa destek | Profil uyumu |
| 13 Ekim | Buluşma modu: çekirdek eksiksizse evet (kontrol 18 Ekim) | Güvenlik ağı |
| 13 Ekim | Demo anlatıcısı kararı 18 Ekim'e ertelendi | Önce çekirdek |
| 13 Ekim | Geliştirmeye geçildi; bu belge tek kaynak | Fikir yeterince netleşti |
| 13 Ekim | Oturum sonrası işleme de MCP araçlarıyla (arşivci ajan) | Jürinin "MCP gerçek iş yapıyor mu?" sorusu |
| 13 Ekim | Erişim: `circle`, `private` çekirdek; `selected` sonra; `all_family` vizyon | Kontrol anlatanda, kapsam küçük |
| 13 Ekim | Erişim filtresi LLM'den önce | Ajanın gizli içeriği sızdırmaması |
| 13 Ekim | Rol kişiye değil (kişi, çember) ikilisine bağlı; hackathon'da tek çember | Kuşaklar arası devir vizyonuna hazırlık |
| 12 Ekim | Herkes kendi anısını kaydedebilir; emoji tepkiler büyüğe sözle iletilir | Döngüyü tamamlıyor; ek maliyeti düşük |
| 12 Ekim | Büyük istediği an anlatabilir; davet sadece hatırlatma | Gerçek Alexa kullanımına uygun |
| 12 Ekim | Baştan dinle: doğrudan bağlılar, kronolojik, gizliler atlanır | Gerçek seslerle podcast benzeri deneyim |
| 12 Ekim | Hayat çizgisi hesaplanır; kesin yıl yerine hayat dönemleri; anlatımlar saklanır | Sonradan gelen bilgiyle bozulmaması |
| 12 Ekim | Üç katmanlı kayıt; ses asıl kaynak | Uydurmama ve güven ilkesi |
| 12 Ekim | Tek oturum motoru, iki ritim (günlük + buluşma) | Kullanım sıklığı ve özgünlük birlikte |
| 12 Ekim | Fire TV, animasyon, PDF kitap, yapay podcast çıkarıldı | Kapsam ve Amazon ürünleriyle çakışma |
| 12 Ekim | Fikir: Aile Hikâyecisi, kategori Alexa+, mini yarışma AWS Builder | Profil uyumu, Ring simülatör riski |
