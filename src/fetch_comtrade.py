"""UN Comtrade (public preview) – Türkiye'nin aylık ihracatı, HS kodu × partner ülke.

Önizleme uç noktası anahtar istemez ama çağrı başına 500 satırla sınırlıdır ve
yavaştır (~15-20 sn). Bu yüzden her çağrıda bir ay ve az sayıda HS kodu istenir;
500 satıra ulaşan yanıtlar kodlara bölünerek yeniden istenir.

Kullanım: python src/fetch_comtrade.py --codes 87,72 74,76 ... --start 2013-01 --end 2026-09
Çıktı:  data/raw/comtrade/{period}_{codes}.json  (yeniden çalıştırmada var olanlar atlanır)
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
REPORTER = 792  # Türkiye
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "comtrade"


def fetch(period: str, codes: str, tries: int = 5) -> str:
    out = OUT / f"{period}_{codes.replace(',', '-')}.json"
    if out.exists():
        return f"skip {out.name}"
    params = {"reporterCode": REPORTER, "period": period, "flowCode": "X",
              "cmdCode": codes, "motCode": 0, "customsCode": "C00", "partner2Code": 0}
    for i in range(tries):
        try:
            r = requests.get(URL, params=params, timeout=120)
            if r.status_code == 200:
                d = r.json()
                n = d.get("count", 0)
                if n >= 500 and "," in codes:  # kesilmiş olabilir -> böl
                    return "|".join(fetch(period, c) for c in codes.split(","))
                out.write_text(json.dumps(d.get("data", [])))
                return f"ok {out.name} n={n}{' TRUNCATED' if n >= 500 else ''}"
            time.sleep(5 * (i + 1))
        except Exception as e:  # ağ hatası
            time.sleep(5 * (i + 1))
    return f"FAIL {period} {codes}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", nargs="+", required=True)
    ap.add_argument("--start", default="2013-01")
    ap.add_argument("--end", default="2026-09")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    periods = [p.strftime("%Y%m") for p in pd.period_range(a.start, a.end, freq="M")]
    jobs = [(p, c) for c in a.codes for p in periods]
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(fetch, p, c) for p, c in jobs]
        for k, f in enumerate(as_completed(futs), 1):
            res = f.result()
            if not res.startswith("skip"):
                print(f"[{k}/{len(jobs)}] {res}", flush=True)


if __name__ == "__main__":
    main()
