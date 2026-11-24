"""Makro veriler: partner geliri, partner fiyatları, kurlar.

Kaynaklar
- IMF WEO: yıllık reel GSYH (NGDP_R), tüm ülkeler (2026 IMF tahmini dahil)
- IMF CPI: aylık TÜFE (toplam), IMF ER: aylık ortalama kur (ulusal para / USD)
- FRED: ABD sanayi üretimi (INDPRO), EUR/USD (DEXUSEU), ABD reel GSYH (GDPC1)
- Eurostat: AB-27 sanayi üretimi (sts_inpr_m), AB-27 çeyreklik reel GSYH (namq_10_gdp)
"""
import io
import os
import sys
import time

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(__file__))
from config import RAW, REGIONS  # noqa: E402

IMF = "https://api.imf.org/external/sdmx/2.1/data"
CSV = {"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}
OUT = RAW / "macro"
ALL = sorted({c for v in REGIONS.values() for c in v} | {"TUR"})


def get(url, headers=None, params=None, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=180)
            if r.status_code == 200:
                return r
            print("HTTP", r.status_code, url[:120])
        except Exception as e:
            print("ERR", e)
        time.sleep(5 * (i + 1))
    raise RuntimeError(url)


def imf(flow, key, start, cols):
    frames = []
    for i in range(0, len(ALL), 40):  # URL uzunluğu için parçala
        k = key.format("+".join(ALL[i:i + 40]))
        r = get(f"{IMF}/{flow}/{k}", CSV, {"startPeriod": start})
        frames.append(pd.read_csv(io.StringIO(r.text), usecols=lambda c: c in cols, low_memory=False))
    return pd.concat(frames, ignore_index=True)


def fred(series):
    r = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
    d = pd.read_csv(io.StringIO(r.text))
    d.columns = ["date", series]
    return d


def eurostat(ds, params):
    r = get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{ds}",
            params={**params, "format": "JSON"})
    j = r.json()
    t = j["dimension"]["time"]["category"]["index"]
    inv = {v: k for k, v in t.items()}
    return pd.DataFrame({"date": [inv[int(i)] for i in j["value"]], "value": list(j["value"].values())})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cols = {"COUNTRY", "INDICATOR", "TIME_PERIOD", "OBS_VALUE", "TYPE_OF_TRANSFORMATION",
            "COICOP_1999", "INDEX_TYPE"}

    print("IMF WEO reel GSYH")
    imf("IMF.RES,WEO", "{}.NGDP_R.A", "2005", cols).to_csv(OUT / "weo_ngdp_r.csv", index=False)
    print("IMF CPI")
    imf("IMF.STA,CPI", "{}.CPI._T.IX.M", "2010-01", cols).to_csv(OUT / "imf_cpi.csv", index=False)
    print("IMF ER")
    imf("IMF.STA,ER", "{}.XDC_USD.PA_RT.M", "2010-01", cols).to_csv(OUT / "imf_er.csv", index=False)

    print("FRED")
    f = fred("INDPRO")
    for s in ["DEXUSEU", "GDPC1", "DCOILBRENTEU"]:
        f = f.merge(fred(s), on="date", how="outer")
    f.to_csv(OUT / "fred.csv", index=False)

    print("Eurostat")
    eurostat("sts_inpr_m", {"geo": "EU27_2020", "nace_r2": "B-D", "s_adj": "SCA", "unit": "I21"}) \
        .to_csv(OUT / "eu_ip.csv", index=False)
    eurostat("namq_10_gdp", {"geo": "EU27_2020", "na_item": "B1GQ", "s_adj": "SCA", "unit": "CLV10_MEUR"}) \
        .to_csv(OUT / "eu_gdp_q.csv", index=False)

    print("tamam")


if __name__ == "__main__":
    main()
