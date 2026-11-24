"""HS6 → CPA 2.1 / NACE Rev.2 bölüm (2 hane) uyum tablosu.

Zincir (UNSD resmi uyum tabloları, data/ref/concordance/):
  HS2012 (H4) ──────────────────────────────┐
  HS2017 (H5) ──────────────────────────────┼─> CPC Ver.2.1 ─> ISIC Rev.4 ─> NACE Rev.2
  HS2022 (H6) ─> HS2017 (WCO/UNSD dönüşüm) ─┘
CPA 2.1, CPC 2.1'den türetilmiştir ve ilk iki hanesi NACE Rev.2 bölümüdür; dolayısıyla
HS6 → CPC 2.1 → NACE Rev.2 bölümü, HS6 → CPA 2.1 bölümüyle aynı sonucu verir.

Bir HS6 kodu birden fazla NACE bölümüne düşerse (kısmi eşleşmeler), kod en çok CPC
alt sınıfının bağlandığı bölüme atanır (eşitlikte küçük kod). Çok-bölümlü kodlar
`n_div > 1` ile işaretlenir; payları build_panel.py'de raporlanır.

Çıktı: data/ref/hs6_nace2.csv  (hs_rev, hs6, nace2, n_div)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from config import RAW  # noqa: E402

REF = RAW.parent / "ref"
CON = REF / "concordance"
MANUF = [f"{i:02d}" for i in range(10, 34)]  # C10–C33


def _hs(s):
    return s.astype(str).str.replace(".", "", regex=False).str.zfill(6)


def cpc_to_nace():
    c2i = pd.read_csv(CON / "cpc21-isic4.txt", dtype=str)
    i2n = pd.read_csv(CON / "ISIC4_NACE2.txt", dtype=str)
    i2n = i2n[i2n.ISIC4code.str.len() == 4]
    c2i = c2i[c2i.ISIC4code.str.fullmatch(r"\d+")]  # "n/a": üreten sanayi yok (ör. hurda)
    c2i["isic4"] = c2i.ISIC4code.str.zfill(4)
    m = c2i.merge(i2n, left_on="isic4", right_on="ISIC4code", how="left")
    # NACE kodu "10.11" biçiminde; bölüm = ilk iki hane. Eksikse ISIC bölümü (bölüm düzeyinde aynıdır).
    m["nace2"] = m.NACE2code.str[:2].fillna(m.isic4.str[:2])
    return m[["CPC21code", "nace2"]].rename(columns={"CPC21code": "cpc"}).drop_duplicates()


def hs_to_cpc():
    a = pd.read_csv(CON / "cpc21-hs2012.txt", dtype=str)
    a = pd.DataFrame({"hs_rev": "H4", "hs6": _hs(a.HS12code), "cpc": a.CPC21code})
    b = pd.read_csv(CON / "CPC21-HS2017.csv", dtype=str)
    b = pd.DataFrame({"hs_rev": "H5", "hs6": _hs(b["HS 2017"]), "cpc": b["CPC Ver. 2.1"].str.zfill(5)})
    conv = pd.read_excel(CON / "HS2022toHS2017ConversionAndCorrelationTables.xlsx",
                         sheet_name="HS2022-HS2017 Conversions", dtype=str)
    conv = pd.DataFrame({"hs6": _hs(conv["From HS2022"]), "hs17": _hs(conv["To HS2017"])})
    c = conv.merge(b[["hs6", "cpc"]].rename(columns={"hs6": "hs17"}), on="hs17")
    c = pd.DataFrame({"hs_rev": "H6", "hs6": c.hs6, "cpc": c.cpc})
    return pd.concat([a, b, c], ignore_index=True)


def build():
    m = hs_to_cpc().merge(cpc_to_nace(), on="cpc", how="left")
    m = m.dropna(subset=["nace2"])
    cnt = m.groupby(["hs_rev", "hs6", "nace2"]).size().rename("k").reset_index()
    cnt = cnt.sort_values(["hs_rev", "hs6", "k", "nace2"], ascending=[True, True, False, True])
    ndiv = cnt.groupby(["hs_rev", "hs6"]).nace2.nunique().rename("n_div")
    out = cnt.drop_duplicates(["hs_rev", "hs6"]).drop(columns="k").merge(ndiv, on=["hs_rev", "hs6"])
    out.to_csv(REF / "hs6_nace2.csv", index=False)
    return out


if __name__ == "__main__":
    t = build()
    print(t.groupby("hs_rev").agg(n=("hs6", "size"), imalat=("nace2", lambda s: s.isin(MANUF).sum()),
                                  cok_bolum=("n_div", lambda s: (s > 1).sum())))
    print(t[t.nace2.isin(MANUF)].groupby("nace2").size().to_dict())
