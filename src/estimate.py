"""İhracat talep esneklikleri.

ANA MODEL – Panel ECM (her sektörde bölgeler havuzlanmış, i = bölge):
  Δlx_it = μ_i + φ·lx_i,t-1 + θp_i·lrp_i,t-1 + θy_i·ly_i,t-1
           [+ D_post·(μ2_i + δp_i·lrp_i,t-1 + δy_i·ly_i,t-1)]
           + Σ a_k Δlx_i,t-k + Σ b_k Δlrp_i,t-k + Σ g_k Δly_i,t-k + ay kuklaları + COVID kuklaları + ε
  - Bölgeye özel uzun dönem: fiyat −θp_i/φ, gelir −θy_i/φ (delta yöntemi)
  - Ortak: uyarlanma hızı φ, kısa dönem dinamikleri, mevsimsellik (verimlilik kazancı)
  - Pandemi sonrası (2021+) uzun dönem: −(θ_i+δ_i)/φ
  - Standart hatalar ay bazında kümelenmiş (bölgeler arası eşanlı şoklara dayanıklı)
  - Gecikme uzunluğu (1–4) havuzlanmış modelde AIC ile
  Ayrıca: "Panel ortalaması" (sektör içinde ortak θ) ve "Tüm imalat" (bölge içinde sektörler
  havuzlanmış, sektör sabit etkili, ortak θ) satırları; 60 aylık kayan pencere panel ECM.

SAĞLAMLIK
  - Hücre bazında ARDL-ECM (sektör × bölge; AIC gecikme ≤6, Pesaran-Shin-Smith sınır testi)
  - LP-IV (Jordà; kümülatif): lx_{t+h}-lx_{t-1} = β_h (lrp_{t+h}-lrp_{t-1}) + γ_h (ly_{t+h}-ly_{t-1}) + …
    göreli fiyat Δln(USD/TRY) ve Δln(USD/EUR) ile araçlanır.
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.iv import IV2SLS

sys.path.insert(0, os.path.dirname(__file__))
from config import COVID, OUTPUT, POST_START, PROC, REGIONS, SECTORS, START  # noqa: E402

warnings.filterwarnings("ignore")
MAXLAG = 6           # hücre ARDL
PANEL_MAXLAG = 4     # panel ECM
MIN_OBS = 120        # bir hücrenin modele girmesi için en az geçerli ay
HAC = {"cov_type": "HAC", "cov_kwds": {"maxlags": 6}}
# PSS (2001) kritik değerler, case III (kısıtsız sabit, trend yok), k=2, %5
PSS_F = (3.79, 4.85)
PSS_T = (-2.86, -3.53)
TOTAL = "Tüm imalat"
POOLED = "Panel ortalaması"


# ------------------------------------------------------------------ ortak yardımcılar
def dummies(dates):
    d = pd.PeriodIndex(dates, freq="M")
    X = pd.DataFrame(index=dates.index)
    for m in range(2, 13):
        X[f"m_{m}"] = (d.month == m).astype(float)
    for m in pd.period_range("2020-03", "2020-06", freq="M"):
        X[f"cv_{m}"] = (d == m).astype(float)
    X["cv_step"] = ((d >= pd.Period("2020-07", "M")) & (d <= pd.Period(COVID[1], "M"))).astype(float)
    return X


def post_dummy(dates):
    return (pd.PeriodIndex(dates, freq="M") >= pd.Period(POST_START, "M")).astype(float)


def longrun(res, num, den="y_l1"):
    """-(Σ num)/φ ve delta yöntemi SE."""
    b, V = res.params, res.cov_params()
    phi = b[den]
    th = sum(b[n] for n in num)
    lr = -th / phi
    g = pd.Series(0.0, index=b.index)
    for n in num:
        g[n] = -1 / phi
    g[den] = th / phi ** 2
    se = float(np.sqrt(g @ V @ g))
    return lr, se


def stars(t):
    a = abs(t)
    return "***" if a > 2.576 else "**" if a > 1.96 else "*" if a > 1.645 else ""


def valid_cell(df):
    return df[["lx", "lrp", "ly"]].notna().all(axis=1).sum() >= MIN_OBS


# ------------------------------------------------------------------ panel ECM
def short_run(df, L):
    X = pd.DataFrame(index=df.index)
    for i in range(1, L + 1):
        X[f"dy_l{i}"] = df.lx.diff().shift(i)
    for i in range(0, L + 1):
        X[f"dp_l{i}"] = df.lrp.diff().shift(i)
        X[f"dinc_l{i}"] = df.ly.diff().shift(i)
    return X


def panel_design(cells, L, hetero, post):
    """cells: [(anahtar, df)]. hetero=True -> uzun dönem θ'lar anahtara özel."""
    ys, Xs, ts = [], [], []
    for k, df in cells:
        df = df.reset_index(drop=True)
        X = pd.DataFrame(index=df.index)
        X["y_l1"] = df.lx.shift(1)
        sfx = f"__{k}" if hetero else ""
        X["p_l1" + sfx], X["inc_l1" + sfx] = df.lrp.shift(1), df.ly.shift(1)
        X[f"fe__{k}"] = 1.0
        if post:
            D = post_dummy(df.date)
            X[f"D__{k}"] = D
            X["Dp_l1" + sfx] = D * df.lrp.shift(1)
            X["Dinc_l1" + sfx] = D * df.ly.shift(1)
        X = pd.concat([X, short_run(df, L), dummies(df.date)], axis=1)
        dy = df.lx.diff()
        ok = dy.notna() & X.notna().all(axis=1)
        ok.iloc[:PANEL_MAXLAG + 1] = False  # tüm L için aynı örneklem
        ys.append(dy[ok]); Xs.append(X[ok]); ts.append(df.date[ok])
    y = pd.concat(ys, ignore_index=True)
    X = pd.concat(Xs, ignore_index=True).fillna(0.0)
    X = X.loc[:, (X != 0).any()]
    t = pd.concat(ts, ignore_index=True)
    return y, X, t


