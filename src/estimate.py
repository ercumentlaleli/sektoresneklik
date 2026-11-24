"""İhracat talep esneklikleri: ARDL-ECM (ana model), kayan pencere ve LP-IV (sağlamlık).

ECM (her sektör × bölge):
  Δlx_t = c + φ·lx_{t-1} + θp·lrp_{t-1} + θy·ly_{t-1}
          [+ D_post·(c2 + δp·lrp_{t-1} + δy·ly_{t-1})]
          + Σ a_i Δlx_{t-i} + Σ b_i Δlrp_{t-i} + Σ g_i Δly_{t-i} + ay kuklaları + COVID kuklaları + ε
  Uzun dönem fiyat esnekliği = -θp/φ ; gelir esnekliği = -θy/φ  (delta yöntemi ile SE)
  Pandemi sonrası (2021+) uzun dönem = -(θ+δ)/φ
  Kısa dönem (etki) esneklikleri = b_0, g_0
  Eşbütünleşme: Pesaran-Shin-Smith sınır testi (F ve t), case III, k=2.

LP-IV (Jordà; kümülatif, Ramey normalizasyonu):
  lx_{t+h}-lx_{t-1} = α + β_h (lrp_{t+h}-lrp_{t-1}) + γ_h (ly_{t+h}-ly_{t-1}) + kontroller + ε
  lrp kümülatif değişimi araçlanır: Δln(USD/TRY)_t, Δln(USD/EUR)_t
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.iv import IV2SLS

sys.path.insert(0, os.path.dirname(__file__))
from config import COVID, OUTPUT, POST_START, PROC  # noqa: E402

warnings.filterwarnings("ignore")
MAXLAG = 6
HAC = {"cov_type": "HAC", "cov_kwds": {"maxlags": 6}}
# PSS (2001) kritik değerler, case III (kısıtsız sabit, trend yok), k=2, %5
PSS_F = (3.79, 4.85)
PSS_T = (-2.86, -3.53)


def dummies(dates):
    d = pd.PeriodIndex(dates, freq="M")
    X = pd.get_dummies(d.month, prefix="m", drop_first=True).astype(float)
    X.index = dates.index
    for m in pd.period_range("2020-03", "2020-06", freq="M"):
        X[f"cv_{m}"] = (d == m).astype(float)
    X["cv_step"] = ((d >= pd.Period("2020-07", "M")) & (d <= pd.Period(COVID[1], "M"))).astype(float)
    return X


def ecm_design(df, L, post=False):
    y, p, yy = df.lx, df.lrp, df.ly
    X = pd.DataFrame(index=df.index)
    X["y_l1"], X["p_l1"], X["inc_l1"] = y.shift(1), p.shift(1), yy.shift(1)
    if post:
        D = (pd.PeriodIndex(df.date, freq="M") >= pd.Period(POST_START, "M")).astype(float)
        X["D"], X["Dp_l1"], X["Dinc_l1"] = D, D * p.shift(1), D * yy.shift(1)
    for i in range(1, L + 1):
        X[f"dy_l{i}"] = y.diff().shift(i)
    for i in range(0, L + 1):
        X[f"dp_l{i}"] = p.diff().shift(i)
        X[f"dinc_l{i}"] = yy.diff().shift(i)
    X = pd.concat([X, dummies(df.date)], axis=1)
    X = sm.add_constant(X)
    return y.diff(), X


def fit_ecm(df, L, post=False, start=MAXLAG + 1):
    dy, X = ecm_design(df, L, post)
    ok = dy.notna() & X.notna().all(axis=1)
    ok.iloc[:start] = False  # tüm gecikme uzunlukları için aynı örneklem (AIC karşılaştırması)
    X = X.loc[ok]
    X = X.loc[:, X.std() > 0].assign(const=1.0)
    return sm.OLS(dy[ok], X).fit(**HAC)


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


def estimate_cell(df):
    df = df.reset_index(drop=True)
    # gecikme seçimi (AIC), temel model
    aics = {L: fit_ecm(df, L).aic for L in range(1, MAXLAG + 1)}
    L = min(aics, key=aics.get)
    base = fit_ecm(df, L)
    inter = fit_ecm(df, L, post=True)
    out = {"lag": L, "n": int(base.nobs), "r2": base.rsquared_adj}
    for tag, var in [("p", "p_l1"), ("y", "inc_l1")]:
        lr, se = longrun(base, [var])
        out[f"{tag}_full"], out[f"{tag}_full_se"] = lr, se
        lr, se = longrun(inter, [var])
        out[f"{tag}_pre"], out[f"{tag}_pre_se"] = lr, se
        lr, se = longrun(inter, [var, "D" + var])
        out[f"{tag}_post"], out[f"{tag}_post_se"] = lr, se
        # fark testi (post - pre = -δ/φ)
        lr, se = longrun(inter, ["D" + var])
        out[f"{tag}_diff_t"] = lr / se
    out["p_sr"], out["p_sr_se"] = base.params["dp_l0"], base.bse["dp_l0"]
    out["y_sr"], out["y_sr_se"] = base.params["dinc_l0"], base.bse["dinc_l0"]
    out["phi"], out["phi_t"] = base.params["y_l1"], base.tvalues["y_l1"]
    out["phi_post"] = inter.params["y_l1"]
    # PSS sınır testi (F): φ=θp=θy=0  (standart OLS kovaryansı ile)
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


def estimate_panel(cells, L=2):
    """Havuzlanmış ECM: ortak uzun dönem katsayıları, bölge sabit etkileri, zamana göre kümelenmiş SE."""
    out = {"lag": L}
    for post in (False, True):
        ys, Xs, groups = [], [], []
        for k, (r, df) in enumerate(cells):
            df = df.reset_index(drop=True)
            dy, X = ecm_design(df, L, post)
            X[f"fe_{k}"] = 1.0
            ok = dy.notna() & X.notna().all(axis=1)
            ok.iloc[:MAXLAG + 1] = False
            ys.append(dy[ok]); Xs.append(X[ok]); groups.append(df.date[ok])
        y = pd.concat(ys, ignore_index=True)
        X = pd.concat(Xs, ignore_index=True).fillna(0.0).drop(columns="const")
        X = X.loc[:, X.std() > 0]
        g = pd.factorize(pd.concat(groups, ignore_index=True))[0]
        res = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": g})
        for tag, var in [("p", "p_l1"), ("y", "inc_l1")]:
            if not post:
                out[f"{tag}_full"], out[f"{tag}_full_se"] = longrun(res, [var])
            else:
                out[f"{tag}_pre"], out[f"{tag}_pre_se"] = longrun(res, [var])
                out[f"{tag}_post"], out[f"{tag}_post_se"] = longrun(res, [var, "D" + var])
                lr, se = longrun(res, ["D" + var])
                out[f"{tag}_diff_t"] = lr / se
        if not post:
            out["n"], out["r2"] = int(res.nobs), res.rsquared_adj
            out["phi"], out["phi_t"] = res.params["y_l1"], res.tvalues["y_l1"]
            out["p_sr"], out["p_sr_se"] = res.params["dp_l0"], res.bse["dp_l0"]
            out["y_sr"], out["y_sr_se"] = res.params["dinc_l0"], res.bse["dinc_l0"]
    out["coint"] = "panel"
    return out


def rolling(df, L, window=60):
    df = df.reset_index(drop=True)
    rows = []
    for end in range(window + MAXLAG, len(df) + 1, 1):
        sub = df.iloc[end - window - MAXLAG:end].reset_index(drop=True)
        try:
            r = fit_ecm(sub, L)
            lp, sp = longrun(r, ["p_l1"])
            ly, sy = longrun(r, ["inc_l1"])
            rows.append({"date": sub.date.iloc[-1], "p_lr": lp, "p_se": sp, "y_lr": ly, "y_se": sy,
                         "phi": r.params["y_l1"]})
        except Exception:
            pass
    return pd.DataFrame(rows)


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
        exo = pd.concat([(df.ly.shift(-h) - df.ly.shift(1)).rename("cum_y"), ctrl], axis=1)
        exo = sm.add_constant(exo)
        ok = dep.notna() & endog.notna() & exo.notna().all(axis=1) & inst.notna().all(axis=1)
        exo_ok = exo[ok].loc[:, exo[ok].std() > 0].assign(const=1.0)
        m = IV2SLS(dep[ok], exo_ok, endog[ok], inst[ok]).fit(
            cov_type="kernel", kernel="bartlett", bandwidth=h + 1)
        fs = m.first_stage.diagnostics
        out.append({"h": h, "p": m.params["cum_rp"], "p_se": m.std_errors["cum_rp"],
                    "y": m.params["cum_y"], "y_se": m.std_errors["cum_y"],
                    "fs_F": float(fs["f.stat"].iloc[0]), "n": int(m.nobs)})
    return pd.DataFrame(out)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PROC / "panel.csv")
    res, roll, lps = [], [], []
    for (s, r), df in panel.groupby(["sector", "region"], sort=False):
        df = df.dropna(subset=["lx", "lrp", "ly"])
        print(f"{s} {r} ...", flush=True)
        o = estimate_cell(df)
        o.update(sector=s, region=r)
        res.append(o)
        rr = rolling(df, o["lag"])
        rr["sector"], rr["region"] = s, r
        roll.append(rr)
        lp = lp_iv(df)
        lp["sector"], lp["region"] = s, r
        lps.append(lp)
    for s, g in panel.groupby("sector", sort=False):
        cells = [(r, d.dropna(subset=["lx", "lrp", "ly"])) for r, d in g.groupby("region", sort=False)]
        o = estimate_panel(cells)
        o.update(sector=s, region="Panel (tüm bölgeler)")
        res.append(o)
    res = pd.DataFrame(res)
    res.to_csv(OUTPUT / "ecm_results.csv", index=False)
    pd.concat(roll).to_csv(OUTPUT / "rolling.csv", index=False)
    pd.concat(lps).to_csv(OUTPUT / "lp_iv.csv", index=False)
    cols = ["sector", "region", "lag", "n", "p_full", "p_pre", "p_post", "y_full", "y_pre", "y_post",
            "phi", "bounds_F", "coint"]
    print(res[cols].round(2).to_string())


if __name__ == "__main__":
    main()
