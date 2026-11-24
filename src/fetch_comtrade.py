"""UN Comtrade (abonelik API'si) – Türkiye'nin aylık ihracatı, HS6 × partner ülke.

Uç nokta: https://comtradeapi.un.org/data/v1/get/C/M/HS
Kimlik:   başlık "Ocp-Apim-Subscription-Key: $COMTRADE_API_KEY"

Çağrı başına en fazla 100 000 satır döndüğü için her ay, partner ülke grupları için
ayrı ayrı istenir (AB-27 | ABD+Diğer Avrupa+BDT+Dünya | MENA+Sahra Altı Afrika).
Bir yanıt 100 000 satıra ulaşırsa grup ikiye bölünerek yeniden istenir.
Yalnızca gerekli sütunlar parquet olarak saklanır.

Kullanım: python src/fetch_comtrade.py --start 2013-01 --end 2026-08 [--workers 3]
Çıktı:  data/raw/comtrade_hs6/{YYYYMM}_{grup}.parquet   (var olanlar atlanır)
        data/raw/comtrade_hs6/_empty.txt               (verisi henüz yayımlanmamış aylar)
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(__file__))
from config import RAW, REGIONS  # noqa: E402

URL = "https://comtradeapi.un.org/data/v1/get/C/M/HS"
REPORTER = 792  # Türkiye
OUT = RAW / "comtrade_hs6"
LIMIT = 100_000
KEEP = ["period", "partnerCode", "cmdCode", "classificationCode", "primaryValue",
        "netWgt", "isNetWgtEstimated", "qty", "qtyUnitCode", "isQtyEstimated"]
# partnerAreas.json'da birden çok kodu olan ülkeler için Comtrade'in Türkiye beyanında kullandığı kod
CODE_OVERRIDE = {"FRA": 251, "USA": 842, "CHE": 757, "NOR": 579}

_lock = threading.Lock()
_last = [0.0]


def partner_codes():
    ref = json.load(open(RAW.parent / "ref" / "partnerAreas.json"))["results"]
    code = {r["PartnerCodeIsoAlpha3"]: r["PartnerCode"] for r in ref
            if r.get("PartnerCodeIsoAlpha3") and not r.get("entryExpiredDate")}
    code.update(CODE_OVERRIDE)
    return code


def groups():
    c = partner_codes()
    pc = lambda regs: [c[i] for r in regs for i in REGIONS[r] if i in c]  # noqa: E731
    return {"eu": pc(["AB-27"]),
            "usoecis": [0] + pc(["ABD", "Diğer Avrupa", "BDT"]),
            "menassa": pc(["MENA", "Sahra Altı Afrika"])}


def throttle(gap=1.5):
    """API: saniyede en çok 1 çağrı."""
    with _lock:
        w = _last[0] + gap - time.time()
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()


def call(period, partners, tries=6):
    params = {"reporterCode": REPORTER, "period": period, "flowCode": "X", "cmdCode": "AG6",
              "partnerCode": ",".join(map(str, partners)), "partner2Code": 0, "motCode": 0,
              "customsCode": "C00", "includeDesc": "false", "maxRecords": LIMIT}
    hdr = {"Ocp-Apim-Subscription-Key": os.environ["COMTRADE_API_KEY"]}
    for i in range(tries):
        throttle()
        try:
            r = requests.get(URL, params=params, headers=hdr, timeout=300)
            if r.status_code == 200:
                d = r.json()
                if d.get("error"):
                    raise RuntimeError(d["error"])
                return d.get("data", [])
            msg = f"HTTP {r.status_code} {r.text[:150]}"
            if r.status_code == 403 and "quota" in r.text.lower():
                raise SystemExit(f"Günlük kota doldu: {msg}")
        except SystemExit:
            raise
        except Exception as e:  # ağ hatası / JSON
            msg = repr(e)[:150]
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"{period} {partners[:3]}...: {msg}")


def fetch(period, name, partners):
    out = OUT / f"{period}_{name}.parquet"
    if out.exists():
        return f"skip {out.name}"
    rows = call(period, partners)
    if len(rows) >= LIMIT:  # kesildi -> ikiye böl
        h = len(partners) // 2
        res = [fetch(period, f"{name}a", partners[:h]), fetch(period, f"{name}b", partners[h:])]
        return " | ".join(res)
    df = pd.DataFrame(rows, columns=KEEP)
    if df.empty:
        with _lock, open(OUT / "_empty.txt", "a") as f:
            f.write(f"{period}_{name}\n")
        return f"empty {period}_{name}"
    df["period"] = df.period.astype(str)
    df["cmdCode"] = df.cmdCode.astype(str)
    df.to_parquet(out, index=False)
    return f"ok {out.name} n={len(df)}"


def done(period, name):
    return any(p.name.startswith(f"{period}_{name}") for p in OUT.glob(f"{period}_{name}*.parquet"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2013-01")
    ap.add_argument("--end", default="2026-08")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    empty = set((OUT / "_empty.txt").read_text().split()) if (OUT / "_empty.txt").exists() else set()
    periods = [p.strftime("%Y%m") for p in pd.period_range(a.start, a.end, freq="M")]
    G = groups()
    jobs = [(p, n, c) for p in reversed(periods) for n, c in G.items()
            if not done(p, n) and f"{p}_{n}" not in empty]
    print(f"{len(jobs)} çağrı bekliyor", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch, *j): j for j in jobs}
        for k, f in enumerate(as_completed(futs), 1):
            try:
                res = f.result()
            except Exception as e:
                res = f"FAIL {futs[f][:2]} {e}"
            print(f"[{k}/{len(jobs)}] {res}", flush=True)


if __name__ == "__main__":
    main()