def fit_panel(cells, L, hetero=True, post=False):
    y, X, t = panel_design(cells, L, hetero, post)
    g = pd.factorize(t)[0]
    return sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": g})


def panel_lag(cells):
    aic = {L: sm.OLS(*panel_design(cells, L, True, False)[:2]).fit().aic
           for L in range(1, PANEL_MAXLAG + 1)}
    return min(aic, key=aic.get)


def panel_results(cells, L, hetero):
    """Uzun dönem (tüm / öncesi / sonrası) ve kısa dönem esneklikler. hetero ise anahtar başına satır."""
    base = fit_panel(cells, L, hetero, post=False)
    inter = fit_panel(cells, L, hetero, post=True)
    keys = [k for k, _ in cells] if hetero else [None]
    out = []
    for k in keys:
        sfx = f"__{k}" if hetero else ""
        o = {"key": k, "lag": L, "n": int(base.nobs), "r2": base.rsquared_adj,
             "phi": base.params["y_l1"], "phi_t": base.tvalues["y_l1"],
             "phi_post": inter.params["y_l1"]}
        for tag, var in [("p", "p_l1"), ("y", "inc_l1")]:
            v = var + sfx
            o[f"{tag}_full"], o[f"{tag}_full_se"] = longrun(base, [v])
            o[f"{tag}_pre"], o[f"{tag}_pre_se"] = longrun(inter, [v])
            o[f"{tag}_post"], o[f"{tag}_post_se"] = longrun(inter, [v, "D" + v])
            lr, se = longrun(inter, ["D" + v])
            o[f"{tag}_diff_t"] = lr / se
        o["p_sr"], o["p_sr_se"] = base.params["dp_l0"], base.bse["dp_l0"]
        o["y_sr"], o["y_sr_se"] = base.params["dinc_l0"], base.bse["dinc_l0"]
        o["coint"] = "panel"
        out.append(o)
    return out


