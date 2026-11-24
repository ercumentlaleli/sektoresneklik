"""Sektörel ihracat esneklikleri – Streamlit arayüzü.

Çalıştırma:  streamlit run app.py
Okuduğu dosyalar: output/*.csv, output/ihracat_esneklikleri.xlsx, data/processed/*.csv
(önce src/ altındaki boru hattı çalıştırılmış olmalı).
"""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from config import POST_START, REGIONS, SECTORS  # noqa: E402

OUT, PROC = ROOT / "output", ROOT / "data" / "processed"
POOLED, TOTAL = "Panel ortalaması", "Tüm imalat"
NO_GOODS = {"C33"}

st.set_page_config(page_title="Sektörel İhracat Esneklikleri", page_icon="📈", layout="wide")

TAG = {"Fiyat esnekliği": "p", "Gelir esnekliği": "y"}
PER = {"Tüm dönem (2013–2026)": "full", "Pandemi öncesi (2013–2020)": "pre",
       "Pandemi sonrası (2021–2026)": "post"}
MODEL = {"Panel ECM (ana model)": "panel", "Hücre ARDL (sağlamlık)": "ardl"}


# ------------------------------------------------------------------ veri
@st.cache_data
def load():
    d = {"panel": pd.read_csv(OUT / "panel_ecm_results.csv"),
         "ardl": pd.read_csv(OUT / "ardl_cell_results.csv"),
         "lp": pd.read_csv(OUT / "lp_iv.csv"),
         "roll": pd.read_csv(OUT / "panel_rolling.csv"),
         "cov": pd.read_csv(PROC / "coverage.csv"),
         "uvinfo": pd.read_csv(PROC / "uv_index_info.csv"),
         "data": pd.read_csv(PROC / "panel.csv")}
    d["ardl"]["region"] = d["ardl"].region.astype(str)
    return d


def stars(t):
    a = abs(t)
    return "***" if a > 2.576 else "**" if a > 1.96 else "*" if a > 1.645 else ""


def label(s):
    return f"{s} {SECTORS[s]}" if s in SECTORS else s


def view(res, tag, per):
    """Uzun format: sektör, bölge, değer, SE, t, anlamlılık."""
    v = res[["sector", "region"]].copy()
    v["deger"] = res[f"{tag}_{per}"]
    v["se"] = res[f"{tag}_{per}_se"]
    v["t"] = v.deger / v.se
    v["yildiz"] = v.t.apply(stars)
    v["alt"], v["ust"] = v.deger - 1.96 * v.se, v.deger + 1.96 * v.se
    if "coint" in res:
        v["esbutunlesme"] = res.coint
    v["fark_t"] = res[f"{tag}_diff_t"]
    return v


def matrix(v, col, rows, cols):
    m = v.pivot_table(index="sector", columns="region", values=col, aggfunc="first")
    return m.reindex(index=rows, columns=cols)


D = load()
SECTOR_ROWS = [s for s in SECTORS if s not in NO_GOODS]

# ------------------------------------------------------------------ kenar çubuğu
with st.sidebar:
    st.title("📈 İhracat esneklikleri")
    st.caption("Türkiye imalat ihracatı · NACE Rev.2 × bölge · aylık 2013/01–2026/08")
    kind = st.radio("Esneklik", list(TAG), horizontal=True)
    period = st.selectbox("Dönem", list(PER))
    model = st.selectbox("Model", list(MODEL))
    sig = st.select_slider("Anlamlılık filtresi", ["Hepsi", "%10", "%5", "%1"], value="Hepsi",
                           help="Bu düzeyde anlamlı olmayan hücreler ısı haritasında gri gösterilir.")
    st.divider()
    st.markdown(
        ("**Panel ECM (ana model):** her sektörde 6 bölge havuzlanmış; bölgeye özel uzun dönem "
         "esneklikler, ortak uyarlanma hızı. Ay bazında kümelenmiş standart hatalar."
         if MODEL[model] == "panel" else
         "**Hücre ARDL (sağlamlık):** her sektör × bölge ayrı tahmin; AIC gecikmesi ≤ 6, HAC standart "
         "hatalar, Pesaran-Shin-Smith sınır testi.") + "\n\n*** %1 · ** %5 · * %10")

tag, per, mkey = TAG[kind], PER[period], MODEL[model]
res = D[mkey]
V = view(res, tag, per)
cols = list(REGIONS) + ([POOLED] if mkey == "panel" else [])
rows = SECTOR_ROWS + ([TOTAL] if mkey == "panel" else [])
crit = {"Hepsi": 0, "%10": 1.645, "%5": 1.96, "%1": 2.576}[sig]

st.title(f"{kind} · {period}")
st.caption(f"{model}. Fiyat esnekliğinde beklenen işaret negatif, gelir esnekliğinde pozitiftir.")

