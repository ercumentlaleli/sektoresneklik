# Sektörel ihracat esneklikleri (NACE Rev.2 × bölge)

Türkiye imalat sanayi ihracatının **fiyat** ve **gelir** esnekliklerini NACE 2'li sektör ×
bölge (AB-27, ABD, MENA, BDT, Diğer Avrupa, Sahra Altı Afrika) düzeyinde, zamana göre
değişen biçimde tahmin eder.

## Yöntem

**Ana model – ARDL hata düzeltme (log seviyeler, aylık, 2013–2026):**

    Δlx_t = c + φ lx_{t-1} + θp lrp_{t-1} + θy ly_{t-1} + D_post·(c2 + δp lrp_{t-1} + δy ly_{t-1})
            + Σ a_i Δlx_{t-i} + Σ b_i Δlrp_{t-i} + Σ g_i Δly_{t-i} + ay kuklaları + COVID kuklaları

- Uzun dönem esneklik = −θ/φ (delta yöntemi SE, HAC); pandemi sonrası (2021+) = −(θ+δ)/φ
- Gecikme uzunluğu AIC ile (≤6), eşbütünleşme Pesaran-Shin-Smith sınır testi
- Kısa dönem (etki) esneklikleri: b₀, g₀
- Zamana göre değişim: 60 aylık kayan pencere
- Panel: her sektörde bölgeler havuzlanmış ECM (ortak uzun dönem, bölge sabit etkisi)

**Sağlamlık – LP-IV (Jordà, kümülatif):** ufuk h için ihracattaki kümülatif değişim,
göreli fiyattaki kümülatif değişime regres edilir. Göreli fiyat Δln(USD/TRY) ve Δln(USD/EUR)
ile araçlanır.

## Veri

| Değişken | Kaynak |
|---|---|
| Sektör × ülke × ay ihracat (USD) | UN Comtrade (Türkiye beyanı, HS) |
| Sektör ihracat fiyatı | TÜİK SDMX, SITC Rev.4 ihracat birim değer endeksleri |
| Bölge reel geliri | Eurostat (AB çeyreklik GSYH), FRED (ABD GSYH), IMF WEO (diğerleri, yıllık) |
| Bölge fiyat düzeyi (USD) | IMF CPI ve kurlar, FRED EUR/USD |
| Araçlar | IMF (USD/TRY), FRED (EUR/USD) |

Bölge ağırlıkları: 2015–2019 Türkiye ihracat payları.

## Çalıştırma

```bash
pip install -r requirements.txt
export TUIK_API_KEY=...            # TÜİK veri portalı API anahtarı
python src/fetch_comtrade.py --codes 87,72 74,76 15,16 17,18 19,20 21,04 11,23 02
python src/fetch_macro.py
python src/build_panel.py
python src/estimate.py
python src/make_tables.py          # -> output/ihracat_esneklikleri_pilot.xlsx
```

## Pilot sınırlamaları

- Sektörler HS **fasıl** düzeyinde yaklaşık eşlenmiştir (C10, C24, C29). Tam sürüm için HS6 → CPA/NACE
  uyum tablosu ve Comtrade API anahtarı gerekir.
- Fiyat Türkiye geneli sektör fiyatıdır; bölgeye özel birim değer HS6 verisiyle eklenecek.
- MENA, BDT, Afrika geliri yıllık WEO verisinden aya interpole edilmiştir.