def panel_rolling(cells, L, window=60):
    """Bölgeye özel uzun dönem esneklikler, 60 aylık kayan pencere (ay sonu tarihine göre)."""
    dates = pd.period_range(START, cells[0][1].date.iloc[-1], freq="M")
    rows = []
    for end in range(window + PANEL_MAXLAG, len(dates) + 1, 3):  # 3 ayda bir
        lo, hi = str(dates[end - window - PANEL_MAXLAG]), str(dates[end - 1])
        sub = [(k, d[(d.date >= lo) & (d.date <= hi)]) for k, d in cells]
        sub = [(k, d) for k, d in sub if d[["lx", "lrp", "ly"]].notna().all(axis=1).sum() >= window * 0.8]
        if not sub:
            continue
        try:
            res = fit_panel(sub, L, hetero=True)
        except Exception:
            continue
        for k, _ in sub:
            lp, sp = longrun(res, [f"p_l1__{k}"])
            ly, sy = longrun(res, [f"inc_l1__{k}"])
            rows.append({"date": hi, "region": k, "p_lr": lp, "p_se": sp, "y_lr": ly, "y_se": sy,
                         "phi": res.params["y_l1"]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ hücre ARDL (sağlamlık)
def ecm_design(df, L, post=False):
    X = pd.DataFrame(index=df.index)
    X["y_l1"], X["p_l1"], X["inc_l1"] = df.lx.shift(1), df.lrp.shift(1), df.ly.shift(1)
    if post:
        D = post_dummy(df.date)
        X["D"], X["Dp_l1"], X["Dinc_l1"] = D, D * df.lrp.shift(1), D * df.ly.shift(1)
    X = pd.concat([X, short_run(df, L), dummies(df.date)], axis=1)
    return df.lx.diff(), sm.add_constant(X)


def fit_ecm(df, L, post=False, start=MAXLAG + 1):
    dy, X = ecm_design(df, L, post)
    ok = dy.notna() & X.notna().all(axis=1)
    ok.iloc[:start] = False
    X = X.loc[ok]
    X = X.loc[:, X.std() > 0].assign(const=1.0)
    return sm.OLS(dy[ok], X).fit(**HAC)


def estimate_cell(df):
    df = df.reset_index(drop=True)
    aics = {L: fit_ecm(df, L).aic for L in range(1, MAXLAG + 1)}
    L = min(aics, key=aics.get)
    base = fit_ecm(df, L)
    inter = fit_ecm(df, L, post=True)
    out = {"lag": L, "n": int(base.nobs), "r2": base.rsquared_adj}
    for tag, var in [("p", "p_l1"), ("y", "inc_l1")]:
        out[f"{tag}_full"], out[f"{tag}_full_se"] = longrun(base, [var])
        out[f"{tag}_pre"], out[f"{tag}_pre_se"] = longrun(inter, [var])
        out[f"{tag}_post"], out[f"{tag}_post_se"] = longrun(inter, [var, "D" + var])
        lr, se = longrun(inter, ["D" + var])
        out[f"{tag}_diff_t"] = lr / se
    out["p_sr"], out["p_sr_se"] = base.params["dp_l0"], base.bse["dp_l0"]
    out["y_sr"], out["y_sr_se"] = base.params["dinc_l0"], base.bse["dinc_l0"]
    out["phi"], out["phi_t"] = base.params["y_l1"], base.tvalues["y_l1"]
    out["phi_post"] = inter.params["y_l1"]
    ols = sm.OLS(base.model.endog, base.model.exog).fit()
    names = base.model.exog_names
    R = np.zeros((3, len(names)))
    for i, n in enumerate(["y_l1", "p_l1", "inc_l1"]):
        R[i, names.index(n)] = 1
    out["bounds_F"] = float(ols.f_test(R).fvalue)
    out["bounds_t"] = float(ols.tvalues[names.index("y_l1")])
    out["coint"] = ("evet" if out["bounds_F"] > PSS_F[1] and out["bounds_t"] < PSS_T[1]
                    else "belirsiz" if out["bounds_F"] > PSS_F[0] else "hayır")
    return out


def lp_iv(df, H=12, nlags=3):
    df = df.reset_index(drop=True)
    out = []
    ctrl = pd.DataFrame(index=df.index)
    for v in ["lx", "lrp", "ly"]:
        for i in range(1, nlags + 1):
            ctrl[f"d{v}_l{i}"] = df[v].diff().shift(i)
    ctrl = pd.concat([ctrl, dummies(df.date)], axis=1)
    inst = pd.DataFrame({"z_usd": df.lusd.diff(), "z_eur": df.leur.diff()})
    for h in range(H + 1):
        dep = df.lx.shift(-h) - df.lx.shift(1)
        endog = (df.lrp.shift(-h) - df.lrp.shift(1)).rename("cum_rp")
        exo = sm.add_constant(pd.concat([(df.ly.shift(-h) - df.ly.shift(1)).rename("cum_y"), ctrl], axis=1))
        ok = dep.notna() & endog.notna() & exo.notna().all(axis=1) & inst.notna().all(axis=1)
        exo_ok = exo[ok].loc[:, exo[ok].std() > 0].assign(const=1.0)
        m = IV2SLS(dep[ok], exo_ok, endog[ok], inst[ok]).fit(
            cov_type="kernel", kernel="bartlett", bandwidth=h + 1)
        fs = m.first_stage.diagnostics
        out.append({"h": h, "p": m.params["cum_rp"], "p_se": m.std_errors["cum_rp"],
                    "y": m.params["cum_y"], "y_se": m.std_errors["cum_y"],
                    "fs_F": float(fs["f.stat"].iloc[0]), "n": int(m.nobs)})
    return pd.DataFrame(out)


# ------------------------------------------------------------------ main
def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PROC / "panel.csv")
    cells = {k: g.reset_index(drop=True) for k, g in panel.groupby(["sector", "region"], sort=False)}
    cells = {k: g for k, g in cells.items() if valid_cell(g)}
    dropped = sorted(set(panel.groupby(["sector", "region"]).groups) - set(cells))
    print(f"{len(cells)} hücre modelde; veri yetersiz: {dropped}")

    main_rows, roll = [], []
    # 1) Ana model: sektör başına bölgeye özel uzun dönem panel ECM + panel ortalaması
    for s in SECTORS:
        cs = [(r, cells[(s, r)]) for r in REGIONS if (s, r) in cells]
        if len(cs) < 2:
            continue
        L = panel_lag(cs)
        print(f"panel {s}: {len(cs)} bölge, L={L}", flush=True)
        for o in panel_results(cs, L, hetero=True):
            main_rows.append({**o, "sector": s, "region": o.pop("key")})
        for o in panel_results(cs, L, hetero=False):
            o.pop("key")
            main_rows.append({**o, "sector": s, "region": POOLED})
        rr = panel_rolling(cs, L)
        rr["sector"] = s
        roll.append(rr)
    # 2) Bölge başına tüm imalat (sektörler havuzlanmış, sektör sabit etkili, ortak θ)
    for r in REGIONS:
        cs = [(s, cells[(s, r)]) for s in SECTORS if (s, r) in cells]
        L = panel_lag(cs)
        print(f"tüm imalat {r}: {len(cs)} sektör, L={L}", flush=True)
        o = panel_results(cs, L, hetero=False)[0]
        o.pop("key")
        main_rows.append({**o, "sector": TOTAL, "region": r})
    pd.DataFrame(main_rows).to_csv(OUTPUT / "panel_ecm_results.csv", index=False)
    pd.concat(roll).to_csv(OUTPUT / "panel_rolling.csv", index=False)

    # 3) Sağlamlık: hücre ARDL ve LP-IV
    ardl, lps = [], []
    for (s, r), df in cells.items():
        df = df.dropna(subset=["lx", "lrp", "ly"]).reset_index(drop=True)
        try:
            o = estimate_cell(df)
            ardl.append({**o, "sector": s, "region": r})
            lp = lp_iv(df)
            lp["sector"], lp["region"] = s, r
            lps.append(lp)
        except Exception as e:
            print(f"ARDL/LP {s} {r}: {e}")
    pd.DataFrame(ardl).to_csv(OUTPUT / "ardl_cell_results.csv", index=False)
    pd.concat(lps).to_csv(OUTPUT / "lp_iv.csv", index=False)
    m = pd.DataFrame(main_rows)
    print(m[["sector", "region", "lag", "p_full", "p_full_se", "y_full", "y_full_se", "phi"]]
          .round(2).to_string())


if __name__ == "__main__":
    main()
