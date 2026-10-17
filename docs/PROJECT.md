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
| Hassas konu | `SensitiveTopic` | Yöneticinin belirlediği (`source = family`) ya da büyüğün kendisinin reddettiği (`source = speaker`), büyüğe sorulmayacak konu. |
| Tepki | `Reaction` | Aile üyesinin hikâyeye bıraktığı emoji. Büyüğe sözle iletilir. |
| Fotoğraf | `StoryPhoto` | Aile üyesinin hikâyeye eklediği eski fotoğraf; hikâye başına bir tane. Ajanlar görmez. |
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

Notlar: Kayıt `POST /api/recordings` ile gelir (ses + isteğe bağlı erişim `circle` | `private`, varsayılan `circle`); çemberin her üyesi, merkez kişi dahil, kayıt yapabilir. En fazla 3 dakika; daha uzun veya boş ses 400 döner. Tek kişilik bir `panel_recording` oturumu açılır, ses cihaz oturumları gibi saklanır, oturum kapanır ve uç hemen 202 döner; döküm (tek parça, `speaker_id` = kaydeden, kelime zamanlarıyla) ve arşivci arka planda çalışır. Anlatan her zaman kaydedendir (kod zorlar); hakkında olanlar çemberin herhangi bir üyesi olabilir ("Babaannem bana ekmek yapmayı öğretti" → merkez kişi). Hikâye istenen erişimle ve `pending` başlar. Panel kaydından soru, cevap veya ret çıkmaz (Karar günlüğü 17 Ekim). Hatalar günlüğe sadece oturum kimliğiyle yazılır, döküm metni asla.

**A5. Tepkiler ve baştan dinleme** (Çekirdek)

- Aile üyesi hikâyeye ❤️ 😂 😢 🙏 bırakır. Sayaç gösterilmez. Tepkiler bir sonraki davette büyüğe sözle iletilir.
- Hikâye sayfasındaki **Baştan dinle** düğmesi, hikâyeyi ve doğrudan bağlı hikâyeleri sırayla çalar. Sıra yaşandığı döneme göredir. Kişinin erişemediği kayıtlar sessizce atlanır. Büyük aynı şeyi sesle ister: "Köydeki evle ilgili ne varsa dinlet." Ajan hikâyeyi `search_archive` ile bulur, `get_linked_playlist`'i çağırır ve çalınacakları tek kısa cümleyle tanıtır (sadece başlık ve anlatan, içeriği anlatmaz). Cihaz önce cevabı, sonra `playlist` kartındaki öğeleri sırayla çalar. Ajan istenmeyen hikâyeyi çalmayı önermez.

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
- Büyük bir konuyu kendiliğinden açıkça reddederse ("Bugün Hatice hakkında konuşmak istemiyorum"; bir sorunun reddi değil), arşivci onu `source = speaker` hassas konu olarak kaydeder (`add_refused_topic`). Ret kalıcıdır, "bugün" dense bile. Büyüğün reddettiği konular **hiçbir panel ucunda, yönetici dahil, dönmez**; ileride eklenecek yönetici konu listesi ucu sadece `source = family` döner.
- Aile sorusu sadece büyüğün reddettiği bir konuya takılırsa `filtered` olarak saklanır ama soran kişiye normal kabul cevabı (`waiting`) döner; aile konusuna takılırsa genel süzme mesajı döner. Böylece büyüğün reddi, `declined` soru gibi, merkez kişi dışındakilere cevaplanmamış görünür.
- Sohbet ajanı iki kaynaktaki konuları da `get_session_context` içinde `avoid_topics` olarak (sadece izleyen merkez kişiyse), kaynak etiketi olmadan alır ve hiçbirini kendisi açmaz; büyük kendisi açarsa sıcakça dinler ama hakkında soru sormaz.
- Aile sorusu eklenirken ve ajan soru seçerken kontrol edilir. Kontrol LLM ile anlamsal yapılır; şüphede soru sorulmaz.
- Takılan soru silinmez, `filtered` durumunda kalır.
- Büyük bir soruyu cevaplamayı reddederse soru `declined` olur ve bir daha sorulmaz. Soran kişi bunu **hiçbir zaman öğrenmez:** merkez kişi dışında herkese her API cevabında `declined` soru cevaplanmamış (`waiting`/`asked`) gibi görünür; reddetmek hassas bir konuya işaret edebilir (filtrelenen soru mesajıyla aynı ilke). Şu an soru durumunu dönen bir REST ucu yok; aile panelinin soru listesi ve bildirim akışı bu kurala uyar.

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

**Kalite ekleri** (çekirdeğin parçası; jüriye kanıt olarak gösterilir)

- **Gizlilik sızıntı testi:** LLM'e giden her istek testte yakalanır; gizli (`is_private`) hiçbir parçanın metni içinde olmamalı. README'de iddia değil, kanıt.
- **Araç çağrısı izi:** Her turda ajanın çağırdığı araç, girdisi, kısa sonucu ve süresi döner; cihaz ekranının yanında panel olarak gösterilir.
- **Gecikme ölçümü:** Her turda konuşmadan metne, LLM, araçlar ve metinden konuşmaya süreleri ayrı ayrı kaydedilir; README'de gerçek rakamlar.

**Sonra** (çekirdek bitince)

- Buluşma modu: QR ile telefonların mikrofon olması, uzaktan katılım, fotoğrafla soru
- Farklı anlatımların hikâye sayfasında yan yana gösterimi (veri modeli baştan destekler)
- `selected` erişim seviyesi
- Kişisel davet linkiyle kimlik (her aile üyesine kendi linki); hackathonda şifresiz kişi seçici ve `X-Person-Id` başlığı kullanılır

**Zaman kalırsa**

