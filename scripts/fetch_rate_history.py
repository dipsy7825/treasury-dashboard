"""Fetch historical FOMC decisions from FRED (DFEDTARU series) and compute bp changes.

Cross-references each FOMC meeting in the past 12 months against the Fed funds target
upper bound on either side of the meeting date to derive the bp change.

Outputs:
  data/rate_history.json - past 12 months of FOMC decisions with bp change at each

Source: https://fred.stlouisfed.org/series/DFEDTARU (Federal Funds Target Range - Upper Limit)
"""

import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU"

# FOMC decision-day dates (Day 2 of two-day meetings).
# Source: federalreserve.gov/monetarypolicy/fomccalendars.htm
# UPDATE ANNUALLY. Keep ~3 years of history so the script can build a 1-year backward view.
FOMC_DATES = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-17",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-16",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16",
    "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-15",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "treasury-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def main():
    try:
        csv_text = fetch(FRED_URL)
    except Exception as exc:
        print(f"ERROR fetching FRED: {exc}", file=sys.stderr)
        sys.exit(1)

    reader = csv.DictReader(io.StringIO(csv_text))
    rate_by_date = {}
    for row in reader:
        # FRED CSVs use either "observation_date" or "DATE" as the date column header,
        # and the series id (DFEDTARU) as the value column.
        date_val = (row.get("observation_date") or row.get("DATE") or "").strip()
        rate_val = (row.get("DFEDTARU") or "").strip()
        if not date_val or rate_val in ("", ".", "NA"):
            continue
        try:
            rate_by_date[date_val] = float(rate_val)
        except ValueError:
            continue

    if not rate_by_date:
        print("ERROR: no FRED data parsed", file=sys.stderr)
        sys.exit(1)

    today = datetime.utcnow().date()
    cutoff = today - timedelta(days=365)

    decisions = []
    for meeting_str in FOMC_DATES:
        meeting_dt = datetime.strptime(meeting_str, "%Y-%m-%d").date()
        # Only past meetings within the last 365 days
        if meeting_dt < cutoff or meeting_dt > today:
            continue

        # Post-decision rate: look forward up to 5 calendar days
        post_rate = None
        for fwd in range(0, 6):
            d = (meeting_dt + timedelta(days=fwd)).strftime("%Y-%m-%d")
            if d in rate_by_date:
                post_rate = rate_by_date[d]
                break

        # Pre-decision rate: look back up to 10 calendar days
        pre_rate = None
        for back in range(1, 11):
            d = (meeting_dt - timedelta(days=back)).strftime("%Y-%m-%d")
            if d in rate_by_date:
                pre_rate = rate_by_date[d]
                break

        if post_rate is None or pre_rate is None:
            continue

        change_bp = round((post_rate - pre_rate) * 100)
        if change_bp > 0:
            label = f"+{change_bp} bp"
        elif change_bp < 0:
            label = f"{change_bp} bp"
        else:
            label = "Hold"

        decisions.append({
            "date": meeting_str,
            "upper_target": post_rate,
            "lower_target": round(post_rate - 0.25, 2),
            "change_bp": change_bp,
            "label": label,
        })

    snapshot = {
        "decisions": decisions,
        "source": "https://fred.stlouisfed.org/series/DFEDTARU",
        "fetched_at_utc": datetime.utcnow().isoformat() + "Z",
    }

    os.makedirs("data", exist_ok=True)
    with open("data/rate_history.json", "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Wrote {len(decisions)} FOMC decisions in trailing 12 months")


if __name__ == "__main__":
    main()
