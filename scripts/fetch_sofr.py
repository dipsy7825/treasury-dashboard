"""Fetch SOFR rates from the NY Fed public API (no auth required).

Endpoints:
  /api/rates/secured/sofr/search.json   - overnight SOFR history
  /api/rates/secured/sofrai/last/N.json - SOFR Averages and Index (30D/90D/180D)

Outputs:
  data/sofr.json          - snapshot with averages table
  data/sofr_history.json  - trailing ~400 days of overnight SOFR
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

SOFR_HIST_URL = (
    "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
    "?startDate={start}&endDate={end}"
)
SOFR_AI_URL = "https://markets.newyorkfed.org/api/rates/secured/sofrai/last/2.json"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "treasury-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")


def average(values):
    vs = [v for v in values if v is not None]
    if not vs:
        return None
    return round(sum(vs) / len(vs), 4)


def to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=400)
    hist = fetch(SOFR_HIST_URL.format(
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
    )) or []

    # NY Fed returns a list of records directly
    history = []
    for r in hist:
        d = r.get("effectiveDate")
        rate = to_float(r.get("percentRate"))
        if d and rate is not None:
            history.append({"date": d, "sofr": rate})
    history.sort(key=lambda r: parse_date(r["date"]))

    if not history:
        print("ERROR: no SOFR observations.", file=sys.stderr)
        sys.exit(1)

    latest = history[-1]
    prev = history[-2] if len(history) > 1 else None
    latest_dt = parse_date(latest["date"])
    year_start = datetime(latest_dt.year, 1, 1)
    w1_start = latest_dt - timedelta(days=7)
    m1_start = latest_dt - timedelta(days=30)
    w52_start = latest_dt - timedelta(days=365)

    def window_avg(start, end):
        return average([h["sofr"] for h in history if start <= parse_date(h["date"]) <= end])

    # SOFR Averages and Index
    ai = fetch(SOFR_AI_URL) or []
    ai_latest = ai[0] if ai else {}
    ai_prev = ai[1] if len(ai) > 1 else {}

    table = [{
        "rate": "O/N SOFR",
        "current": latest["sofr"],
        "change_bp": round((latest["sofr"] - prev["sofr"]) * 100, 1) if prev else None,
        "avg_1w":  window_avg(w1_start, latest_dt),
        "avg_1m":  window_avg(m1_start, latest_dt),
        "avg_ytd": window_avg(year_start, latest_dt),
        "avg_52w": window_avg(w52_start, latest_dt),
    }]

    for label, field in [
        ("30D Avg SOFR", "average30day"),
        ("90D Avg SOFR", "average90day"),
        ("180D Avg SOFR", "average180day"),
    ]:
        cur = to_float(ai_latest.get(field))
        prv = to_float(ai_prev.get(field))
        chg = round((cur - prv) * 100, 1) if (cur is not None and prv is not None) else None
        table.append({
            "rate": label,
            "current": cur,
            "change_bp": chg,
            "avg_1w": None,
            "avg_1m": None,
            "avg_ytd": None,
            "avg_52w": None,
        })

    snapshot = {
        "latest_date": latest["date"],
        "previous_date": prev["date"] if prev else None,
        "table": table,
        "fetched_at_utc": datetime.utcnow().isoformat() + "Z",
        "source": "https://markets.newyorkfed.org/api/rates/secured/",
    }

    os.makedirs("data", exist_ok=True)
    with open("data/sofr.json", "w") as f:
        json.dump(snapshot, f, indent=2)
    with open("data/sofr_history.json", "w") as f:
        json.dump(history, f, indent=2)

    print(f"Wrote SOFR through {latest['date']} ({len(history)} observations)")


if __name__ == "__main__":
    main()
