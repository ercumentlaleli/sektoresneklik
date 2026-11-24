"""Excel çıktısı: panel ECM esneklik tabloları (sektör × bölge), dönem karşılaştırması,
sağlamlık (hücre ARDL, LP-IV), kayan pencere, veri kapsamı ve notlar."""
import os
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(__file__))
from config import OUTPUT, PROC, REGIONS, SECTORS  # noqa: E402
from estimate import POOLED, TOTAL, stars  # noqa: E402

COLS = list(REGIONS) + [POOLED]
ROWS = list(SECTORS) + [TOTAL]
NO_GOODS = {"C33"}


def fmt(v, se):
    return "" if pd.isna(v) else f"{v:.2f}{stars(v / se)}"


def label(s):
    return f"{s} {SECTORS[s]}" if s in SECTORS else s


def grid(res, f, mark=None):
    """Satır: sektör, sütun: bölge. f(row) -> hücre metni."""
    out = []
    for s in ROWS:
        row = {"Sektör": label(s)}
        for r in COLS:
            q = res[(res.sector == s) & (res.region == r)]
            if s in NO_GOODS:
                row[r] = "mal ihracatı yok"
            elif q.empty:
                row[r] = "" if (s == TOTAL and r == POOLED) else "veri yetersiz"
            else:
                row[r] = f(q.iloc[0]) + (mark(q.iloc[0]) if mark else "")
        out.append(row)
    return pd.DataFrame(out)


def full(tag):
    return lambda x: fmt(x[f"{tag}_full"], x[f"{tag}_full_se"])


def prepost(tag):
    def f(x):
        d = "‡" if abs(x[f"{tag}_diff_t"]) > 1.96 else ""
        return (f"{fmt(x[f'{tag}_pre'], x[f'{tag}_pre_se'])} → "
                f"{fmt(x[f'{tag}_post'], x[f'{tag}_post_se'])}{d}")
    return f


def detail(res):
    keep = ["sector", "region", "lag", "n", "r2",
            "p_full", "p_full_se", "p_pre", "p_pre_se", "p_post", "p_post_se", "p_diff_t",
            "y_full", "y_full_se", "y_pre", "y_pre_se", "y_post", "y_post_se", "y_diff_t",
            "p_sr", "p_sr_se", "y_sr", "y_sr_se", "phi", "phi_t", "phi_post"]
    extra = [c for c in ["bounds_F", "bounds_t", "coint"] if c in res]
    names = {"sector": "Sektör", "region": "Bölge", "lag": "Gecikme (AIC)", "n": "Gözlem",
             "r2": "Düz. R²", "p_full": "Fiyat UD tüm", "p_pre": "Fiyat UD öncesi",
             "p_post": "Fiyat UD sonrası", "p_diff_t": "Fiyat fark t", "y_full": "Gelir UD tüm",
             "y_pre": "Gelir UD öncesi", "y_post": "Gelir UD sonrası", "y_diff_t": "Gelir fark t",
             "p_sr": "Fiyat KD (etki)", "y_sr": "Gelir KD (etki)", "phi": "Uyarlanma hızı φ",
             "phi_t": "φ t", "phi_post": "φ (etkileşimli model)", "bounds_F": "PSS F",
             "bounds_t": "PSS t", "coint": "Eşbütünleşme"}
    d = res[keep + extra].copy()
    d.columns = [names.get(c, c.replace("_se", " SE").replace("p_", "Fiyat ").replace("y_", "Gelir "))
                 for c in d.columns]
    return d.round(3)


def lp_sheet(lp, h=12):
    rows = []
    for (s, r), g in lp.groupby(["sector", "region"], sort=False):
        x, x0 = g[g.h == h].iloc[0], g[g.h == 0].iloc[0]
        rows.append({"Sektör": s, "Bölge": r,
                     "Fiyat h=0": fmt(x0.p, x0.p_se), f"Fiyat h={h}": fmt(x.p, x.p_se),
                     f"Gelir h={h}": fmt(x.y, x.y_se),
                     "1. aşama F (h=0)": round(x0.fs_F, 1), f"1. aşama F (h={h})": round(x.fs_F, 1)})
    return pd.DataFrame(rows)


