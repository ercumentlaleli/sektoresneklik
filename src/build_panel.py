"""Sektör (NACE Rev.2, C10–C33) × bölge × ay paneli.

Değişkenler (hepsi log, USD bazlı):
- lv   : nominal ihracat (Comtrade HS6 × ülke, HS6 → NACE eşlemesiyle sektöre toplanmış)
- lp   : bölgeye özel sektör ihracat birim değer endeksi (kilogram başına USD; ağırlıklı
         zaman-ürün kuklası (TPD) regresyonu, kalem = HS6 × varış ülkesi)
- lx   : reel ihracat = lv - lp
- lpf  : bölge fiyat düzeyi, USD (ülke TÜFE / kur, Türkiye ihracat ağırlıklı geometrik)
- lrp  : göreli fiyat = lp - lpf
- ly   : bölge reel geliri (AB/ABD: çeyreklik GSYH; diğerleri: WEO yıllık GSYH; aya interpole)
- lusd : USD/TRY, leur: USD per EUR, loil: Brent (LP-IV araç değişkenleri / kontroller)
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from config import (END, PRICE_EXCLUDE, PROC, RAW, REGIONS, SECTORS, START,  # noqa: E402
                    UV_MIN_ITEMS, UV_MIN_VALUE, UV_TRIM)
from fetch_comtrade import partner_codes  # noqa: E402

MONTHS = pd.period_range(START, END, freq="M")
EURO = {"AUT": 1999, "BEL": 1999, "CYP": 2008, "FIN": 1999, "FRA": 1999, "DEU": 1999, "GRC": 2001,
        "IRL": 1999, "ITA": 1999, "LUX": 1999, "MLT": 2008, "NLD": 1999, "PRT": 1999, "SVK": 2009,
        "SVN": 2007, "ESP": 1999, "EST": 2011, "LVA": 2014, "LTU": 2015, "HRV": 2023}


# ---------------------------------------------------------------- Comtrade HS6
def load_comtrade():
    """HS6 × ülke × ay ihracatı; NACE bölümü ve bölge eklenmiş. Dünya (partner 0) ayrı döner."""
    files = sorted(glob.glob(str(RAW / "comtrade_hs6" / "*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    d = d.drop_duplicates(["period", "partnerCode", "cmdCode"])
    d = d[d.cmdCode.str.len() == 6]
    conc = pd.read_csv(RAW.parent / "ref" / "hs6_nace2.csv", dtype=str)
    conc["sector"] = "C" + conc.nace2
    d = d.merge(conc[["hs_rev", "hs6", "sector"]], left_on=["classificationCode", "cmdCode"],
                right_on=["hs_rev", "hs6"], how="left").drop(columns=["hs_rev", "hs6"])
    code2iso = {v: k for k, v in partner_codes().items()}
    c2r = {c: r for r, cs in REGIONS.items() for c in cs}
    d["iso"] = d.partnerCode.map(code2iso)
    d["region"] = d.iso.map(c2r)
    d["date"] = pd.PeriodIndex(d.period, freq="M")
    d = d[(d.date >= MONTHS[0]) & (d.date <= MONTHS[-1])]
    world = d[d.partnerCode == 0]
    d = d[d.region.notna()]
    return d, world


def coverage_report(d, world):
    """Eşleme kapsamı: dünya ihracatının imalat sektörlerine atanan payı, çok-bölümlü HS6 payı."""
    conc = pd.read_csv(RAW.parent / "ref" / "hs6_nace2.csv", dtype=str)
    multi = set(zip(conc.hs_rev[conc.n_div.astype(int) > 1], conc.hs6[conc.n_div.astype(int) > 1]))
    w = world.assign(year=world.date.dt.year,
                     manuf=world.sector.isin(SECTORS),
                     multi=[(a, b) in multi for a, b in zip(world.classificationCode, world.cmdCode)])
    tot = w.groupby("year").primaryValue.sum()
    rep = pd.DataFrame({
        "dunya_ihracat_mlr_usd": tot / 1e9,
        "imalat_payi": w[w.manuf].groupby("year").primaryValue.sum() / tot,
        "cok_bolumlu_hs6_payi": w[w.multi].groupby("year").primaryValue.sum() / tot,
        "bolgeler_payi": d.assign(year=d.date.dt.year).groupby("year").primaryValue.sum() / tot,
        "kg_mevcut_payi": w[w.netWgt > 0].groupby("year").primaryValue.sum() / tot,
    })
    return rep


# ---------------------------------------------------------------- unit value index
def tpd(item, t, y, w, T, iters=500, tol=1e-9):
    """Ağırlıklı zaman-ürün kuklası: y_it = a_i + d_t + e_it, ağırlık w (ay içi değer payı).
    Değişen yönlerde ortalama alma (alternating projections). d_0 = 0 normalizasyonu."""
    a = np.zeros(item.max() + 1)
    dlt = np.zeros(T)
    sw_i = np.bincount(item, w, len(a))
    sw_t = np.bincount(t, w, T)
    for _ in range(iters):
        a = np.bincount(item, w * (y - dlt[t]), len(a)) / np.where(sw_i > 0, sw_i, 1)
        new = np.bincount(t, w * (y - a[item]), T) / np.where(sw_t > 0, sw_t, 1)
        if np.max(np.abs(new - dlt)) < tol:
            dlt = new
            break
        dlt = new
    return a, dlt


def unit_value_index(g):
    """Bir sektör × bölge için aylık log birim değer endeksi (2015 ortalaması = 0).
    Kalem: HS6 kodu × varış ülkesi. Birim değer = USD / net kg."""
    g = g[(g.netWgt > 0) & (g.primaryValue >= UV_MIN_VALUE) & ~g.isNetWgtEstimated.fillna(False)]
    if g.empty:
        return pd.Series(np.nan, index=MONTHS), 0
    item = pd.factorize(g.cmdCode + "_" + g.iso)[0]
    t = ((g.date.dt.year - MONTHS[0].year) * 12 + g.date.dt.month - MONTHS[0].month).to_numpy()
    y = np.log(g.primaryValue.to_numpy() / g.netWgt.to_numpy())
    v = g.primaryValue.to_numpy()
    w = v / np.bincount(t, v, len(MONTHS))[t]
    T = len(MONTHS)
    keep = np.ones(len(y), bool)
    for _ in range(2):  # artıklara göre aykırı değer kırpma, yeniden tahmin
        a, dl = tpd(item[keep], t[keep], y[keep], w[keep], T)
        e = y - a[item] - dl[t]
        e[~keep] = 0
        mad = 1.4826 * np.median(np.abs(e[keep]))
        keep = np.abs(e) <= UV_TRIM * max(mad, 1e-6)
    a, dl = tpd(item[keep], t[keep], y[keep], w[keep], T)
    # tek dönemlik kalemler endeksi tanımlamaz; ay başına "köprülenmiş" kalem sayısı
    multi = np.bincount(item[keep], minlength=item.max() + 1) > 1
    n_t = np.bincount(t[keep][multi[item[keep]]], minlength=T)
    s = pd.Series(dl, index=MONTHS).where(n_t >= UV_MIN_ITEMS)
    s = s.interpolate(limit_area="inside")
    base = s[s.index.year == 2015]
    s = s - (base.mean() if base.notna().any() else s.mean())
    return s, int(np.median(n_t[n_t > 0])) if (n_t > 0).any() else 0


# ---------------------------------------------------------------- weights
def country_weights(d):
    """Bölge içi ülke ağırlıkları: 2015-2019 Türkiye imalat ihracatı payı."""
    m = d[(d.date.dt.year >= 2015) & (d.date.dt.year <= 2019) & d.sector.isin(SECTORS)]
    if m.region.nunique() < len(REGIONS):  # 2015-2019 henüz indirilmemişse (test) tüm dönem
        print("UYARI: 2015-2019 verisi eksik, ülke ağırlıkları tüm dönemden")
        m = d[d.sector.isin(SECTORS)]
    w = m.groupby(["region", "iso"]).primaryValue.sum()
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
    d, world = load_comtrade()
    rep = coverage_report(d, world)
    rep.round(4).to_csv(PROC / "coverage.csv")
    print(rep.round(3))
    w = country_weights(d)
    w.rename("weight").to_csv(PROC / "country_weights.csv")
    Y, PF, FX = income(w), partner_prices(w), fx()
    d = d[d.sector.isin(SECTORS)]
    rows, uvinfo = [], []
    for (s, r), g in d.groupby(["sector", "region"], sort=True):
        v = g.groupby("date").primaryValue.sum().reindex(MONTHS)
        lp, nitems = unit_value_index(g)
        if nitems < UV_MIN_ITEMS:  # birim değer endeksi için yetersiz kalem -> hücre modele girmez
            lp[:] = np.nan
        uvinfo.append({"sector": s, "region": r, "medyan_kalem": nitems,
                       "ihracat_2015_19_mn_usd": g[(g.date.dt.year >= 2015) & (g.date.dt.year <= 2019)]
                       .primaryValue.sum() / 5e6,
                       "uv_eksik_ay": int(lp.isna().sum())})
        p = pd.DataFrame({"sector": s, "region": r, "date": MONTHS,
                          "lv": np.log(v.where(v > 0)).values, "lp": lp.values,
                          "lpf": PF[r].values, "ly": Y[r].values})
        p = pd.concat([p, FX.reset_index(drop=True)], axis=1)
        p["lx"] = p.lv - p.lp
        p["lrp"] = p.lp - p.lpf
        rows.append(p)
    panel = pd.concat(rows, ignore_index=True)
    panel["date"] = panel.date.astype(str)
    panel.to_csv(PROC / "panel.csv", index=False)
    info = pd.DataFrame(uvinfo)
    info.round(1).to_csv(PROC / "uv_index_info.csv", index=False)
    print(info.pivot(index="sector", columns="region", values="medyan_kalem"))


if __name__ == "__main__":
    main()
