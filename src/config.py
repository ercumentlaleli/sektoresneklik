"""Proje genel tanımları: dönem, bölgeler, sektörler, birim değer parametreleri."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUTPUT = ROOT / "output"

START, END = "2013-01", "2026-08"   # END: Comtrade'de son yayımlanan ay
POST_START = "2021-01"          # pandemi sonrası dönem başlangıcı
PRE_END = "2019-12"             # pandemi öncesi dönem sonu
COVID = ("2020-03", "2020-12")  # kukla ile kontrol edilen dönem

# --- Bölgeler (ISO3) -------------------------------------------------------
EU27 = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU",
        "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT",
        "ROU", "SVK", "SVN", "ESP", "SWE"]
USA = ["USA"]
# Dünya Bankası MENA tanımı (İsrail ve Malta hariç tutuldu: Malta AB'de; İsrail ayrı
# değerlendirilebilir ama WB tanımında var -> dahil). Türkiye raporlayıcı.
MENA = ["DZA", "BHR", "DJI", "EGY", "IRN", "IRQ", "ISR", "JOR", "KWT", "LBN", "LBY",
        "MAR", "OMN", "PSE", "QAT", "SAU", "SYR", "TUN", "ARE", "YEM"]
CIS = ["ARM", "AZE", "BLR", "GEO", "KAZ", "KGZ", "MDA", "RUS", "TJK", "TKM", "UKR", "UZB"]
OTHER_EUROPE = ["GBR", "CHE", "NOR", "ISL", "SRB", "BIH", "MKD", "ALB", "MNE", "XKX"]
SSA = ["AGO", "BEN", "BWA", "BFA", "BDI", "CPV", "CMR", "CAF", "TCD", "COM", "COD", "COG",
       "CIV", "GNQ", "ERI", "SWZ", "ETH", "GAB", "GMB", "GHA", "GIN", "GNB", "KEN", "LSO",
       "LBR", "MDG", "MWI", "MLI", "MRT", "MUS", "MOZ", "NAM", "NER", "NGA", "RWA", "STP",
       "SEN", "SYC", "SLE", "SOM", "ZAF", "SSD", "SDN", "TZA", "TGO", "UGA", "ZMB", "ZWE"]

REGIONS = {
    "AB-27": EU27,
    "ABD": USA,
    "MENA": MENA,
    "BDT": CIS,
    "Diğer Avrupa": OTHER_EUROPE,
    "Sahra Altı Afrika": SSA,
}
# Fiyat endeksinde resmi kur ile piyasa kuru çok ayrışan / verisi güvenilmez ülkeler
PRICE_EXCLUDE = ["IRN", "SYR", "LBN", "YEM", "LBY", "SDN", "SSD", "PSE", "XKX", "ERI", "SOM"]

# --- İmalat sektörleri: NACE Rev.2 bölümleri (C10–C33) ------------------------------
# HS6 → NACE eşlemesi src/concordance.py ile (data/ref/hs6_nace2.csv) kurulur.
# C33 (onarım ve kurulum) hizmet faaliyetidir; HS kapsamında mal ihracatı yoktur.
SECTORS = {
    "C10": "Gıda ürünleri", "C11": "İçecekler", "C12": "Tütün ürünleri", "C13": "Tekstil ürünleri",
    "C14": "Giyim eşyası", "C15": "Deri ve ilgili ürünler", "C16": "Ağaç ve mantar ürünleri",
    "C17": "Kâğıt ve kâğıt ürünleri", "C18": "Basım ve kayıt hizmetleri", "C19": "Kok ve rafine petrol",
    "C20": "Kimyasallar", "C21": "Temel eczacılık ürünleri", "C22": "Kauçuk ve plastik",
    "C23": "Diğer metalik olmayan mineral", "C24": "Ana metal", "C25": "Fabrikasyon metal",
    "C26": "Bilgisayar, elektronik ve optik", "C27": "Elektrikli teçhizat", "C28": "Makine ve ekipman",
    "C29": "Motorlu kara taşıtları", "C30": "Diğer ulaşım araçları", "C31": "Mobilya",
    "C32": "Diğer imalat", "C33": "Makine ve ekipman onarım ve kurulumu",
}

# --- Birim değer endeksi parametreleri --------------------------------------------
UV_MIN_VALUE = 5_000      # USD; bundan küçük HS6×ülke×ay işlemleri birim değerde kullanılmaz
UV_TRIM = 3.0             # TPD artığı |e| > UV_TRIM × sağlam std ise gözlem atılır
UV_MIN_ITEMS = 5          # ayda en az bu kadar eşleşen kalem yoksa endeks interpolasyonla doldurulur
