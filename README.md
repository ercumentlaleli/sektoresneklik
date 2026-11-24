# Sektörel ihracat esneklikleri (NACE Rev.2 × bölge)

Türkiye imalat sanayi ihracatının **fiyat** ve **gelir** esnekliklerini 24 NACE Rev.2 imalat
bölümü (C10–C33) × 6 bölge düzeyinde, 2013/01–2026/08 aylık verisiyle tahmin eder.
Ana sonuç **panel hata düzeltme modelidir (panel ECM)**; hücre bazında ARDL ve LP-IV sağlamlık
kontrolüdür.

Çıktı: `output/ihracat_esneklikleri.xlsx`

## Bölgeler

Bölge geliri, fiyat düzeyi ve bölge içi ülke ağırlıkları, Türkiye'nin 2015–2019 imalat ihracatı
paylarıyla hesaplanır.

| Bölge | Ülkeler |
|---|---|
| **AB-27** (27) | Almanya, Avusturya, Belçika, Bulgaristan, Çekya, Danimarka, Estonya, Finlandiya, Fransa, Hırvatistan, Hollanda, İrlanda, İspanya, İsveç, İtalya, Kıbrıs (GKRY), Letonya, Litvanya, Lüksemburg, Macaristan, Malta, Polonya, Portekiz, Romanya, Slovakya, Slovenya, Yunanistan |
| **ABD** (1) | Amerika Birleşik Devletleri |
| **MENA** (20) | Bahreyn, BAE, Cezayir, Cibuti, Fas, Filistin, Irak, İran, İsrail, Katar, Kuveyt, Libya, Lübnan, Mısır, Suudi Arabistan, Suriye, Tunus, Umman, Ürdün, Yemen (Dünya Bankası tanımı; Malta AB'de) |
| **BDT** (12) | Azerbaycan, Belarus, Ermenistan, Gürcistan, Kazakistan, Kırgızistan, Moldova, Özbekistan, Rusya, Tacikistan, Türkmenistan, Ukrayna |
| **Diğer Avrupa** (10) | Birleşik Krallık, İsviçre, Norveç, İzlanda, Sırbistan, Bosna-Hersek, Kuzey Makedonya, Arnavutluk, Karadağ, Kosova* |
| **Sahra Altı Afrika** (48) | Dünya Bankası SSA tanımındaki 48 ülke (Güney Afrika, Nijerya, Etiyopya, Kenya, Gana, Tanzanya, Senegal, Fildişi Sahili, …; tam liste `src/config.py`) |

\* Kosova Comtrade partner listesinde ISO kodu olmadığından ihracat verisine girmez.
Bölge fiyat düzeyinde, resmi kurun piyasa kurundan çok ayrıştığı ya da verisi güvenilmez
ülkeler dışlanır: İran, Suriye, Lübnan, Yemen, Libya, Sudan, Güney Sudan, Filistin, Eritre, Somali.

## Veri

| Değişken | Tanım | Kaynak |
|---|---|---|
| `lv` nominal ihracat | HS6 × ülke × ay, USD; HS6 → NACE eşlemesiyle sektöre toplanır | UN Comtrade abonelik API'si (`comtradeapi.un.org/data/v1/get/C/M/HS`, Türkiye beyanı, akış X) |
| `lp` ihracat fiyatı | **Bölgeye özel** sektör birim değer endeksi (USD/kg), aşağıda | Comtrade net ağırlık (kg) |
| `lx` reel ihracat | `lv − lp` | |
| `lpf` bölge fiyat düzeyi | Ülke TÜFE / USD kuru, ihracat ağırlıklı geometrik ortalama | IMF CPI ve ER, FRED EUR/USD |
| `lrp` göreli fiyat | `lp − lpf` | |
| `ly` bölge reel geliri | AB-27: çeyreklik reel GSYH (Eurostat); ABD: GDPC1 (FRED); diğerleri: yıllık reel GSYH (IMF WEO), aya interpole | |
| araçlar | Δln(USD/TRY), Δln(USD/EUR) | IMF ER, FRED |

### HS6 → CPA/NACE Rev.2 uyumu (`src/concordance.py`)

Comtrade, Türkiye verisini beyan edildiği HS sürümüyle verir: HS2012 (H4, 2013–2016),
HS2017 (H5, 2017–2021), HS2022 (H6, 2022–). Her sürüm UNSD resmi tablolarıyla eşlenir:

    HS2012 ───────────────────────────┐
    HS2017 ───────────────────────────┼─> CPC Ver.2.1 ─> ISIC Rev.4 ─> NACE Rev.2 bölümü
    HS2022 ─> HS2017 (WCO dönüşümü) ──┘

CPA 2.1, CPC 2.1'den türetilmiştir ve ilk iki hanesi NACE Rev.2 bölümüdür; bu zincir HS6 → CPA
bölümü eşlemesiyle aynı sonucu verir. Birden çok bölüme bölünen HS6 kodları (sürüm başına ~180 kod),
en çok CPC alt sınıfının bağlandığı bölüme atanır. Hurda ve atık gibi üreten sanayisi
olmayan kodlar (CPC → ISIC "n/a") ile 999999 sınıflandırılmamış kalemler imalata girmez
(dünya ihracatının yaklaşık %1–2'si). Yıllık kapsam `data/processed/coverage.csv`'dedir.
Uyum tablosu `data/ref/hs6_nace2.csv`; kaynak tablolar `data/ref/concordance/` altındadır.

**C33 (onarım ve kurulum)** hizmet faaliyetidir, HS'de karşılığı yoktur; tablolarda "mal ihracatı yok"
olarak görünür. Dolayısıyla tahmin 23 sektörde yapılır.

### Bölgeye özel birim değer endeksi (`build_panel.unit_value_index`)

Her sektör × bölge için kalem = **HS6 kodu × varış ülkesi**, birim değer = USD / net kg.
Endeks, ağırlıklı **zaman-ürün kuklası (TPD)** regresyonundan elde edilir:

    ln(uv_it) = α_i + δ_t + ε_it ,   ağırlık = kalemin o ayki değer payı

- `exp(δ_t)` fiyat endeksidir (2015 ortalaması = 100). TPD çok taraflıdır, zincirleme kayması (chain
  drift) yoktur ve dengesiz paneli (girip çıkan kalemleri) doğal biçimde işler. HS sürüm geçişlerinde
  değişmeyen kodlar dönemler arası köprü görevi görür.
- Değeri 5 000 USD'nin altındaki, kg'ı sıfır ya da tahmini olan işlemler dışlanır.
- Aykırı değer: TPD artığı sağlam standart sapmanın (1,4826 × MAD) 3 katını aşan gözlemler atılır ve
  model yeniden tahmin edilir (iki tur).
- Bir ayda en az iki dönemde görünen kalem sayısı 5'in altındaysa endeks o ay doğrusal interpolasyonla
  doldurulur. Ay başına medyan kalem sayısı `data/processed/uv_index_info.csv`'dedir.

Bölgeye özel endeks, aynı sektörde farklı pazarlara satılan ürün karmasını ve fiyatlama farklarını
yakalar. Kg temelli birim değerler kalite
ve bileşim değişimine duyarlıdır. Bu duyarlılık, ürünleri ağırlıkla iyi ölçülemeyen C21 (ilaç), C26
(elektronik), C30 (uçak, gemi) ve C32'de daha büyüktür.

## Yöntem

### Ana model: panel ECM (`estimate.panel_results`)

Her sektörde 6 bölge (i) havuzlanır:

    Δlx_it = μ_i + φ·lx_i,t-1 + θp_i·lrp_i,t-1 + θy_i·ly_i,t-1
             + D_post·(μ2_i + δp_i·lrp_i,t-1 + δy_i·ly_i,t-1)
             + Σ_k a_k Δlx_i,t-k + Σ_k b_k Δlrp_i,t-k + Σ_k g_k Δly_i,t-k
             + ay kuklaları + COVID kuklaları (2020/03–06 tekil, 2020/07–12 basamak) + ε_it

- **Bölgeye özel uzun dönem esneklikler:** fiyat `−θp_i/φ`, gelir `−θy_i/φ` (delta yöntemi).
- **Ortak:** uyarlanma hızı φ, kısa dönem dinamikleri ve mevsimsellik. Tek ülke-sektör serilerinde
  gürültülü olan φ'nin ortak tahmini, uzun dönem oranlarını belirgin biçimde istikrarlı kılar.
- **Standart hatalar ay bazında kümelenir.** Böylece aynı ay tüm bölgeleri etkileyen şoklara (kur,
  pandemi) karşı dayanıklıdır.
- **Pandemi öncesi/sonrası:** 2021+ etkileşim terimleriyle tek modelde; öncesi `−θ/φ`, sonrası
  `−(θ+δ)/φ`, fark testi `−δ/φ`.
- **Kısa dönem (etki) esneklikleri:** `b_0`, `g_0`.
- Gecikme uzunluğu (1–4) havuzlanmış modelde AIC ile seçilir. Modele girmek için bir hücrenin en az
  120 geçerli ayı olmalıdır.

Ek satırlar:
- **Panel ortalaması:** aynı sektörde tüm bölgeler için ortak θ.
- **Tüm imalat:** her bölgede 23 sektör havuzlanır (sektör sabit etkili, ortak θ).
- **Kayan pencere:** 60 aylık pencerelerle (3 ayda bir) bölgeye özel uzun dönem esneklikler.

### Sağlamlık

- **Hücre ARDL-ECM:** sektör × bölge başına ayrı model, AIC gecikmesi ≤ 6, HAC standart hatalar,
  Pesaran-Shin-Smith sınır testi (case III, k=2). † işareti eşbütünleşmenin %5'te doğrulanmadığını
  gösterir.
- **LP-IV (Jordà, kümülatif):** ufuk h = 0…12 için `lx_{t+h} − lx_{t−1}`, `lrp`'nin kümülatif değişimine
  regres edilir; göreli fiyat Δln(USD/TRY) ve Δln(USD/EUR) ile araçlanır. Bu, birim değerden gelen
  ortak ölçüm hatasının ("bölme yanlılığı") fiyat esnekliğini negatife çekme riskine karşı kontroldür.

## Çalıştırma

```bash
pip install -r requirements.txt
```

```bash
export COMTRADE_API_KEY=...
```

```bash
python src/fetch_comtrade.py --start 2013-01 --end 2026-08 --workers 6
```

```bash
python src/fetch_macro.py
```

```bash
python src/concordance.py
```

```bash
python src/build_panel.py
```

```bash
python src/estimate.py
```

```bash
python src/make_tables.py
```

Comtrade çağrı başına 100 000 satır döndürür. Bu yüzden her ay üç partner grubu için ayrı istenir
(AB-27 | ABD + Diğer Avrupa + BDT + Dünya | MENA + SSA); sınıra ulaşan grup ikiye bölünür. Ham veri
(`data/raw/`, ~250 MB parquet) depoya konmaz. Yeniden çalıştırmada var olan aylar atlanır.

## Sınırlamalar

- Kg temelli birim değer, gerçek ihracat fiyatı değil bir yaklaşımdır. Kalite ve bileşim değişimini
  tam ayıramaz (yukarıdaki sektörler).
- MENA, BDT, Diğer Avrupa ve SSA geliri yıllık WEO verisinden aya interpole edilmiştir. 2026 IMF tahminidir.
- Arz tarafı değişkeni (ör. sektörel üretim veya kapasite) modelde yer almaz. Esneklikler talep
  denklemi olarak yorumlanmalıdır.