tabs = st.tabs(["🗺️ Özet", "🏭 Sektör", "🌍 Bölge", "🔎 Sağlamlık", "📚 Veri ve yöntem", "⬇️ İndir"])

# ------------------------------------------------------------------ Özet
with tabs[0]:
    cells = V[V.sector.isin(SECTOR_ROWS) & V.region.isin(REGIONS)]
    sign = -1 if tag == "p" else 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tahmin edilen hücre", f"{len(cells)}")
    c2.metric("Medyan esneklik", f"{cells.deger.median():.2f}")
    c3.metric("Beklenen işaretle %5 anlamlı", f"{(sign * cells.t > 1.96).sum()}")
    c4.metric("Ters işaretle %5 anlamlı", f"{(sign * cells.t < -1.96).sum()}")

    z = matrix(V, "deger", rows, cols)
    t = matrix(V, "t", rows, cols)
    txt = matrix(V.assign(s=V.deger.round(2).astype(str) + V.yildiz), "s", rows, cols)
    zshow = z.where(t.abs() >= crit) if crit else z
    lim = float(np.nanpercentile(np.abs(z.values), 95)) if np.isfinite(z.values).any() else 1
    fig = go.Figure(go.Heatmap(
        z=zshow.values, x=cols, y=[label(r) for r in rows], text=txt.fillna("").values,
        texttemplate="%{text}", textfont={"size": 11}, zmid=0, zmin=-lim, zmax=lim,
        colorscale="RdBu" if tag == "y" else "RdBu_r", colorbar={"title": "esneklik"},
        hovertemplate="%{y}<br>%{x}<br>esneklik: %{z:.2f}<extra></extra>"))
    fig.update_layout(height=780, margin=dict(l=10, r=10, t=40, b=10), yaxis_autorange="reversed",
                      plot_bgcolor="#e5e5e5", xaxis_side="top")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Gri: veri yetersiz ya da seçilen düzeyde anlamsız. C33 (onarım ve kurulum) hizmet "
               "faaliyetidir, mal ihracatı yoktur. Renk ölçeği, değerlerin %95'lik dilimiyle sınırlanmıştır.")

