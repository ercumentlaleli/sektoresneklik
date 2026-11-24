"""Proje genel tanımları: bölgeler, pilot sektörler, HS ve SITC eşlemeleri."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUTPUT = ROOT / "output"

START, END = "2013-01", "2026-08"
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

# --- Pilot sektörler: NACE Rev.2 -> HS fasılları (Comtrade) -> SITC (TÜİK birim değer) --
# HS fasıl düzeyi yaklaşık eşlemedir; tam sürümde HS6 -> CPA/NACE uyum tablosu kullanılacak.
# Fiyat: fasılın karşılık geldiği SITC Rev.4 ihracat birim değer endeksi (TÜİK, USD, 2015=100);
# sektör fiyatı bu endekslerin Comtrade ihracat değeriyle ağırlıklı zincirleme Törnqvist'i.
SECTORS = {
    "C10": {"ad": "Gıda ürünleri",
            "hs": {"02": "01", "16": "01", "04": "02", "11": "04", "19": "04", "17": "06",
                   "18": "07", "23": "08", "20": "05", "21": "09", "15": "42"}},
    "C24": {"ad": "Ana metal",
            "hs": {"72": "67", "74": "68", "76": "68"}},
    "C29": {"ad": "Motorlu kara taşıtları",
            "hs": {"87": "78"}},
}