NOTES = [
    "ANA SONUÇ: Panel hata düzeltme modeli (ECM). Her sektörde 6 bölge havuzlanır; uzun dönem fiyat ve gelir "
    "katsayıları bölgeye özel, uyarlanma hızı (φ), kısa dönem dinamikleri ve mevsimsellik ortaktır.",
    "Değerler uzun dönem esnekliklerdir (−θ/φ, delta yöntemi); *** %1, ** %5, * %10. Standart hatalar ay "
    "bazında kümelenmiştir (bölgeler arası eşanlı şoklara dayanıklı).",
    "‘Panel ortalaması’: aynı sektörde tüm bölgeler için ortak uzun dönem katsayısı. ‘Tüm imalat’: bölge "
    "içinde 23 sektör havuzlanmış, sektör sabit etkili, ortak katsayılı model.",
    "Dönem sayfaları: Pandemi öncesi (2013–2020, 2020 COVID kuklalı) → Pandemi sonrası (2021–2026/08); "
    "tek modelde 2021+ etkileşim terimleriyle. ‡: fark %5'te anlamlı.",
    "Fiyat esnekliği: reel ihracatın göreli fiyata (bölgeye özel sektör ihracat birim değeri / bölge fiyat "
    "düzeyi, USD) esnekliği; beklenen işaret negatif. Gelir esnekliği: bölge reel GSYH'sine; beklenen pozitif.",
    "Birim değer endeksi: Comtrade HS6 × ülke × ay, USD/kg; ağırlıklı zaman-ürün kuklası (TPD) regresyonu, "
    "kalem = HS6 × varış ülkesi; aykırı değerler kırpılmıştır. Reel ihracat = nominal ihracat / bu endeks.",
    "Kg temelli birim değerler kalite ve bileşim değişimine duyarlıdır (özellikle C21, C26, C30, C32); bu "
    "sektörlerde fiyat esnekliği temkinle yorumlanmalı. Ortak ölçüm hatası fiyat esnekliğini negatife çekebilir; "
    "LP-IV (kur araçları) bu yanlılığa karşı sağlamlık sağlar.",
    "C33 (onarım ve kurulum) hizmet faaliyetidir; HS kapsamında mal ihracatı yoktur.",
    "Sektör eşlemesi: HS6 → CPC 2.1 → ISIC Rev.4 → NACE Rev.2 (UNSD resmi tabloları; HS2022 kodları HS2017'ye "
    "dönüştürülerek). CPA 2.1 bölümleri NACE Rev.2 bölümleriyle aynıdır.",
    "Kaynaklar: UN Comtrade (Türkiye ihracatı, HS6 × ülke × ay), IMF WEO/CPI/ER, Eurostat, FRED.",
]


def style(ws, widths, freeze="B2"):
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
    ws.freeze_panes = freeze


def main():
    res = pd.read_csv(OUTPUT / "panel_ecm_results.csv")
    ardl = pd.read_csv(OUTPUT / "ardl_cell_results.csv")
    lp = pd.read_csv(OUTPUT / "lp_iv.csv")
    roll = pd.read_csv(OUTPUT / "panel_rolling.csv")
    cov = pd.read_csv(PROC / "coverage.csv")
    uv = pd.read_csv(PROC / "uv_index_info.csv")
    dag = lambda x: "" if x.coint == "evet" else " †"  # noqa: E731
    sheets = {
        "Fiyat esnekliği": grid(res, full("p")),
        "Gelir esnekliği": grid(res, full("y")),
        "Fiyat öncesi→sonrası": grid(res, prepost("p")),
        "Gelir öncesi→sonrası": grid(res, prepost("y")),
        "Panel ECM ayrıntı": detail(res),
        "ARDL hücre fiyat": grid(ardl, full("p"), dag).drop(columns=POOLED),
        "ARDL hücre gelir": grid(ardl, full("y"), dag).drop(columns=POOLED),
        "ARDL hücre ayrıntı": detail(ardl),
        "LP-IV": lp_sheet(lp),
        "LP-IV tüm ufuklar": lp.round(3),
        "Kayan pencere (60 ay)": roll.round(3),
        "Veri kapsamı": cov.round(3),
        "Birim değer endeksi": uv,
        "Notlar": pd.DataFrame({"Notlar": NOTES}),
    }
    path = OUTPUT / "ihracat_esneklikleri.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    wb = load_workbook(path)
    for name in list(sheets)[:4] + ["ARDL hücre fiyat", "ARDL hücre gelir"]:
        ws = wb[name]
        style(ws, [38] + [20] * len(COLS))
        r0 = ws.max_row + 2
        notes = NOTES if not name.startswith("ARDL") else [
            "Sağlamlık: hücre bazında ARDL-ECM (AIC gecikme ≤6, HAC SE). † : Pesaran-Shin-Smith sınır testi "
            "eşbütünleşmeyi %5'te doğrulamıyor."] + NOTES[4:]
        for i, n in enumerate(notes):
            ws.cell(row=r0 + i, column=1, value=n).font = Font(italic=True, size=9)
    for name in ["Panel ECM ayrıntı", "ARDL hücre ayrıntı", "LP-IV"]:
        style(wb[name], [12, 20] + [13] * 30)
    wb["Notlar"].column_dimensions["A"].width = 160
    wb.save(path)
    print("yazıldı:", path)


if __name__ == "__main__":
    main()