- Görsel, cilalı zaman çizelgesi ekranı
- Buluşma öncesi kişiye özel soru kartları
- Gelemeyenlere gerçek seslerden kısa özet
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
| 5 | MCP sunucusu | Projenin beyni. Araçlar + erişim filtresi. Streamable HTTP; protokol 2026-07-28 (2025-11-25 istemcileri de desteklenir). |
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
| Backend + MCP | Python, FastAPI, resmi MCP Python SDK v2 (\`mcp\` 2.3.0, sınıf adı \`MCPServer\`; eski adı FastMCP) | Profilimize uygun. 13 Ekim'de kontrol edildi: v2, 2026-07-28 revizyonunu uygular ve 2025-11-25 istemcilerine de hizmet verir. İlk testte negotiated sürüm **2026-07-28 çıktı, doğrulandı.** |
| Web istemci | React + Vite (veya sade HTML/JS) | Bağımlılığı az tutun; 3 ekran. |
| LLM | Amazon Bedrock, Converse API. İki ajan da şimdilik Nova 2 Lite; arşivci için aday Claude Haiku 4.5 | 13 Ekim testinde üç model de araç çağırdı; Nova 2 Lite en hızlısı (1,4 sn). Claude'un krediden düştüğü teyit edilene kadar Nova. Bölge us-east-1, us. profilleri. |
| Konuşmadan metne | faster-whisper small.en, yerel CPU (`word_timestamps`) | İngilizce ve kelime zaman damgası şart. Transcribe ücretsiz planda kapalı. Testte 73 sn ses 25 sn sürdü; aile isimleri ipucu olarak verilince isimler doğru. Ayrıntı: docs/spike-results.md |
| Metinden konuşmaya | Şimdilik Amazon Polly standard (eu-north-1); aday: Polly neural veya tarayıcı sesi | Ücretsiz planda proje bölgesi Stockholm; orada sadece robotik standard ses var. Demo öncesi Edge Natural sesler veya ücretli plan değerlendirilir. Kodda tek bir speak() fonksiyonunun arkasında. |
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
QuestionStatus = "waiting" | "asked" | "answered" | "filtered" | "declined"
                                                 # declined = büyük cevaplamayı reddetti; bir daha sorulmaz
TopicSource   = "family" | "speaker"            # speaker = büyük konuyu kendisi reddetti; panelde hiç görünmez
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
  person_id, circle_id, role: Role,
  relation_to_center: str | None                # ör. "daughter", "granddaughter"; yönetici girer,
                                                # yapay zekâ tahmin etmez; merkez kişide boş

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

StoryPhoto:                                     # hikâye başına bir tane; yenisi eskisinin yerine geçer (dosya silinir)
  id, story_id, path,                           # path = data/photos/<uuid>.jpg, kullanıcı adı asla
  caption | None,                               # en fazla 120 karakter
  uploaded_by, created_at

StoryLink:
  id, from_story_id, to_story_id, reason: LinkReason,
  source: LinkSource, status: LinkStatus

Question:
  id, circle_id, target_person_id, asker_id | None,   # None = ajan
  text, source: QuestionSource, period: LifePeriod | None,
  status: QuestionStatus,                       # waiting → asked (sohbet ajanı) → answered | declined
                                                # | waiting (arşivci: sorulup cevaplanmayan soru tekrar beklemeye döner)
                                                # merkez kişi dışındakilere declined, cevaplanmamış gibi görünür
  answer: {story_id, session_id, start_ms, end_ms} | None,
  created_at

SensitiveTopic:
  id, circle_id, text, source: TopicSource,     # varsayılan family
  added_by, created_at                          # source = speaker ise added_by = merkez kişi

Reaction:                                       # PK (story_id, person_id, emoji)
  story_id, person_id, emoji: Emoji,
  delivered_to_center: bool, created_at

Invitation:                                     # (circle_id, date) tekil: çember başına günde bir davet
  id, circle_id, person_id, date: "YYYY-MM-DD",  # date çemberin saat dilimindeki yerel gün
  reason: str, status: InvitationStatus
```

**Hesaplanan görünümler** (saklanmaz)

- `lifeline(person_id, viewer_id)` → dönem başına, `viewer_id`'nin görebildiği hikâyeler. Dönem: `period_source = family` varsa o, yoksa `ai`.
  Her dönem `years: {from, to}` taşır: kişinin `birth_year`'ından sabit yaş aralıklarıyla hesaplanır (childhood 0-12, youth 13-22,
  marriage_early_years 23-30, raising_children 31-45, midlife 46-60, retirement 61+). `to` açık uçta (retirement) ve bu yıldan
  sonraysa `null`; `birth_year` bilinmiyorsa `years` `null`.
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
| `get_session_context` | Sohbet ajanı | – | merkez kişi, davet nedeni, iletilmemiş tepkiler, son 3 oturumun özeti, `avoid_topics` | Oturum başında bir kez; hafıza buradan gelir. `avoid_topics`: çemberin tüm hassas konularının metni (iki kaynak, kaynak etiketi yok), sadece izleyen merkez kişiyse; başkasına `[]`. Ajan bunları hiç açmaz |
| `get_pending_questions` | Sohbet ajanı | `limit?` | sıralı soru listesi | Hassas konu ve erişim süzülmüş; sıra: aile → takip → boşluk |
| `mark_question_asked` | Sohbet ajanı | `question_id` | ok | Ajan soruyu sorduğunda |
| `add_question` | İki ajan | `text, source: follow_up\|gap, period?` | `question_id` | Hassas konu kontrolü burada da. `gap` sorusu `period` ister; o dönem için bekleyen bir `gap` sorusu varsa reddedilir |
| `search_archive` | Sohbet ajanı, arşivci ajan | `query, person_id?, period?` | hikâye listesi (başlık, özet, ses aralığı) | "Dedem askerliği nerede yaptı?" Anahtar kelimeyle, `can_see` süzülmüş, en fazla 5; döküm metni dönmez. Arşivci bağlantı ve yeniden anlatım adayı bulmak için kullanır; oturumun anlatanı adına çalışır (cihaz oturumunda merkez kişi, panel kaydında kaydeden), yani sadece onun görebildiği hikâyeleri görür. Arşivcinin kodu bunu daha da daraltır: modele sadece `circle` erişimli ve yayınlanmış (ya da anlatanın kendi bekleyen) hikâyeler gider, ses aralıkları, anlatan, erişim ve durum çıkarılarak; yeni bir aile hikâyesi gizli ya da bekleyen bir hikâyenin sözlerini tekrarlamasın, sesine işaret etmesin |
| `get_linked_playlist` | Sohbet ajanı | `story_id` | hikâye başına bir öğe: `story_id`, `title`, `teller` (ad), `period`; ses aralığı yok | Sesle baştan dinle; `build_playlist` merkez kişi adına çalışır (derinlik 1, yaşandığı döneme göre, gizli parçalar kesilir, görülemeyen bağlı hikâye iz bırakmaz). Görülemeyen hikâye olmayanla aynı hatayı alır. Cihaz turu `playlist` kartının ses aralıklarını sunucuda aynı servisle yeniden kurar |
| `mark_private` | Sohbet ajanının kodu (model değil) | `start_ms, end_ms`; oturum `X-Evoca-Session-Id` başlığından | ok | "Bunu kimse duymasın". Model milisaniye vermez: yerel `keep_private(scope)` aracını çağırır (`this_turn`, `previous_turn`, `next`), kod bunu tam parça sınırlarına çevirir; ajanın o turlara verdiği cevaplar da gizlenir |
| `set_story_access` | Sohbet ajanı | `story_id, type` | ok | Sesle erişim seçimi; sadece anlatan; şimdilik `private` ve `circle` (`selected` sonra) |
| `mark_reactions_delivered` | Sohbet ajanının kodu (model değil) | `story_ids` | ok | Cevapta o hikâyeye tepki veren herkesin adı geçtiyse; tepki bir sonraki oturumda tekrar söylenmez |
| `get_session_transcript` | Arşivci ajan | `session_id` | gizli olmayan parçalar + kelime zamanları | İşlemenin girdisi |
| `save_story` | Arşivci ajan | `title, summary, teller_id, subjects: [{person_id, period}], sources, place?, stated_year?, original_story_id?` | `story_id` | `status = pending`, erişim varsayılan `circle`. Bağlantı `X-Evoca-Session-Id` taşıyorsa her kaynak o oturumdan olmalı (arşivcinin kodu da her modda kontrol eder); `original_story_id` izleyenin görebildiği bir hikâye olmalı |
| `record_answer` | Arşivci ajan | `question_id, story_id, start_ms, end_ms` | ok | Soru `answered` olur, cevap iletimi tetiklenir. Soru `asked` olmalı; tek istisna hiç sorulmamış, bekleyen (`waiting`) bir aile (`family`) sorusu: büyük onu kendiliğinden cevapladıysa (takip ve boşluk soruları için yine `asked` şart). Arşivcinin kodu `story_id`'nin bu çalışmada kaydedilen bir hikâye olmasını ister. Ajan önce sıcaklık 0 bir kontrolle konuşmacının o aralıktaki sözlerinin soruyu gerçekten cevapladığını doğrular; emin değilse kaydetmez |
| `mark_question_declined` | Arşivci ajan | `question_id, session_id, start_ms, end_ms` | ok | Büyük açıkça reddettiyse soru `declined` olur; aynı kontrolle doğrulanır, emin değilse reddedilmiş sayılmaz |
| `add_refused_topic` | Arşivci ajan | `text, start_ms, end_ms`; oturum `X-Evoca-Session-Id` başlığından | `{topic_id, added}` | Büyük bir konuyu kendiliğinden açıkça reddettiyse `SensitiveTopic(source = speaker, added_by = merkez kişi)`; aynı metin ikinci kez eklenmez; `text` konunun kendisini adlandırır (ör. "Hatice", "kız kardeşi Hatice" değil, yoksa her "sister" sorusu süzülür) ve eşleşecek anlamlı kelimesi yoksa reddedilir. Aralık kuralları: arşivlenen oturum, sadece merkez kişinin kendi sözleri (buluşmada başka birinin reddi sayılmaz), gizli parçayla çakışma yok; geçmeyen aralık kontrole hiç gitmez. Sıcaklık 0 kontrol konuşmacının o aralıktaki sözlerinden "evet" demezse (hayır, emin değil, boş, hata) eklenmez. Panel kaydında sunulmaz |
| `reopen_question` | Arşivci ajanın kodu (model değil) | `question_id` | ok | Oturum sonunda sorulup cevaplanmayan ve reddedilmeyen soru `waiting`e döner |
| `merge_stories` | Arşivci ajanın kodu (model değil) | `story_ids, title, summary`; oturum `X-Evoca-Session-Id` başlığından | `{story_id, merged_ids}` | Bölünme korumasının işaretlediği ve bir konu dönemini paylaşan hikâyeler ilk hikâyede birleşir: kaynakların birleşimi, herhangi bir parçanın `stated_year`'ı, konuların birleşimi, tek bir LLM çağrısının birleşik dökümden (gizli parça yok) yazdığı yeni başlık ve özet. Birleşen kimliklere bağlı cevap, bağlantı, fotoğraf, tepki ve yeniden anlatım kalan hikâyeye taşınır, diğerleri silinir. Sadece bu oturumun `pending` hikâyeleri, aynı anlatan |
| `link_stories` | Arşivci ajan | `from_story_id, to_story_id, reason`; oturum `X-Evoca-Session-Id` başlığından | `{link_id, added}` | `source = ai, status = suggested`. `reason`: `same_place`, `same_event`, `continuation` (`answer_to` değil). İki hikâye de çemberde ve izleyen (oturumun anlatanı) ikisini de görebiliyor; aynı hikâye kendine bağlanmaz; `from_story_id` bu oturumda kaydedilmiş olmalı. Aynı çift iki yönde de tek bağlantıdır (var olanın kimliği döner; ailenin kaldırdığı bağlantı yeniden önerilmez). İki hikâyenin de en fazla 3 canlı bağlantısı olabilir (sadece izleyenin görebildiği hikâyelere giden bağlantılar sayılır). Yeniden anlatım bağlantı değildir: `save_story(original_story_id)` |
| `find_gaps` | Arşivci ajan | `person_id` | boş dönemler (`LifePeriod` sırasıyla) | Sadece çemberin merkez kişisi için (hem `person_id` hem izleyen); başkasına hata. Sunucuda hesaplanır: merkez kişinin konu olduğu, `hidden` dışındaki her hikâye sayılır (anlatan ve erişim ne olursa olsun); dışarı sadece dönem adları çıkar. Kişinin yaşı dönemin en erken makul yaşının altındaysa (gençlik 13, evlilik ve çocuk büyütme 18, orta yaş 40, emeklilik 55) o dönem boşluk sayılmaz; doğum yılı yoksa hiçbir dönem atlanmaz. Sonra en fazla bir `add_question(source = gap)` |

