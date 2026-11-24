"""Excel çıktısı: fiyat ve gelir esnekliği tabloları (bölge × NACE 2'li), tanı ve sağlamlık sayfaları."""
import os
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

sys.path.insert(0, os.path.dirname(__file__))
from config import OUTPUT, REGIONS, SECTORS  # noqa: E402
from estimate import stars  # noqa: E402

COLS = [f"{s} {m['ad']}" for s, m in SECTORS.items()]


def cell(r, tag, per):
    v, se = r[f"{tag}_{per}"], r[f"{tag}_{per}_se"]
    return f"{v:.2f}{stars(v / se)}"


def main_table(res, tag):
    rows = []
    for reg in list(REGIONS) + ["Panel (tüm bölgeler)"]:
        row = {"Bölge": reg}
        for s, m in SECTORS.items():
            q = res[(res.region == reg) & (res.sector == s)]
            if q.empty:
                row[f"{s} {m['ad']}"] = "veri bekleniyor"
                continue
            r = q.iloc[0]
            flag = "" if r.coint in ("evet", "panel") else " †"
            row[f"{s} {m['ad']}"] = (f"{cell(r, tag, 'full')} | {cell(r, tag, 'pre')} | "
                                     f"{cell(r, tag, 'post')}{flag}")
        rows.append(row)
    return pd.DataFrame(rows)


def long_sheet(res):
    keep = ["sector", "region", "lag", "n", "r2",
            "p_full", "p_full_se", "p_pre", "p_pre_se", "p_post", "p_post_se", "p_diff_t",
            "y_full", "y_full_se", "y_pre", "y_pre_se", "y_post", "y_post_se", "y_diff_t",
            "p_sr", "p_sr_se", "y_sr", "y_sr_se", "phi", "phi_t", "phi_post",
            "bounds_F", "bounds_t", "coint"]
    names = {"sector": "Sektör", "region": "Bölge", "lag": "Gecikme (AIC)", "n": "Gözlem",
             "r2": "Düz. R²", "p_full": "Fiyat UD tüm", "p_pre": "Fiyat UD öncesi",
             "p_post": "Fiyat UD sonrası", "p_diff_t": "Fiyat fark t", "y_full": "Gelir UD tüm",
             "y_pre": "Gelir UD öncesi", "y_post": "Gelir UD sonrası", "y_diff_t": "Gelir fark t",
             "p_sr": "Fiyat KD (etki)", "y_sr": "Gelir KD (etki)", "phi": "Uyarlanma hızı φ",
             "phi_t": "φ t", "phi_post": "φ (etkileşimli model)", "bounds_F": "PSS F",
             "bounds_t": "PSS t", "coint": "Eşbütünleşme"}
    d = res[keep].copy()
    d.columns = [names.get(c, c.replace("_se", " SE").replace("p_", "Fiyat ").replace("y_", "Gelir "))
                 for c in d.columns]
    return d.round(3)


def lp_sheet(lp, h=12):
    rows = []
    for (s, r), g in lp.groupby(["sector", "region"], sort=False):
        x = g[g.h == h].iloc[0]
        x0 = g[g.h == 0].iloc[0]
        rows.append({"Sektör": s, "Bölge": r,
                     "Fiyat h=0": f"{x0.p:.2f}{stars(x0.p / x0.p_se)}",
                     f"Fiyat h={h}": f"{x.p:.2f}{stars(x.p / x.p_se)}",
                     f"Gelir h={h}": f"{x.y:.2f}{stars(x.y / x.y_se)}",
                     "1. aşama F (h=0)": round(x0.fs_F, 1), f"1. aşama F (h={h})": round(x.fs_F, 1)})
    return pd.DataFrame(rows)


NOTES = [
    "Hücre biçimi: Tüm dönem (2013–2026) | Pandemi öncesi (2013–2020, 2020 COVID kuklalı) | Pandemi sonrası (2021–2026).",
    "Değerler ARDL hata düzeltme modelinden uzun dönem esnekliklerdir; *** %1, ** %5, * %10 anlamlılık (HAC standart hatalar, delta yöntemi).",
    "† : Pesaran-Shin-Smith sınır testi eşbütünleşmeyi %5'te doğrulamıyor; uzun dönem katsayısı temkinle yorumlanmalı.",
    "Fiyat esnekliği: reel ihracatın göreli fiyata (sektör ihracat birim değeri / bölge fiyat düzeyi, USD) esnekliği; beklenen işaret negatif.",
    "Gelir esnekliği: reel ihracatın bölge reel GSYH'sine esnekliği (Türkiye ihracat ağırlıklı); beklenen işaret pozitif.",
    "Pandemi öncesi/sonrası değerler tek modelde 2021+ etkileşim terimleriyle tahmin edilmiştir (ortak uyarlanma hızı).",
    "PİLOT: Sektörler HS fasıl düzeyinde yaklaşık eşlenmiştir (C10: HS 02,04,11,15-21,23; C24: HS 72,74,76; C29: HS 87).",
    "Kaynaklar: UN Comtrade (Türkiye ihracatı, ülke×HS×ay), TÜİK (SITC ihracat birim değer endeksleri), IMF WEO/CPI/ER, Eurostat, FRED.",
]


def style(ws, widths):
    thin = Side(style="thin", color="BBBBBB")
    hdr = PatternFill("solid", fgColor="1F3864")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = hdr
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            c.alignment = Alignment(horizontal="center", vertical="center")
        row[0].font = Font(bold=True)
        row[0].alignment = Alignment(horizontal="left")
    for i, w in enumerate(widths[:ws.max_column]):
        ws.column_dimensions[get_column_letter(i + 1)].width = w
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2"


def main():
    res = pd.read_csv(OUTPUT / "ecm_results.csv")
    lp = pd.read_csv(OUTPUT / "lp_iv.csv")
    roll = pd.read_csv(OUTPUT / "rolling.csv")
    path = OUTPUT / "ihracat_esneklikleri_pilot.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        main_table(res, "p").to_excel(xw, sheet_name="Fiyat esnekliği", index=False)
        main_table(res, "y").to_excel(xw, sheet_name="Gelir esnekliği", index=False)
        long_sheet(res).to_excel(xw, sheet_name="Ayrıntı ve tanı", index=False)
        lp_sheet(lp).to_excel(xw, sheet_name="LP-IV", index=False)
        lp.round(3).to_excel(xw, sheet_name="LP-IV tüm ufuklar", index=False)
        roll.round(3).to_excel(xw, sheet_name="Kayan pencere (60 ay)", index=False)
        pd.DataFrame({"Notlar": NOTES}).to_excel(xw, sheet_name="Notlar", index=False)
    wb = load_workbook(path)
    for name in ["Fiyat esnekliği", "Gelir esnekliği"]:
        ws = wb[name]
        style(ws, [20] + [34] * len(SECTORS))
        r0 = ws.max_row + 2
        for i, n in enumerate(NOTES):
            ws.cell(row=r0 + i, column=1, value=n).font = Font(italic=True, size=9)
    for name in ["Ayrıntı ve tanı", "LP-IV"]:
        style(wb[name], [10, 18] + [13] * 30)
    wb["Notlar"].column_dimensions["A"].width = 140
    wb.save(path)
    print("yazıldı:", path)


if __name__ == "__main__":
    main()
