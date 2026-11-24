"""Sektör × bölge × ay paneli.

Değişkenler (hepsi log, USD bazlı):
- lx   : reel ihracat = nominal ihracat / sektör ihracat fiyat endeksi
- lp   : sektör ihracat fiyatı (TÜİK SITC birim değer endeksleri, Comtrade değer ağırlıklı Törnqvist)
- (bölgeye özel fiyat: HS6 verisi gelince eklenecek; HS2 düzeyinde kg toplamı yok)
- lpf  : bölge fiyat düzeyi, USD (ülke TÜFE / kur, Türkiye ihracat ağırlıklı geometrik)
- lrp  : göreli fiyat = lp - lpf
- ly   : bölge reel geliri (AB/ABD: çeyreklik GSYH; diğerleri: WEO yıllık GSYH; aya interpole)
- lusd : USD/TRY, leur: USD per EUR (LP-IV araç değişkenleri)
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from config import END, PRICE_EXCLUDE, PROC, RAW, REGIONS, SECTORS, START  # noqa: E402

MONTHS = pd.period_range(START, END, freq="M")
EURO = {"AUT": 1999, "BEL": 1999, "CYP": 2008, "FIN": 1999, "FRA": 1999, "DEU": 1999, "GRC": 2001,
        "IRL": 1999, "ITA": 1999, "LUX": 1999, "MLT": 2008, "NLD": 1999, "PRT": 1999, "SVK": 2009,
        "SVN": 2007, "ESP": 1999, "EST": 2011, "LVA": 2014, "LTU": 2015, "HRV": 2023}


# ---------------------------------------------------------------- Comtrade
def load_comtrade():
    ref = json.load(open(RAW.parent / "ref" / "partnerAreas.json"))["results"]
    iso = {r["PartnerCode"]: r.get("PartnerCodeIsoAlpha3") for r in ref}
    rows = []
    for f in glob.glob(str(RAW / "comtrade" / "*.json")):
        for r in json.load(open(f)):
            rows.append((r["period"], r["partnerCode"], r["cmdCode"], r["primaryValue"], r["netWgt"]))
    d = pd.DataFrame(rows, columns=["period", "pcode", "hs", "value", "kg"]).drop_duplicates()
    d["iso"] = d.pcode.map(iso)
    d["date"] = pd.PeriodIndex(d.period.astype(str), freq="M")
    c2r = {c: r for r, cs in REGIONS.items() for c in cs}
    d["region"] = d.iso.map(c2r)
    return d


def tuik_uv():
    """TÜİK aylık SITC Rev.4 ihracat birim değer endeksleri (USD, 2015=100), log."""
    t = pd.read_csv(RAW / "macro" / "tuik_DF_IHRACAT_BIRIM_DEGER_V1.csv", low_memory=False)
    t = t[t.FREQ == "M"]
    t = t[t.SITC_REV4_205.astype(str) != "_Z"]
    u = t.pivot_table(index="TIME_PERIOD", columns=t.SITC_REV4_205.astype(str), values="OBS_VALUE")
    u.index = pd.PeriodIndex(u.index, freq="M")
    return np.log(u).reindex(MONTHS)


def sector_price(world, hs2sitc, luv):
    """Sektör ihracat fiyatı (log): SITC birim değer endekslerinin zincirleme Törnqvist'i.
    Ağırlıklar: Comtrade'de HS fasıllarının (SITC'ye eşlenmiş) dünya ihracat değeri payları."""
    w = world.assign(sitc=world.hs.map(hs2sitc)).pivot_table(
        index="date", columns="sitc", values="value", aggfunc="sum").reindex(MONTHS)
    s = w.div(w.sum(axis=1), axis=0)
    dl = luv[s.columns].diff()
    wb = (s + s.shift(1)) / 2
    ok = dl.notna() & wb.notna()
    wn = wb.where(ok)
    wn = wn.div(wn.sum(axis=1), axis=0)
    return (wn * dl.where(ok)).sum(axis=1, min_count=1).fillna(0.0).cumsum()


# ---------------------------------------------------------------- weights
def country_weights(d):
    """Bölge içi ülke ağırlıkları: 2015-2019 Türkiye ihracat payı (pilot fasılların toplamı)."""
    m = d[(d.date.dt.year >= 2015) & (d.date.dt.year <= 2019) & d.region.notna()]
    w = m.groupby(["region", "iso"]).value.sum()
    return w / w.groupby(level=0).transform("sum")


# ---------------------------------------------------------------- income
def monthly_from_quarterly(q: pd.Series) -> pd.Series:
    """Çeyreklik log seviye -> aylık (çeyrek ortası ayına yerleştir, doğrusal interpolasyon)."""
    idx = pd.PeriodIndex(q.index, freq="Q")
    mid = idx.asfreq("M", how="start") + 1
    s = pd.Series(np.log(q.values), index=mid)
    full = pd.period_range(min(mid.min(), MONTHS[0]), max(mid.max(), MONTHS[-1]), freq="M")
    return s.reindex(full).interpolate(limit_direction="both").reindex(MONTHS)


def monthly_from_annual(a: pd.Series) -> pd.Series:
    """Yıllık log seviye -> aylık (Haziran'a yerleştir, kübik interpolasyon)."""
    s = pd.Series(np.log(a.values), index=pd.PeriodIndex([f"{y}-06" for y in a.index], freq="M"))
    full = pd.period_range(s.index.min(), s.index.max(), freq="M")
    s = s.reindex(full)
    s.index = np.arange(len(s))
    s = s.interpolate(method="cubic")
    s.index = full
    return s.reindex(MONTHS)


def income(w):
    mac = RAW / "macro"
    weo = pd.read_csv(mac / "weo_ngdp_r.csv")
    weo["year"] = weo.TIME_PERIOD.astype(int)
    weo = weo.pivot_table(index="year", columns="COUNTRY", values="OBS_VALUE")
    out = {}
    for r in REGIONS:
        if r == "AB-27":
            q = pd.read_csv(mac / "eu_gdp_q.csv").set_index("date").value
            out[r] = monthly_from_quarterly(q)
        elif r == "ABD":
            f = pd.read_csv(mac / "fred.csv")[["date", "GDPC1"]].dropna()
            f["q"] = pd.PeriodIndex(pd.to_datetime(f.date), freq="Q")
            out[r] = monthly_from_quarterly(f.set_index("q").GDPC1)
        else:
            ws = w.loc[r]
            ws = ws[ws.index.isin(weo.columns)]
            g = np.log(weo[ws.index]).diff()          # ülke reel büyüme oranları
            ws = ws / ws.sum()
            gr = (g * ws).sum(axis=1, min_count=1)   # ağırlıklı bölge büyümesi
            lvl = np.exp(gr.loc[2006:2027].cumsum())
            out[r] = monthly_from_annual(lvl)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- partner prices
def partner_prices(w):
    mac = RAW / "macro"
    cpi = pd.read_csv(mac / "imf_cpi.csv")
    er = pd.read_csv(mac / "imf_er.csv")
    for t in (cpi, er):
        t["date"] = pd.PeriodIndex(t.TIME_PERIOD.str.replace("-M", "-"), freq="M")
    cpi = cpi.pivot_table(index="date", columns="COUNTRY", values="OBS_VALUE")
    er = er.pivot_table(index="date", columns="COUNTRY", values="OBS_VALUE")
    full = pd.period_range("2010-01", END, freq="M")
    cpi, er = cpi.reindex(full), er.reindex(full)
    f = pd.read_csv(mac / "fred.csv")[["date", "DEXUSEU"]].dropna()
    f["m"] = pd.PeriodIndex(pd.to_datetime(f.date), freq="M")
    usd_per_eur = f.groupby("m").DEXUSEU.mean().reindex(full)
    eur_per_usd = 1 / usd_per_eur
    for c, y in EURO.items():
        s = er[c] if c in er else pd.Series(np.nan, index=full)
        # euro sonrası: EUR/USD × (son ulusal kur / o tarihteki EUR/USD) — süreklilik için
        last = s.dropna()
        if len(last):
            k = last.index.max()
            ratio = last.iloc[-1] / eur_per_usd[k]
            s = s.where(s.notna(), eur_per_usd * ratio)
        else:
            s = eur_per_usd
        er[c] = s
    pusd = np.log(cpi) - np.log(er)  # ülke fiyat düzeyi, USD
    dp = pusd.diff()
    out = {}
    for r in REGIONS:
        ws = w.loc[r]
        ws = ws[ws.index.isin(dp.columns) & ~ws.index.isin(PRICE_EXCLUDE)]
        sub = dp[ws.index]
        # aylık |Δ| > %30 değerleri (devalüasyon/veri hatası) kırp
        sub = sub.where(sub.abs() < 0.3)
        wm = pd.DataFrame(np.tile(ws.values, (len(sub), 1)), index=sub.index, columns=ws.index).where(sub.notna())
        wm = wm.div(wm.sum(axis=1), axis=0)
        out[r] = (sub * wm).sum(axis=1, min_count=1).fillna(0).cumsum()
    return pd.DataFrame(out).reindex(MONTHS)


def fx():
    mac = RAW / "macro"
    er = pd.read_csv(mac / "imf_er.csv")
    er = er[er.COUNTRY == "TUR"].copy()
    er["date"] = pd.PeriodIndex(er.TIME_PERIOD.str.replace("-M", "-"), freq="M")
    lusd = np.log(er.set_index("date").OBS_VALUE).reindex(MONTHS)
    f = pd.read_csv(mac / "fred.csv")[["date", "DEXUSEU", "DCOILBRENTEU"]]
    f["m"] = pd.PeriodIndex(pd.to_datetime(f.date), freq="M")
    g = f.groupby("m")[["DEXUSEU", "DCOILBRENTEU"]].mean().reindex(MONTHS)
    return pd.DataFrame({"lusd": lusd, "leur": np.log(g.DEXUSEU), "loil": np.log(g.DCOILBRENTEU)})


def main():
    PROC.mkdir(parents=True, exist_ok=True)
    d = load_comtrade()
    w = country_weights(d)
    w.rename("weight").to_csv(PROC / "country_weights.csv")
    Y = income(w)
    PF = partner_prices(w)
    FX = fx()
    luv = tuik_uv()
    rows = []
    for s, meta in SECTORS.items():
        hs = list(meta["hs"])
        ds = d[d.hs.isin(hs)]
        months_per_hs = ds[ds.pcode == 0].groupby("hs").date.nunique().reindex(hs).fillna(0)
        if (months_per_hs < len(MONTHS) - 3).any():
            print(f"{s}: veri eksik, atlandı ->", months_per_hs.astype(int).to_dict())
            continue
        lp = sector_price(ds[ds.pcode == 0], meta["hs"], luv)
        for r in REGIONS:
            dr = ds[ds.region == r]
            v = dr.groupby("date").value.sum().reindex(MONTHS)
            p = pd.DataFrame({"sector": s, "region": r, "date": MONTHS,
                              "lv": np.log(v.values), "lp": lp.values,
                              "lpf": PF[r].values, "ly": Y[r].values})
            p = pd.concat([p, FX.reset_index(drop=True)], axis=1)
            p["lx"] = p.lv - p.lp
            p["lrp"] = p.lp - p.lpf
            rows.append(p)
    panel = pd.concat(rows, ignore_index=True)
    panel["date"] = panel.date.astype(str)
    panel.to_csv(PROC / "panel.csv", index=False)
    print(panel.groupby(["sector", "region"]).agg(n=("lx", "count"), lv_mean=("lv", "mean")).round(2))


if __name__ == "__main__":
    main()