**İki ajan, bir MCP sunucusu.** *Sohbet ajanı* büyükle canlı konuşur. *Arşivci ajan* oturum kapanınca arka planda çalışır ve şu sırayı izler:

1. `get_session_transcript` ile oturumu okur.
2. Hikâyeleri ayıklar; her biri için önce `search_archive` (yer, kişi ya da nesneyle), sonra `save_story` (mevcut bir hikâyenin yeniden anlatımıysa bulunan hikâyenin `original_story_id`'si ile). Bir anı bir hikâyedir: aynı anıya eklenen ayrıntı, kişi ya da duygu yeni hikâye değildir; sadece açıkça başka bir olaya, zamana ya da yere geçilince bölünür. Kaynaklar sadece anlatanın kendi parçalarıdır, her parça ayrı kaynak (başka parçaları kapsayan tek aralık yok). Aynı çalışmada kaydedilen iki hikâyenin kaynakları örtüşüyor ya da arada (arkadaşın parçaları sayılmadan) 5 saniyeden az boşluk varsa ve aynı yeri ya da bir konu dönemini paylaşıyorlarsa kod bunu "olası bölünme" olarak (sadece hikâye kimlikleriyle) günlüğe yazar; çalışma bitince bir konu dönemini paylaşanları `merge_stories` ile birleştirir (farklı dönemler ayrı kalır). `save_story` sunucuya gitmeden önce sıcaklık 0 kontrol, anlatanın kaynaklardaki kendi sözlerine bakıp pasajın esas olarak bir şeyden bahsetmeyi reddetmek olup olmadığını söyler; "evet" ya da emin değilse (hata dahil) hikâye kaydedilmez ve kod aynı aralık için `add_refused_topic` yolunu (aynı kontrol kurallarıyla) çalıştırır. Ret asla hikâye olmaz.
3. Sorulan her soru için cevap aralığını bulur; `record_answer`. Döküm bekleyen aile sorularını da gösterir (`waiting_family_questions`, hassas olanlar hariç); büyük hiç sorulmamış bir aile sorusunu açıkça cevapladıysa aynı cevap kontrolüyle o da `record_answer` ile kaydedilir. Büyük açıkça reddettiyse `mark_question_declined`. Büyük bir konuyu kendiliğinden açıkça reddettiyse `add_refused_topic`.
4. Arama sonuçlarında açıkça aynı adlandırılmış yer, aynı olay ya da devamı olan hikâye için `link_stories`; emin değilse bağlamaz.
5. Merkez kişi için `find_gaps`; boş dönem varsa oturum başına en fazla bir `add_question(source = gap, period)`, nazik ve açık uçlu ("What do you remember about your early married years?"). Kod sınırı da uygular: dönem bu çalışmada `find_gaps`'in döndürdüklerinden olmalı (model çağırmadıysa kod çağırır). Takip soruları ayrıca en fazla iki. Panel kaydında `find_gaps` ve soru araçları sunulmaz; sadece `get_session_transcript`, `save_story`, `search_archive`, `link_stories`.
6. Kalan her `asked` soru (cevaplanmamış, reddedilmemiş) `reopen_question` ile `waiting`e döner; sonraki oturumda yeniden sorulur.

Cevap iletimi (bildirim) `record_answer`'ın yan etkisidir; ajan doğrudan bildirim göndermez.

**REST uçları** (web istemci çağırır; hepsi `can_see` ile süzer)

| Uç | Kim | Ne yapar |
| --- | --- | --- |
| `POST /api/device/session/start` | Cihaz ekranı | Oturumu başlatır (davet varsa `invitation`, yoksa `spontaneous`), MCPBridge ve ChatAgent açar, açılış turunu çalıştırır; `POST /api/device/turn` ile aynı şekli döner |
| `POST /api/device/turn` | Cihaz ekranı | Ses yükler; cevap metni + TTS sesi + gösterilecek kartlar döner |
| `POST /api/device/session/end` | Cihaz ekranı | Oturumu kapatır, işlemeyi başlatır |
| `GET /api/device/invitation` | Cihaz ekranı | Işık yansın mı? |
| `POST /api/questions` | Aile paneli | Aile sorusu ekler; filtrelenirse açıklama döner |
| `GET /api/feed` | Aile paneli | Bildirimler: cevaplar, yeni hikâyeler |
| `GET /api/lifeline/{person_id}` | Aile paneli | Hesaplanmış hayat çizgisi: tüm dönemler enum sırasıyla (boşlar boş liste), dönem içinde eskiden yeniye; kişi izleyenin bir çemberinde değilse 404 |
| `GET /api/stories/{id}` | Aile paneli | Hikâye sayfası: ses aralıkları, döküm, anlatımlar, bağlantılar. Gizli parçalar ses aralığından, dökümden ve süreden çıkarılır; `has_private_part` sadece anlatana `true` olabilir. Görülemeyen hikâye, olmayan hikâyeyle aynı 404'ü döner. Tepkiler sayısız: `present` ve `mine` |
| `GET /api/stories/{id}/playlist` | Aile paneli | Baştan dinle sırası: hikâye + doğrudan bağlılar (derinlik 1, `removed` hariç), en erken konu dönemine sonra `created_at`'e göre; görülemeyen bağlı hikâye iz bırakmadan atlanır (`skipped_count` yok) |
| `POST /api/recordings` | Aile paneli | Aile üyesinin kendi anısı (tek kişilik `panel_recording` oturumu): multipart `audio` + `access?` (`circle`\|`private`); en fazla 3 dakika, boş veya uzun ses 400; hemen 202 `{session_id, started_by, processing}`, döküm ve arşivci arka planda (A4 notları) |
| `POST /api/stories/{id}/reactions` | Aile paneli | Emoji ekler/kaldırır; tekrar edilebilir (idempotent), yeni tepki `delivered_to_center = false`. Sayı dönmez |
| `PATCH /api/stories/{id}/subjects/{person_id}` | Aile paneli | Dönem düzeltme (`period_source = family`, `corrected_by` = izleyen); hikâyeyi gören herkes |
| `PATCH /api/stories/{id}` | Anlatan, konu kişi, merkez, yönetici | Erişimi (`circle`/`private`) sadece anlatan değiştirir. Gizlemeyi anlatan, hikâyenin konusu olan kişi, merkez kişi veya yönetici yapar; gizleme kesindir, `hidden: false` herkes için reddedilir |
| `DELETE /api/links/{id}` | Aile paneli | Yanlış bağlantıyı kaldırır (`status = removed`, satır silinmez); izleyen iki hikâyeyi de görebilmeli |
| `POST /api/stories/{id}/photo` | Anlatan, konu kişi, yönetici | Multipart `image` (JPEG/PNG/WebP, en fazla 5 MB) + `caption?` (en fazla 120 karakter). Pillow ile en fazla 1600 px JPEG'e yeniden kodlanır, tüm üst veri (EXIF, GPS) silinir; `data/photos/<uuid>.jpg`. Hikâye başına bir fotoğraf: yenisi eskisinin yerine geçer, eski dosya silinir. Görülemeyen ya da gizlenmiş hikâye olmayanla aynı 404; gören ama yetkisi olmayan 403; yanlış tür, büyük ya da bozuk dosya 400 |
| `DELETE /api/stories/{id}/photo` | Yükleyen, anlatan, yönetici | Fotoğrafı ve dosyasını siler |
| `GET /api/photos/{photo_id}` | Hikâyeyi gören herkes | JPEG, `Cache-Control: private, no-store` (tarayıcı kopya saklamaz); görülemeyen ya da gizlenmiş hikâyenin fotoğrafı olmayanla aynı 404. Panel sesi gibi başlıkla `fetch` edip blob olarak gösterir. `photo_url` ve `photo_caption` hikâye sayfasında, akış hikâye ve cevap kartlarında ve hayat çizgisi öğelerinde döner (yoksa `null`) |
| `GET`/`POST /api/admin/sensitive-topics`, `DELETE /api/admin/sensitive-topics/{id}` | Yönetici | Aile hassas konuları. Liste sadece `source = family` döner (`{id, text, added_by, created_at}`); `speaker` konuları listelenmez, sayılmaz, id'leri olmayan id ile aynı 404'ü alır. Ekleme `source = family`, `added_by` = izleyen; boş metin ya da eşleşecek anlamlı kelimesi olmayan metin 400 (`add_refused_topic` kuralı); aynı metin (büyük/küçük harf farksız) mevcut konuyu döner. Silme süzülmüş soruları yeniden değerlendirmez |
| `PATCH /api/admin/circle` | Yönetici | `chat_time?` (`HH:MM`), `timezone?` (IANA adı); geçersiz değer 400. Davet zamanlayıcı bir sonraki turda kullanır; bugünün daveti zaten varsa bugün bir şey değişmez |
| `POST /api/admin/members` | Yönetici | Henüz yok (Bilinen sınırlar). Tüm `/api/admin/*` uçları sadece çemberin `admin`'ine açık; merkez dahil herkes aynı 403'ü alır |
| `GET /api/audio/{session_id}?start=&end=` | Herkes | Ses aralığını akıtır; erişim kontrolü burada da yapılır |
| `GET /api/people` | Kişi seçici | **Sadece demo**, başlık istemez: kişiler ve çemberleri (`circle_id`, rol). Bkz. Bilinen sınırlar |
| GET /api/circle | Aile paneli | Çember, "ben" ve üyeler (rol, relation\_to\_center). İzleyen kişi X-Person-Id başlığından okunur (hackathon kimlik kararı, bkz. Karar günlüğü 17 Ekim). Örnek cevaplar: docs/api-samples/ |

**Arka plan işleri**

- **Davet zamanlayıcı** (dakikada bir, açılışta da; `core/services/invitations.py`, demo için `python -m server.run_invitations`): her `active` çemberde, çemberin saat dilimine göre sohbet saati geçtiyse ve o yerel gün için davet yoksa merkez kişiye tam bir `Invitation` açar. Merkez kişinin o yerel gün daha önce başlamış bir oturumu varsa ya da şu an canlı bir oturum varsa davet `skipped` olur (gün işlenmiş sayılır, ışık yanmaz); yoksa `sent`. Ailenin panel kayıtları sayılmaz. Günde birden fazla davet `(circle_id, date)` tekil indeksiyle eşzamanlı çalışmada da engellenir. Hatalar günlüğe yazılır, döngü durmaz.
  Sebep kodda üretilir (sohbet ajanı kendi sözleriyle söyler), şu öncelikle: (1) merkez kişinin hikâyelerine iletilmemiş tepki: "<ad> reacted to your story", birden fazla kişiyse "Your family reacted to your stories"; (2) bekleyen aile sorusu: "<soranın adı> has a question for you"; (3) bekleyen takip/boşluk sorusu: "I have a question about one of your stories"; (4) yoksa "Would you like to chat today?". Sadece `get_pending_questions`'ın sunacağı sorular sayılır (`waiting`, hassas konuya takılmayan); `filtered`, `declined`, `asked` asla. Sebepte soru metni, hikâye başlığı ya da konu kelimesi olmaz, en fazla bir ön ad.
- **Yayınlayıcı** (dakikada bir): `publish_at` geçen `pending` hikâyeleri `published` yapar ve bildirim üretir.
- **Boşluk denetimi**: şimdilik ayrı bir iş değil; arşivci her cihaz oturumundan sonra `find_gaps` ile yapar (en fazla bir boşluk sorusu).

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

**Git çalışma kuralları**

- `main` her zaman çalışır durumda kalır; demo ve testler oradan yapılır.
- Her iş için kısa ömürlü bir dal: `zeynep/<iş>`, `aleyna/<iş>`. Dallar `main`'den açılır.
- İş bitince aynı gün pull request ve `main`'e birleştirme. Onay şartı yok; karşı tarafı etkileyen değişiklik (ör. bir REST ucunun cevabı) haber verilir ve bu belgede güncellenir.
- Her gün başlamadan önce `main`'e geçip Pull.
- Commit mesajları İngilizce ve kısa: `Add save_story tool`, `Fix audio range playback`.

**Günlük plan** (Türkiye saati)

**13 Ekim Salı · Kurulum ve doğrulama**

- [ ] Ortak: bu belgeyi okuyup itirazları karar günlüğüne yazmak; isim ve demo dili kararı
- [ ] Ortak: akşam 4-5 kişiyle kısa kullanıcı görüşmesi
- [x] A: repo, lisans, FastAPI + MCP sunucusu "merhaba" aracı Streamable HTTP üzerinden; SDK'nın spec 2025-11-25 desteğini doğrulamak
- [x] A: 1 dakikalık Türkçe kayıtla iki STT seçeneğini kelime zaman damgasıyla denemek; LLM sağlayıcısını seçip araç çağırma testi
- [ ] B: web iskeleti; cihaz ekranında bas-konuş kayıt ve ses çalma

**14 Ekim Çarşamba · İlk uçtan uca konuşma**

- [x] A: veri modeli, veritabanı, `can_see`, demo ailesi tohum verisi (Fatma, Ayşe, Elif, Can)
- [x] A: sohbet ajanı döngüsü; `get_session_context`, `get_pending_questions`, `mark_question_asked`
- [ ] B: cihaz ekranı ↔ `POST /api/device/turn`: konuş, cevabı duy

**15 Ekim Perşembe · Arşiv**

- [x] A: arşivci ajan; `get_session_transcript`, `save_story`, dönem tahmini; TTS
- [ ] B: hayat çizgisi ve hikâye sayfası (önce sahte veriyle), ses aralığı oynatıcı

**16 Ekim Cuma · Soru döngüsü** (karar noktası)

- [x] A: `add_question`, hassas konu kontrolü, `record_answer`, ses aralığı akıtma ucu
- [ ] B: soru formu, bildirim akışı, cevap kartı
- [ ] Ortak: **Döngü uçtan uca çalışıyor mu?** Elif soru sorar → Fatma cevaplar → Elif kendi sesiyle duyar. Çalışmıyorsa 17 Ekim'in tamamı buna.

**17 Ekim Cumartesi · Ritim ve aile katılımı**

- [x] A: davet zamanlayıcı, yayınlayıcı, `DEMO_NOW`, `find_gaps`, `mark_private`, tepkilerin büyüğe iletilmesi
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
| LLM sağlayıcısı | Karar verildi: Amazon Bedrock, Nova 2 Lite (Claude Haiku 4.5 arşivci için aday) | – |
| Konuşmadan metne servisi | Karar verildi: yerel faster-whisper + aile isimleri ipucu (Transcribe ücretsiz planda kapalı) | – |
| Kim A, kim B? | **Karar verildi:** A Zeynep Sude, B Aleyna | – |
| Buluşma modu yapılsın mı? | **Karar verildi:** çekirdek eksiksizse evet; kontrol 18 Ekim | 18 Ekim |
| Ses (TTS) kalitesi | Polly standard robotik. Seçenekler: Edge Natural sesler, ücretli plan + Polly neural | 21 Ekim |
| Claude kullanımı krediden düşüyor mu? | Faturalama ekranından kontrol; düşüyorsa arşivci Claude Haiku 4.5'e geçebilir | 14 Ekim |
| Kimlik: panel isteğin kimden geldiğini nasıl bilir? | **Karar verildi:** hackathon için şifresiz kişi seçici (A) ve `X-Person-Id` başlığı. Kişisel davet linki (C) "Sonra"ya taşındı. Ses `X-Person-Id` başlığıyla çekilir ve blob olarak çalınır | – |

**Riskler**

| Risk | Etkisi | Önlem |
| --- | --- | --- |
| "Bu sadece LLM sohbeti" eleştirisi | Fikir ve teknik puanı düşer | İki ajan ve 14 araçlı MCP sunucusu; boşluk tespiti; videoda araç çağrıları paneli |
| "Neden telefon etmiyorum?" itirazı | Etki puanı düşer | Bire çok paylaşım, kalıcılık, toplu hatırlama, aramaya teşvik eden bildirim; görüşmelerden alıntılar |
| MCP SDK spec 2025-11-25'i desteklemiyor | İlk eleme riski | 13 Ekim'de doğrulandı (2026-07-28); risk kalktı |
| Yaşlı konuşmasında tanıma hatası | Döküm ve eşleştirme bozulur | Ses asıl kaynak; döküm düzeltilebilir; aile isimleri Whisper'a ipucu olarak verilir; demo kayıtları önceden denenir |
| Cevap eşleştirmede yanlış aralık | Torun yanlış parçayı duyar | Eşleştirmeye birkaç saniye pay; demo öncesi elle kontrol |
| LLM'in gizli içeriği sızdırması | Güven kaybı | Filtre LLM'den önce; gizli parçalar bağlama hiç girmez |
| Yeni AWS hesabında kota veya kredi sorunu | Servis çalışmaz | 13 Ekim: Bedrock çalışıyor, Transcribe ücretsiz planda kapalı (yerine Whisper). AWS Builder için Bedrock + Polly standard + Kiro |
| Alexa'nın Türkçe desteklememesi | Jüri sorusu | Ürün ve demo İngilizce; risk kalktı |
| Zaman | Çekirdek yetişmez | Karar noktaları (16 ve 18 Ekim); buluşma modu kesilebilir |

**Ürün olarak çözülmemiş soru:** Çoklu çemberde bir kişi hakkındaki hikâyeyi, o kişinin farklı çemberlerindeki akrabaları görebilmeli mi? Hackathon kapsamında değil; erişim modeli ileride buna göre genişletilecek.

**Bilinen sınırlar**

- Gizleme API'den geri alınamaz: `hidden: false` herkes için reddedilir. Yanlışlıkla gizlenen bir hikâye sadece veritabanından elle geri açılabilir; kimin gizlediği saklanmadığı için anlatanın, konu kişinin gizlemesini geri alması da böylece engellenir.
- Hikâye kaydedildikten sonra bir parça gizli işaretlenirse ses aralığı ve döküm her okumada yeniden kesilir, ama başlık ve `ai_summary` yeniden üretilmez ve gizli kısmı anabilir. Bugünkü akışta işaret arşivciden önce yapıldığı için bu durum beklenmez.
- Panel kaydından çıkan `private` hikâye önce `circle` olarak kaydedilir ve hemen ardından kod tarafından `private` yapılır; bu milisaniyelik aralıkta `pending` hikâyeyi merkez kişi ve yönetici görebilir (tek adımda oluşturmak `save_story` MCP yolunu değiştirmeyi gerektirir).
- `GET /api/people` sadece demo içindir: başlık istemeden herkesin adını, çemberini ve rolünü döner; gerçek kullanımda kaldırılmalıdır.
- Şifresiz kişi seçici sadece demo içindir: panelde herkes herhangi bir kişiyi (merkez kişi dahil) seçip onun adına görebilir, gizli parçalar dahil; gerçek kullanımdan önce kişisel davet linkiyle kimlik şarttır.
- Açık `keep_private` her zaman işaretler: modelin yanlış okuması zararsız bir hikâyeyi de gizleyebilir. Örnek: eval prompt_v9, private_then_move_on 2. koşu 4. tur — benzetilen kişinin "bazı aile meseleleri özel kalmalı" demesi üzerine `next` çağrıldı ve sonraki gül/yorgan hikâyesi arşivden düştü.
- Başka bir kişiyi anan cümleler de koruyucu terimi olur ("Kızım Leyla gülleri sever" → leyla, kızım, gül); devam kuralındaki "başka bir kişiyi anıyorsa" istisnası bu yüzden pratikte bir şey değiştirmez.
- Koruyucu terimleri daraldı: "Now he never speaks to me" gibi bir cümle konu değişikliği sayılır, sadece cümle başında geçen bir isim ("Selim took the money.") isim sayılmaz.
- Gizlilik kontrolü bir LLM yargısıdır; dolaylı bir isteğe ("bu aile kitabına girmesin") yanlış "hayır" diyebilir ve otomatik işaret düşer (reddedilen konuların gizlenmemesi için bilerek yapılan takas).
- Prompt'taki "konuyu reddetmek sır değildir" kuralı, ret ve gizlilik isteğini karıştıran turlarda modelin `keep_private`'ı atlamasına yol açabilir; tek yedek kontrolden geçen otomatik işarettir.
- API testleri gizlilik kontrolünü hep "evet" olarak taklit eder; "hayır" yolu sadece ajan testlerinde denenir.
- Davetin "sonra" ve "bugün değil" cevapları ayrı izlenmez: oturum başlayınca davet `accepted` olur ve öyle kalır; o gün yeni davet zaten açılmaz (günde bir). `postponed` ve `declined` durumları şimdilik kullanılmıyor. Davetler panelde hiçbir uçta görünmez, bu yüzden reddedilen davet aileye raporlanmaz.
- Arşivci (Nova 2 Lite) tek bir anıyı bazen iki hikâyeye böler (gerçek denemede liman anısı, "pazar günleri liman" ve "balıkçı tekneleri" olarak iki kez); iki hikâye de aynı oturumdan ve doğru bağlantılı olduğu için kabul edildi. Prompt "bir anı = bir hikâye" kuralı ve liman örneğiyle güncellendikten sonra eval split_v1'de tek anı 3 koşunun 2'sinde tek hikâye oldu (1 koşuda üçe bölündü: liman, tekneler, babası ve balıkçılar); iki ayrı anı 3/3 doğru ayrıldı. Otomatik birleştirme yok. Kod koruması bu bölünmeyi yakalamadı: büyüğün parçaları arasında arkadaşın sorusu olduğu için boşluk 5 saniyenin üstünde kaldı. Koruma artık arkadaşın parçalarını boşluğa saymıyor ve kaynak kuralı ("anlatanın her parçası ayrı kaynak, sadece anlatanın parçaları") eklendi; split_v2 regresyon koşusu: tek anı yine 2/3 (1 koşuda üçe bölündü, koruma iki olası bölünmeyi günlüğe yazdı), iki ayrı anı 2/3 (1 koşuda model `get_session_transcript`'e yanlış oturum kimliği verdi, "bulunamadı" hatasından sonra durdu ve hiç hikâye kaydetmedi; bölünmeyle ilgisiz). Daha fazla prompt değişikliği yapılmadı. 17 Ekim gerçek tarayıcı oturumunda (feeea8a0) oyunlar anısı üçe, düğün ikiye bölündü; artık bölünme korumasının işaretlediği ve aynı dönemi paylaşan hikâyeler kodla otomatik birleştirilir (Karar günlüğü). Kısa iki ayrı anı aynı dönemde ve bitişikse yanlışlıkla birleşebilir; bu kabul edildi.
- Reddedilen konu sorulara sadece kelime eşleşmesiyle uygulanır: dolaylı bir bağlantı (Hatice'yi reddettikten sonra "Zehra nasıl biriydi?") yakalanmaz.
- Yönetici bir aile konusunu silince o konunun daha önce süzdüğü sorular `filtered` kalır; yeniden değerlendirilmez, aile soruyu yeniden sormalıdır.
- `POST /api/admin/members` yok: aile üyeleri sadece seed'den gelir; panelden üye eklenemez.
- Fotoğrafı yükleyen kişi hikâyeyi artık göremiyorsa (anlatan hikâyeyi `private` yaptı) kendi fotoğrafını silemez: hikâyenin varlığını söylememek için aynı 404'ü alır. Fotoğrafı anlatan veya yönetici silebilir.
- Fotoğraf yüklemesinde boyut sınırı `Content-Length` başlığına bakılarak gövde okunmadan uygulanır; başlıksız (chunked) bir gövde ancak okunduktan sonra 5 MB kontrolüne takılır. Gerçek kullanımda sınır ters vekil sunucuda da konmalıdır.

## Karar günlüğü

Yeni kararlar tablonun en üstüne eklenir. Bir karar geri alınırsa satır silinmez; yeni bir satır eklenir.

| Tarih | Karar | Gerekçe |
| --- | --- | --- |
| 17 Ekim | Gerçek tarayıcı oturumundaki (feeea8a0) üç arşivci hatası için kod düzeltmesi: (1) Ret hikâye olmaz: `save_story`'den önce sıcaklık 0 kontrol, anlatanın kaynaklardaki kendi sözlerinin esas olarak bir şeyden bahsetmeyi reddetmek olup olmadığına bakar; "evet" ya da emin değilse (hata dahil) hikâye kaydedilmez, kod konuyu adlandırır ve o aralık için `add_refused_topic` yolunu aynı kontrol kurallarıyla çalıştırır; günlüğe sadece kimlikler yazılır. (2) Bu kayıt 17 Ekim'deki "otomatik birleştirme yok" kararının yerine geçer: bölünme korumasının işaretlediği ve bir konu dönemini paylaşan hikâyeler çalışmanın sonunda `merge_stories` ile birleşir (kaynak birleşimi, herhangi bir parçanın `stated_year`'ı, konu birleşimi, birleşik dökümden tek LLM çağrısıyla yeni başlık ve özet; cevap, bağlantı ve fotoğraflar kalan hikâyeye taşınır); farklı dönemler ayrı kalır. (3) Arşivci, hiç sorulmamış bekleyen bir aile sorusunu büyük açıkça cevapladıysa aynı cevap kontrolüyle `record_answer` çağırabilir; takip ve boşluk soruları yine `asked` ister. Regresyon: `tests/fixtures/real_session_feeea8a0.json` ve `tests/test_archivist_real_session.py`. Gerçek arşivciyle (Bedrock) oturumun yeniden arşivlenmesi: oyunlar 1 hikâye (childhood), düğün 1 hikâye (marriage_early_years, 1971), Mustafa hikâye değil konuşmacının reddettiği konu, oyun sorusu cevaplandı, sır hiçbir yerde değil; 3 koşunun ilkinde (bekleyen aile soruları henüz ilk mesajda değilken) cevap eşleşmedi, sonraki 2'si ve `data/browser.db` üzerindeki koşu tam. split_v3: tek anı 3/3, iki anı 3/3 | Gerçek oturumda "Declining to Discuss Mustafa" hikâyesi kaydedildi (ret ailenin akışına düşerdi), oyunlar üç ve düğün iki karta bölündü, Elif'in oyun sorusu hiç sorulmadığı için cevabı eşleşmedi. Eval'ler bunları yakalamadı. Prompt kuralları modelde tutmadığı için kontrol koda alındı |
| 17 Ekim | Hikâye bölünmesi satırını günceller: (1) bölünme korumasında boşluk, aradaki arkadaş (ajan) parçaları çıkarılarak ölçülür, eşik yine 5 saniye. (2) Arşivci prompt'una kaynak kuralı: anlatanın her parçası ayrı kaynak, başka parçaları kapsayan aralık yok, sadece anlatanın kendi parçaları. split_v2 (3'er koşu): tek anı 2/3, iki anı 2/3 (başarısız koşu yanlış oturum kimliği yüzünden hiç hikâye kaydetmedi). Sonuç ne olursa olsun daha fazla prompt değişikliği yok. (3) Arşivci, oturum kimliği alan her araçta (`get_session_transcript`, `mark_question_declined`, `save_story` kaynakları) modelin değerini yok sayar ve arşivlediği oturumu kullanır (farklıysa sadece kimlikler günlüğe yazılır); prompt değişmedi. split_v3_session (sadece iki anı, 3 koşu): 3/3 | (1) split_v1'deki gerçek bölünmede büyüğün parçaları arkadaşın sorusu yüzünden 5,0-5,4 saniye arayla duruyordu ve koruma yakalamadı; split_v2'de yakaladı. (2) Gizlilik incelemesi: geniş tek aralık gizli bir parçaya değip kaydı düşürebilir, toplu oturumda başkasının sözü anlatanın hikâyesine karışabilir |
| 17 Ekim | Hikâye bölünmesi: arşivci prompt'una "bir anı = bir hikâye" kuralı eklendi (sadece açıkça başka olay, zaman ya da yere geçilince böl; daha az ama zengin hikâye), liman anısıyla bir olumlu ve bir olumsuz örnek. Kod koruması: aynı çalışmada kaynakları örtüşen ya da 5 saniyeden yakın ve aynı yeri ya da bir konu dönemini paylaşan iki hikâye "olası bölünme" olarak sadece kimlikleriyle günlüğe yazılır (`ArchiveResult.possible_splits`); otomatik birleştirme yok. Eval: `evals/run_archivist_split.py` (bellekte veritabanı, gerçek arşivci); split_v1: tek anı 2/3, iki anı 3/3 | Gerçek denemede liman anısı iki karta bölündü. Bölünmeyi iki kısa anıdan ayırmak insan kararı ister, birleştirmek yanlışsa bir anı kaybolur. Bir prompt revizyonundan sonra 3/3 olmadığı için daha fazla denenmedi (Bilinen sınırlar) |
| 17 Ekim | Hikâye fotoğrafları ("Zaman kalırsa"dan çekildi): `StoryPhoto` tablosu, hikâye başına bir fotoğraf (yenisi eskisini ve dosyasını siler). Yükleme anlatan, konu kişi veya yönetici; silme yükleyen, anlatan veya yönetici. Her yükleme Pillow ile yeni bir JPEG'e (en fazla 1600 px) kodlanır, EXIF/GPS dahil tüm üst veri silinir, dosya adı UUID'dir. Gizlenmiş hikâye kimseye fotoğraf göstermez (anlatana bile). Ajanlar fotoğraf görmez; seed'de fotoğraf yok, demo fotoğrafları API'den yüklenir. Hayat çizgisi dönemlerine `years: {from, to}` eklendi, sabit yaş aralıklarıyla (childhood 0-12, youth 13-22, marriage_early_years 23-30, raising_children 31-45, midlife 46-60, retirement 61+) | Panel tasarımı hikâye başına bir fotoğraf üstüne kurulu. Eski fotoğrafların EXIF'i konum ve cihaz bilgisi taşıyabilir; yeniden kodlamak her alanı tek tek silmekten güvenli. Yıllar paneldeki zaman çizelgesi için; sabit aralık, kişiye göre tahminden basit ve tutarlı |
| 17 Ekim | Sesle baştan dinle satırını günceller: (1) `get_linked_playlist` modele sadece `story_id`, `title`, `teller` (ad), `period` döner, hikâye başına bir öğe; `session_id`/`start_ms`/`end_ms` modele gitmez. Cihaz kartının `url`'leri o turda sunucuda `playlist_ranges` (aynı `build_playlist`, aynı izleyici, aynı sıra ve sınır) ile yeniden kurulur. (2) Sohbet ajanı bir aile üyesinin isteğini ya da ilgisini sadece araçlarda o kişiden bir tepki ya da bekleyen soru varsa anar | (1) İki aralık arasındaki boşluk modele gizli bir parçanın kesildiğini söyler (gizlilik incelemesi). (2) Eval playlist_v1 2. koşu: soru yokken "kızınız Ayşe ... dinlemek ister" uyduruldu |
| 17 Ekim | Sesle baştan dinle: `get_linked_playlist(story_id)` MCP aracı `core/services/stories.build_playlist`'i oturumun izleyicisi (merkez kişi) adına çağırır; `can_see` ve gizli parça kesme aynen uygulanır, en fazla 5 öğe döner (istenen hikâyenin parçaları önce tutulur, kalan yerleri bağlılar doldurur), görülemeyen hikâye olmayanla aynı hatayı alır. Cihaz turu cevabına o turda araç başarıyla çalıştıysa `{type: "playlist", items: [{story_id, title, teller, url}]}` kartı eklenir; `url` mevcut `/api/audio/{session_id}?start=&end=` ucudur. Cihaz önce cevap sesini, sonra öğeleri sırayla çalar (istemcinin işi). Ajan sadece istenince çalar ve hikâyeyi yeniden anlatmaz | Büyüğün "dinlet" isteği A5'in çekirdek parçası; aynı servis panelle aynı gizlilik kurallarını garanti eder, ses de zaten kontrollü uçtan çalar |
| 17 Ekim | Yönetici uçları: `GET`/`POST /api/admin/sensitive-topics`, `DELETE /api/admin/sensitive-topics/{id}`, `PATCH /api/admin/circle` (`core/services/admin.py`). Hepsi sadece çemberin `admin`'ine açık; merkez ve üye aynı 403'ü alır. Sadece `source = family` konular listelenir, eklenir, silinir; `speaker` konusunun id'si olmayan id ile aynı 404'ü alır ve tekrar kontrolü sadece aile konularına bakar. Ekleme metni `add_refused_topic` kuralıyla doğrulanır. Silme süzülmüş soruları yeniden değerlendirmez. `chat_time`/`timezone` değişikliği zamanlayıcının bir sonraki turunda geçerli olur, o günün mevcut davetine dokunmaz. `POST /api/admin/members` bu adımda yok. `add_refused_topic` tekrar kontrolü artık sadece `speaker` konularına bakar: aynı metinli aile konusu olsa da büyüğün reddi ayrı satır olarak saklanır | Demo için yönetici ekranı gerekli. Büyüğün reddettiği konu yöneticiye de gösterilmez (17 Ekim kararı); tekrar kontrolü `speaker` konusunu da sayıp mevcut id'yi dönseydi, yönetici isim deneyerek büyüğün reddini çıkarabilirdi. Eşleşecek kelimesi olmayan konu hiçbir soruyu süzmez, kaydetmek tutamayacağı bir söz vermek olur. Yeniden değerlendirme, `asked` ya da cevaplanmış sorular için ayrı kurallar gerektirirdi. Silme ucu gelince, aile satırına yaslanan bir red o satırla birlikte silinirdi (gizlilik incelemesi) |
| 17 Ekim | `link_stories` ve `find_gaps` eklendi. Arşivci bağlantı adayını `search_archive` ile, oturumun anlatanı adına arar (cihaz oturumunda merkez kişi, panel kaydında kaydeden); her hikâyeden önce arar, yeniden anlatımı `original_story_id` ile kaydeder. Bağlantı: `answer_to` hariç neden, `ai`/`suggested`, iki yönde tek, hikâye başına en fazla 3, `from_story_id` bu oturumdan (oturum başlıktan). `find_gaps` sadece merkez kişi için; `hidden` dışındaki tüm hikâyeleri sunucuda sayar, sadece dönem adı döner; doğum yılına göre yaşanamamış dönemleri atlar. Oturum başına en fazla bir boşluk sorusu, `find_gaps`'in döndürdüğü bir dönem için ve o dönemde bekleyen boşluk sorusu yoksa; `gap` sorusu `period` ister | Arşivci sadece anlatanın görebildiği hikâyeleri görmeli; gizli bir hikâyeye bağlantı zaten görmeyen kişiden gizlenir ama model de onu bilmemeli. Boşluk hesabı tüm hikâyeleri saymazsa, başkasının gizli hikâyesi olan bir dönem için soru tekrar tekrar sorulurdu; dönem adı hikâyeyi açığa çıkarmaz. Gerçek denemede (Nova 2 Lite) model aramayı ayrı bir adım olarak atladı ve var olan bir hikâyeyi ikinci kez kaydetti; kaydetmeden önce arama adımı bunu düzeltti. Gizlilik incelemesi: arama sonuçları başka oturumların ses aralıklarını taşıdığı için model bunları yeni bir `circle` hikâyesine kopyalayabilirdi; bu yüzden kaynaklar oturuma bağlandı, arama sonuçları daraltıldı ve `record_answer` bu çalışmanın hikâyelerine sınırlandı |
| 17 Ekim | Davet zamanlayıcı: çember başına yerel günde tek davet (`(circle_id, date)` tekil indeksi; `init_db` eski veritabanına ekler, çakışan satır varsa eklemez ve silmez). Atlama kuralı: merkez kişinin o yerel gün daha önce başlamış ya da şu an canlı bir oturumu varsa davet `skipped` açılır (gün işlenir, ışık yanmaz). Sebep metinleri kodda, öncelik sırasıyla: "<ad> reacted to your story" / "Your family reacted to your stories", "<ad> has a question for you", "I have a question about one of your stories", "Would you like to chat today?". `get_session_context` bugünün `sent` ya da `accepted` davetini okur | Açılış turu, `session/start` daveti `accepted` yaptıktan sonra bağlamı okuyordu; sadece `sent` aranınca sebep ajana hiç ulaşmıyordu. Atlama kuralı "sohbet saatinden önce" yerine "o gün daha önce" diye yazıldı: sunucu sohbet saatinden sonra açılırsa, büyük çoktan konuşmuşken ışık yanmasın. Sebepte içerik olmaması, cihaz ekranında ya da sesli sebepte sorunun veya hassas bir konunun açığa çıkmaması için |
| 17 Ekim | Büyüğün reddettiği konular için gizlilik incelemesi kararları: (1) `POST /api/questions` sadece `speaker` konusuna takılırsa soru `filtered` saklanır ama normal kabul cevabı (`waiting`) döner; aile konusuna takılırsa genel süzme mesajı kalır. (2) `add_refused_topic` sadece merkez kişinin kendi sözlerini sayar ("ya da oturum konuşmacısı" kaldırıldı). (3) `get_session_context` `avoid_topics`'i sadece izleyen merkez kişiyse doldurur, başkasına `[]` | (1) Aile konularını bilen biri, genel mesajla isimleri deneyerek büyüğün neyi reddettiğini çıkarabiliyordu; `declined` soru ilkesiyle aynı: merkez kişi dışındakilere cevaplanmamış görünür. (2) Buluşmada bir torunun reddi büyüğün konusu olmamalı. (3) Büyüğün retleri, merkez kişi dışında bir kimlikle açılan MCP bağlantısına gitmemeli |
| 17 Ekim | Büyüğün kendiliğinden reddettiği konu hatırlanır: `SensitiveTopic`'e `source: family \| speaker` eklendi (varsayılan `family`; `init_db` sütunu mevcut veritabanına veri silmeden ekler). Arşivci açık bir konu reddinde `add_refused_topic(text, start_ms, end_ms)` çağırır; sıcaklık 0 kontrol konuşmacının o aralıktaki kendi sözlerinden "evet" demezse hiçbir şey eklenmez; aralık kuralları `mark_question_declined` ile aynıdır ve geçmeyen aralık kontrole gitmez. `add_question` ve `POST /api/questions` iki kaynağı da süzer, mesaj genel kalır. `get_session_context` tüm konuları kaynaksız `avoid_topics` olarak verir; sohbet ajanı bunları açmaz, büyük açarsa dinler ama soru sormaz. `speaker` konuları hiçbir panel ucunda, yönetici dahil, dönmez | Reddedilen konu oturumlar arası hatırlanmıyordu; arşivci onun hakkında takip sorusu üretebiliyordu ve sohbet ajanı aile konularını hiç bilmediği için kendisi açabiliyordu. Büyüğün reddini aileye göstermek, reddin kendisini paylaşmak olur (`declined` soru ilkesi) |
| 17 Ekim | Panel kaydından (`panel_recording`) soru çıkmaz: arşivci bu oturumlarda takip/boşluk sorusu eklemez, cevap veya ret kaydetmez, `reopen_question` çalıştırmaz ve modele sorulan sorular hiç gösterilmez; sadece `get_session_transcript`, `save_story`, `link_stories` sunulur. Anlatan kod tarafından kaydeden kişiye sabitlenir; istenen erişim kayıttan hemen sonra ve arşivci bittikten sonra tekrar uygulanır | Sorular, cevaplar ve retler merkez kişinin kendi oturumları içindir; bir torunun kaydı büyüğün sorusunu cevaplayamaz ya da reddedemez. `reopen_question` canlı bir cihaz oturumunda sorulmuş soruyu yanlışlıkla beklemeye döndürürdü. `private` bir kayıt, bekleme süresinde merkez kişi ve yöneticiye görünmemeli |
| 17 Ekim | Panel hikâye uçları: (1) `GET /api/people` sadece demo için, başlıksız kişi seçici listesi (Bilinen sınırlar). (2) Tepkiler hiçbir cevapta sayı taşımaz; sadece hangi emojilerin olduğu (`present`) ve izleyenin kendi emojileri (`mine`) döner; örnekteki `counts` kaldırıldı. (3) Baştan dinle cevabında `skipped_count` yok; görülemeyen bağlı hikâye iz bırakmadan atlanır. (4) Yapay zekâ dönemleri `estimated: true` taşır. (5) Görülemeyen hikâye olmayanla aynı 404'ü döner | (2) "Sayaç gösterilmez" kuralı. (3) Erişimi olmayan kişi gizli kaydın varlığını bile görmemeli; bir sayı bile varlığını söyler. (1) Şifresiz seçici başka türlü kişi listesini alamaz |
| 17 Ekim | Gizlilik vaadi kuralı (17 Ekim "Bunu kimse duymasın" satırını günceller): modelin açık `keep_private` çağrısı her zaman işaretler. Cevap hattının en sonunda (koruyucu ve her yeniden üretimden sonra) tek bir kural çalışır: söylenecek cevap gizlilik vaat ediyorsa ve bu turu açık bir işaret (ya da önceki bir `next`) kapsamıyorsa, sıcaklık 0 bir kontrol konuşanın bu turdaki ve önceki turdaki kendi sözlerini görür. "Evet", "emin değilim", okunamayan cevap veya kontrol hatası: `previous_turn` işaretlenir (iki tur da gizlenir; günlüğe sadece oturum kimliği yazılır). Açık "hayır": vaat cevaptan çıkarılır; yerine gelen cevap onay gibi duyulamaz ("anlıyorum", "tabii" yok) ve gizli bir terime dokunamaz, yoksa nötr cevap kullanılır. Reddedilen konu sır değildir | Söylenen her gizlilik sözü doğru olmalı: istek bir önceki turda yapılmış ya da sır önceki turda söylenmiş olabilir, vaat koruyucunun yeniden üretiminde de ortaya çıkabilir; hepsini tek bir yerde yakalamak bunu garanti eder. Konuyu konuşmak istememek sır saklama isteğiyle karıştırılınca gerçek hikâyeler arşivden düşüyordu (declines_topic); açık "hayır" bu yüzden işareti durdurur |
| 17 Ekim | Kimlik: hackathon için aile paneli şifresiz bir kişi seçiciyle açılır, her istek kişiyi `X-Person-Id` başlığıyla taşır. Kişisel davet linki (C) "Sonra"ya taşındı. Sonuç: ses uçları (`/api/audio`, `/api/tts`) da başlık ister; bir `<audio src>` başlık gönderemediği için panel sesi başlıkla `fetch` edip blob olarak çalar (docs/api-samples/README.md) | Demo ve hakem kurulumu için en basit yol; tüm erişim kuralları sunucuda başlıktaki kişiye göre zaten uygulanıyor. Davet linki gerçek kullanım için doğru çözüm ama çekirdek değil |
| 17 Ekim | "Bunu kimse duymasın": model yerel `keep_private(scope)` aracını çağırır; `this_turn` (sır ve istek aynı turda), `previous_turn` (sır önceki turda; ikisi de gizlenir), `next` (sıradaki tur). Şüphede `previous_turn`. Kod kapsamı tam parça sınırlarına çevirir ve `mark_private(start_ms, end_ms)` MCP aracını çağırır; oturum `X-Evoca-Session-Id` başlığıyla gelir. Gizlenen turlar ajanın kendi geçmişinden de silinir. İşaret başarısız olursa bekletilir ve oturum sonunda yeniden denenir; yine başarısızsa o oturum için arşivci çalışmaz. Cevap gizlilik vaat edip işaret yapılmadıysa kod `this_turn` uygular. Büyüğe asla "ailene söyle" denmez | Model milisaniye uyduramaz; uzun bir hikâyeyi varsayılan olarak gizlemek arşivden sessizce siler, bu yüzden kapsamı model seçer. Söylenen gizlilik sözü her zaman doğru olmalı; hikâye kaybolabilir ama sır sızamaz. Sır, söylendiği turda canlı olarak LLM'e ulaşır (ajan cevap verebilmek için duymak zorunda); koruma işaretten sonra başlar |
| 16 Ekim | `QuestionStatus`'a `declined` eklendi. Oturum sonunda arşivci, sorulup cevaplanmayan her soruyu `waiting`e döndürür (yeni geçiş `asked` → `waiting`, `reopen_question`); büyük açıkça reddettiyse soru `declined` olur ve bir daha sorulmaz. Cevap ve ret, sıcaklık 0 bir kontrolle doğrulanmadan kaydedilmez; emin değilken soru cevaplanmamış ve reddedilmemiş sayılır. Soran kişi reddi hiçbir zaman öğrenmez: merkez kişi dışındakilere `declined` soru cevaplanmamış gibi görünür | Cevaplanmayan soru kaybolmasın; reddedilen soru ısrarla sorulmasın. Ret `asked` durumunda kalsaydı sonraki oturumun arşivcisi onu yeniden açardı, ayrı durum bunu kalıcı yapar. Yanlış cevap torunun yanlış kaydı duymasına yol açar (Riskler); ret bilgisi hassas bir konuya işaret edebilir |
| 16 Ekim | `GET /api/audio` bir sorunun cevap aralığını sadece soran kişi cevabın hikâyesini `can_see()` ile görebiliyorsa çalar; `pending` hikâyenin cevabı sıradan üyeye yayından sonra açılır. Gizli bir parçayla çakışan aralık sadece çakıştığı her gizli parçanın konuşmacısına (`speaker_id`) ve aralık başka bir kuralla da izinliyse çalınır; merkez kişi dahil başka hiç kimse başkasının gizli parçasını duyamaz. Her ret aynı genel 403 mesajıyla döner (gizli kısmın varlığı belli olmaz). Tüm oturumu sadece `panel_recording` oturumunu kaydeden kişi ve, katıldığı oturumlarda, çemberin merkez kişisi dinleyebilir (17 Ekim'de daraltıldı: önceden merkez kişi her oturumu, başka bir üyenin panel kaydını da, baştan sona dinleyebiliyordu; `private` bir panel kaydı böylece anlatan dışında birine açılıyordu); `/api/tts` dosyaları sadece oturumun katılımcılarına | Kontroller demo için atlanmaz (Kurallar); 24 saat bekleme demoda `DEMO_NOW` ile gösterilir; erişimi olmayan kişi gizli kaydın varlığını bile görmez; `private` "sadece anlatan" demektir ve "burada gizli kısım var" uyarısı anlatana görünür, yani anlatan kendi gizli kısmını dinleyebilmeli |
| 16 Ekim | `POST /api/device/session/start` eklendi: oturumu başlatır (davet varsa `invitation` ve davet `accepted` olur), MCPBridge ve ChatAgent açar, açılış turunu çalıştırır; `/turn` ile aynı şekli döner. `/turn` ve `/session/end` sadece oturumu başlatan kişiye açık | Cihaz ekranının açılış selamını ve araç izini sohbet başlamadan göstermesi gerekiyor |
| 15 Ekim | Kapsamdan kısılmıyor; üç kalite eki eklendi (sızıntı testi, araç izi, gecikme ölçümü); Kiro görevleri büyütüldü (ajan + araçları bir arada) | Kazanmaya oynuyoruz; temel kalıplar oturduğu için büyük görevler güvenli |
| 13 Ekim | REST cevap şekilleri docs/api-samples/ altında taslak sözleşme; GET /api/circle eklendi; geçici kimlik X-Person-Id başlığı | Aleyna backend'i beklemeden sahte veriyle çalışabilsin; panelin isim ve rol listesine ihtiyacı var |
| 13 Ekim | Membership'e relation\_to\_center eklendi; uygulamayı kullanmayan kişiler (ör. vefat etmiş dede) sadece hikâye metninde isim olarak geçer | Ajan sıcak hitap eder ("torununuz Elif"), arşivci "kızım"ı doğru kişiye bağlar; değeri yönetici girdiği için soy ağacı riski yok |
| 13 Ekim | LLM: Amazon Bedrock; iki ajan da şimdilik Nova 2 Lite | Testte en hızlı (1,4 sn), sıcak cevap, krediden düşüyor, Amazon'un modeli |
| 13 Ekim | STT: yerel faster-whisper; aile ve yer isimleri her zaman ipucu olarak verilir | Transcribe ücretsiz planda kapalı; ipucuyla 6/6 isim doğru |
| 13 Ekim | TTS: şimdilik Polly standard (eu-north-1); kalite kararı demo öncesi | Ücretsiz planda proje bölgesi Stockholm ve orada neural ses yok |
| 13 Ekim | AWS'ye bağlantı aws login ile, erişim anahtarı yok | Repo herkese açık; sızabilecek anahtar olmasın |
| 13 Ekim | Deneme kodu sohbette hazırlanır, ürün kodu Kiro'da yazılır | Kiro'nun 50 kredisi ürün koduna kalsın |
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
