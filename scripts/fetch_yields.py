"""Fetch US Treasury daily yields, compute multi-period averages.

Pulls current year + prior year so trailing 52-week average is computable.

Outputs:
  data/yields.json   - latest snapshot {latest_date, yields (full curve), table (headline tenors w/ averages)}
  data/history.json  - trailing ~2 years of {date, yields: {tenor: pct}}
"""

import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

URL_TEMPLATE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all"
    "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)

MATURITIES = [
    "1 Mo", "1.5 Month", "2 Mo", "3 Mo", "4 Mo", "6 Mo",
    "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr",
]

TABLE_TENORS = ["2 Yr", "5 Yr", "10 Yr", "30 Yr"]


def fetch_year(year):
    url = URL_TEMPLATE.format(year=year)
    req = urllib.request.Request(url, headers={"User-Agent": "treasury-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig")


def parse_date(s):
    return datetime.strptime(s, "%m/%d/%Y")


def parse_rows(text):
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        date_str = (r.get("Date") or "").strip()
        if not date_str:
            continue
        obs = {"date": date_str, "yields": {}}
        for m in MATURITIES:
            v = (r.get(m) or "").strip()
            if v in ("", "N/A"):
                continue
            try:
                obs["yields"][m] = float(v)
            except ValueError:
                continue
        if obs["yields"]:
            rows.append(obs)
    return rows


def average(values):
    vs = [v for v in values if v is not None]
    if not vs:
        return None
    return round(sum(vs) / len(vs), 4)


def main():
    this_year = datetime.utcnow().year
    prior_year = this_year - 1

    try:
        cur_text = fetch_year(this_year)
    except Exception as exc:
        print(f"ERROR fetching current year: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        prior_text = fetch_year(prior_year)
    except Exception as exc:
        print(f"WARNING: failed to fetch prior year: {exc}", file=sys.stderr)
        prior_text = ""

    rows = parse_rows(cur_text) + parse_rows(prior_text)
    seen = set()
    history = []
    for r in rows:
        if r["date"] in seen:
            continue
        seen.add(r["date"])
        history.append(r)
    history.sort(key=lambda r: parse_date(r["date"]))

    if not history:
        print("ERROR: no observations.", file=sys.stderr)
        sys.exit(1)

    for h in history:
        h["__dt"] = parse_date(h["date"])

    latest = history[-1]
    prev = history[-2] if len(history) > 1 else None
    latest_dt = latest["__dt"]
    year_start = datetime(latest_dt.year, 1, 1)
    w1_start = latest_dt - timedelta(days=7)
    m1_start = latest_dt - timedelta(days=30)
    w52_start = latest_dt - timedelta(days=365)

    def window_avg(tenor, start, end):
        return average([h["yields"].get(tenor) for h in history if start <= h["__dt"] <= end])

    table = []
    for tenor in TABLE_TENORS:
        cur = latest["yields"].get(tenor)
        prv = prev["yields"].get(tenor) if prev else None
        chg_bp = round((cur - prv) * 100, 1) if (cur is not None and prv is not None) else None
        table.append({
            "tenor": tenor,
            "current": cur,
            "change_bp": chg_bp,
            "avg_1w":  window_avg(tenor, w1_start, latest_dt),
            "avg_1m":  window_avg(tenor, m1_start, latest_dt),
            "avg_ytd": window_avg(tenor, year_start, latest_dt),
            "avg_52w": window_avg(tenor, w52_start, latest_dt),
        })

    snapshot = {
        "latest_date": latest["date"],
        "previous_date": prev["date"] if prev else None,
        "yields": {m: latest["yields"].get(m) for m in MATURITIES if latest["yields"].get(m) is not None},
        "table": table,
        "fetched_at_utc": datetime.utcnow().isoformat() + "Z",
        "source": URL_TEMPLATE.format(year=this_year),
    }

    os.makedirs("data", exist_ok=True)
    with open("data/yields.json", "w") as f:
        json.dump(snapshot, f, indent=2)

    history_out = [{"date": h["date"], "yields": h["yields"]} for h in history]
    with open("data/history.json", "w") as f:
        json.dump(history_out, f, indent=2)

    print(f"Wrote {len(history)} observations through {latest['date']}")


if __name__ == "__main__":
    main()