# ------------------------------------------------------------------ Sektör
with tabs[1]:
    s = st.selectbox("Sektör", SECTOR_ROWS, format_func=label, index=SECTOR_ROWS.index("C29"))
    a, b = st.columns([3, 2])
    with a:
        q = V[(V.sector == s) & V.region.isin(cols)].set_index("region").reindex(cols).dropna(subset=["deger"])
        fig = go.Figure(go.Bar(
            x=q.index, y=q.deger, error_y=dict(type="data", symmetric=False,
                                               array=q.ust - q.deger, arrayminus=q.deger - q.alt),
            marker_color=["#888" if r == POOLED else "#1f3864" for r in q.index],
            customdata=np.c_[q.se, q.yildiz],
            hovertemplate="%{x}<br>esneklik: %{y:.2f}%{customdata[1]}<br>SE: %{customdata[0]:.2f}<extra></extra>"))
        fig.add_hline(y=0, line_color="black", line_width=1)
        fig.update_layout(title=f"{label(s)} – {kind.lower()} (%95 güven aralığı)", height=420,
                          margin=dict(t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.markdown("**Dönem karşılaştırması**")
        pp = res[(res.sector == s) & res.region.isin(cols)].set_index("region").reindex(cols).dropna(how="all")
        tbl = pd.DataFrame({
            "Öncesi": pp[f"{tag}_pre"].round(2).astype(str) + (pp[f"{tag}_pre"] / pp[f"{tag}_pre_se"]).apply(stars),
            "Sonrası": pp[f"{tag}_post"].round(2).astype(str) + (pp[f"{tag}_post"] / pp[f"{tag}_post_se"]).apply(stars),
            "Fark t": pp[f"{tag}_diff_t"].round(2),
            "Kısa dönem": pp[f"{tag}_sr"].round(2),
            "φ": pp.phi.round(2)})
        st.dataframe(tbl.rename_axis("Bölge"), use_container_width=True)
        st.caption("Fark t: pandemi sonrası − öncesi farkının t istatistiği (|t| > 1,96 → %5'te anlamlı).")

    if mkey == "panel":
        rr = D["roll"][D["roll"].sector == s]
        col = "p_lr" if tag == "p" else "y_lr"
        sec = "p_se" if tag == "p" else "y_se"
        rr = rr.assign(alt=rr[col] - 1.96 * rr[sec], ust=rr[col] + 1.96 * rr[sec])
        regs = st.multiselect("Kayan pencere – bölgeler (tek bölge seçilince %95 bandı gösterilir)",
                              list(REGIONS), default=list(REGIONS)[:3])
        fig = go.Figure()
        for i, r in enumerate(regs):
            x = rr[rr.region == r]
            c = px.colors.qualitative.D3[i % 10]
            fig.add_trace(go.Scatter(x=x.date, y=x[col], name=r, line_color=c))
            if len(regs) == 1:  # güven bandı yalnızca tek bölgede (okunabilirlik)
                fig.add_trace(go.Scatter(x=list(x.date) + list(x.date[::-1]), y=list(x.ust) + list(x.alt[::-1]),
                                         fill="toself", fillcolor=c, opacity=0.15, line_width=0,
                                         showlegend=False, hoverinfo="skip"))
        fig.add_hline(y=0, line_color="black", line_width=1)
        if len(rr):
            lo, hi = np.nanpercentile(rr[col], [2, 98])
            pad = 0.25 * (hi - lo)
            fig.update_yaxes(range=[lo - pad, hi + pad])
        fig.update_layout(title="60 aylık kayan pencere, uzun dönem esneklik (pencere sonu tarihi)",
                          height=420, margin=dict(t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------ Bölge
with tabs[2]:
    r = st.selectbox("Bölge", list(REGIONS))
    q = V[(V.region == r) & V.sector.isin(rows)].set_index("sector").reindex(rows).dropna(subset=["deger"])
    q = q.sort_values("deger")
    fig = go.Figure(go.Scatter(
        x=q.deger, y=[label(i) for i in q.index], mode="markers",
        marker=dict(size=10, color=["#c00" if i == TOTAL else "#1f3864" for i in q.index]),
        error_x=dict(type="data", symmetric=False, array=q.ust - q.deger, arrayminus=q.deger - q.alt)))
    fig.add_vline(x=0, line_color="black", line_width=1)
    fig.update_layout(title=f"{r} – sektörlere göre {kind.lower()} (%95 güven aralığı)",
                      height=max(450, 26 * len(q)), margin=dict(t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**{r} ülkeleri:** {', '.join(REGIONS[r])}")

# ------------------------------------------------------------------ Sağlamlık
with tabs[3]:
    a, b = st.columns(2)
    with a:
        m = view(D["panel"], tag, per).merge(view(D["ardl"], tag, per), on=["sector", "region"],
                                               suffixes=("_panel", "_ardl"))
        lim = float(np.nanpercentile(np.abs(m[["deger_panel", "deger_ardl"]].values), 95))
        fig = px.scatter(m, x="deger_panel", y="deger_ardl", color="region",
                         hover_data={"sector": True}, labels={"deger_panel": "Panel ECM",
                                                              "deger_ardl": "Hücre ARDL"})
        fig.add_shape(type="line", x0=-lim, y0=-lim, x1=lim, y1=lim, line_dash="dot")
        fig.update_xaxes(range=[-lim, lim]); fig.update_yaxes(range=[-lim, lim])
        fig.update_layout(title=f"Panel ECM ve hücre ARDL (korelasyon {m.deger_panel.corr(m.deger_ardl):.2f})",
                          height=480)
        st.plotly_chart(fig, use_container_width=True)
        co = D["ardl"].coint.value_counts()
        st.caption(f"ARDL sınır testi (PSS): eşbütünleşme var {co.get('evet', 0)}, belirsiz "
                   f"{co.get('belirsiz', 0)}, yok {co.get('hayır', 0)} hücre.")
    with b:
        lp = D["lp"]
        s2 = st.selectbox("LP-IV sektörü", sorted(lp.sector.unique()), format_func=label, key="lp_s")
        r2 = st.selectbox("LP-IV bölgesi", list(REGIONS), key="lp_r")
        x = lp[(lp.sector == s2) & (lp.region == r2)]
        if x.empty:
            st.info("Bu hücre için LP-IV yok (veri yetersiz).")
        else:
            col, sec = ("p", "p_se") if tag == "p" else ("y", "y_se")
            fig = go.Figure([
                go.Scatter(x=list(x.h) + list(x.h[::-1]),
                           y=list(x[col] + 1.96 * x[sec]) + list((x[col] - 1.96 * x[sec])[::-1]),
                           fill="toself", opacity=0.2, line_width=0, showlegend=False),
                go.Scatter(x=x.h, y=x[col], mode="lines+markers", showlegend=False)])
            fig.add_hline(y=0, line_color="black", line_width=1)
            fig.update_layout(title=f"LP-IV kümülatif {kind.lower()}, ufuk h (ay)", height=420,
                              xaxis_title="h")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Birinci aşama F (h=0): {x.fs_F.iloc[0]:.1f}. F < 10 zayıf araç demektir; "
                       "LP-IV yalnızca yön kontrolü olarak okunmalıdır.")

# ------------------------------------------------------------------ Veri ve yöntem
with tabs[4]:
    a, b = st.columns(2)
    with a:
        s3 = st.selectbox("Sektör", SECTOR_ROWS, format_func=label, key="uv_s", index=SECTOR_ROWS.index("C29"))
        x = D["data"][D["data"].sector == s3]
        what = st.radio("Seri", ["Birim değer endeksi (lp)", "Reel ihracat (lx)", "Göreli fiyat (lrp)",
                                 "Bölge geliri (ly)"], horizontal=True)
        c = what.split("(")[1][:-1]
        fig = px.line(x, x="date", y=c, color="region")
        fig.add_vline(x=POST_START, line_dash="dot")
        fig.update_layout(height=420, title=f"{label(s3)} – {what} (log)", xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Birim değer endeksi: kalem = HS6 × varış ülkesi, USD/kg, ağırlıklı zaman-ürün "
                   "kuklası regresyonu; log, 2015 ortalaması = 0.")
    with b:
        st.markdown("**Veri kapsamı (yıllık)**")
        cov = D["cov"].rename(columns={"year": "Yıl", "dunya_ihracat_mlr_usd": "Toplam ihracat (mlr $)",
                                       "imalat_payi": "İmalata eşlenen pay",
                                       "cok_bolumlu_hs6_payi": "Çok bölümlü HS6 payı",
                                       "bolgeler_payi": "6 bölgenin payı", "kg_mevcut_payi": "Kg verisi olan pay"})
        st.dataframe(cov.set_index("Yıl").style.format("{:.3f}"), use_container_width=True)
        st.markdown("**Birim değer endeksi: ay başına medyan kalem sayısı**")
        st.dataframe(D["uvinfo"].pivot(index="sector", columns="region", values="medyan_kalem"),
                     use_container_width=True)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    with st.expander("Yöntem ayrıntısı (README)"):
        st.markdown(readme)

# ------------------------------------------------------------------ İndir
with tabs[5]:
    st.subheader("Seçili görünüm")
    tbl = V[V.sector.isin(rows)].copy()
    tbl.insert(0, "sektor_adi", tbl.sector.map(lambda s: SECTORS.get(s, s)))
    tbl = tbl.round(4).rename(columns={
        "sektor_adi": "Sektör adı", "sector": "Sektör", "region": "Bölge", "deger": "Esneklik", "se": "SE",
        "yildiz": "Anlamlılık", "alt": "%95 alt", "ust": "%95 üst", "esbutunlesme": "Eşbütünleşme",
        "fark_t": "Öncesi-sonrası fark t"})
    st.dataframe(tbl, use_container_width=True, height=300)
    a, b, c = st.columns(3)
    a.download_button("Seçili görünüm (CSV)", tbl.to_csv(index=False).encode("utf-8-sig"),
                      f"esneklik_{tag}_{per}_{mkey}.csv", "text/csv")
    wide = matrix(V.assign(s=V.deger.round(2).astype(str) + V.yildiz), "s", rows, cols)
    wide.index = [label(i) for i in wide.index]
    b.download_button("Seçili tablo, sektör × bölge (CSV)", wide.to_csv().encode("utf-8-sig"),
                      f"tablo_{tag}_{per}_{mkey}.csv", "text/csv")
    xlsx = OUT / "ihracat_esneklikleri.xlsx"
    c.download_button("Tüm tablolar (Excel)", xlsx.read_bytes(), xlsx.name,
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.subheader("Tüm sonuç ve veri dosyaları")
    files = {"panel_ecm_results.csv": OUT, "ardl_cell_results.csv": OUT, "lp_iv.csv": OUT,
             "panel_rolling.csv": OUT, "panel.csv": PROC, "coverage.csv": PROC,
             "uv_index_info.csv": PROC, "country_weights.csv": PROC}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f, d in files.items():
            z.write(d / f, f)
        z.write(xlsx, xlsx.name)
        z.write(ROOT / "README.md", "README.md")
        z.write(ROOT / "data" / "ref" / "hs6_nace2.csv", "hs6_nace2.csv")
    st.download_button("Hepsini indir (ZIP)", buf.getvalue(), "ihracat_esneklikleri.zip", "application/zip")
    g = st.columns(4)
    for i, (f, d) in enumerate(list(files.items()) + [("hs6_nace2.csv", ROOT / "data" / "ref")]):
        g[i % 4].download_button(f, (d / f).read_bytes(), f, "text/csv", key=f"dl_{f}")
    st.caption("panel.csv: sektör × bölge × ay paneli (log değişkenler). hs6_nace2.csv: HS6 → NACE Rev.2 "
               "uyum tablosu. Ham Comtrade verisi boyutu nedeniyle dahil değildir.")
