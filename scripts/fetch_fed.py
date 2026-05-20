"""Fetch next FOMC meeting and Polymarket-implied probabilities.

Strategy:
  1. Look up next FOMC meeting from hardcoded calendar (verify annually against federalreserve.gov).
  2. Query Polymarket gamma API for active "Fed rates" events.
  3. Pick the event whose end date is closest to the next meeting.
  4. Extract sub-market probabilities (Yes prices).

Outputs:
  data/fed.json - { next_meeting, probabilities[], event_title, source_url, ... }
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# 2026 + 2027 FOMC decision-day dates (second day of two-day meetings).
# Source: federalreserve.gov/monetarypolicy/fomccalendars.htm
# UPDATE ANNUALLY. Hardcoded so the dashboard doesn't break if the Fed page changes layout.
FOMC_CALENDAR = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-16",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16",
    "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-15",
]

POLYMARKET_EVENTS = "https://gamma-api.polymarket.com/events"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "treasury-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def next_fomc():
    today = datetime.utcnow().date()
    for d in FOMC_CALENDAR:
        meeting = datetime.strptime(d, "%Y-%m-%d").date()
        if meeting >= today:
            return meeting
    return None


def parse_end(e):
    ed = e.get("endDate") or ""
    try:
        return datetime.fromisoformat(ed.replace("Z", "+00:00"))
    except Exception:
        return None


def find_fed_event(target_date):
    """Find Polymarket event for the Fed decision around target_date.

    Tries tag slug first, then keyword fallback.
    """
    candidates = []
    for params in (
        {"active": "true", "closed": "false", "tag_slug": "fed-rates", "limit": "50"},
        {"active": "true", "closed": "false", "tag": "Fed Rates",      "limit": "50"},
    ):
        try:
            url = POLYMARKET_EVENTS + "?" + urllib.parse.urlencode(params)
            events = fetch(url) or []
            if events:
                candidates = events
                break
        except Exception:
            continue

    if not candidates:
        try:
            url = POLYMARKET_EVENTS + "?" + urllib.parse.urlencode({"active": "true", "closed": "false", "limit": "100"})
            all_events = fetch(url) or []
            candidates = [
                e for e in all_events
                if "fed" in (str(e.get("title", "")).lower() + " " + str(e.get("slug", "")).lower())
                and ("decision" in str(e.get("title", "")).lower() or "rate" in str(e.get("title", "")).lower())
            ]
        except Exception:
            return None

    if not candidates:
        return None

    # Filter to events ending on/after target_date, then earliest first
    valid = [(e, parse_end(e)) for e in candidates]
    valid = [(e, end) for e, end in valid if end is not None]
    if not valid:
        return None
    valid.sort(key=lambda x: x[1])

    if target_date:
        for e, end in valid:
            if end.date() >= target_date:
                return e
    return valid[0][0]


def extract_probabilities(event):
    if not event:
        return []
    markets = event.get("markets") or []
    probs = []
    for m in markets:
        label = m.get("groupItemTitle") or m.get("question") or ""
        prices_raw = m.get("outcomePrices")
        try:
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else (prices_raw or [])
        except Exception:
            prices = []
        if not prices:
            continue
        try:
            p = float(prices[0])  # Yes price = probability outcome occurs
        except (TypeError, ValueError):
            continue
        probs.append({"label": label, "value": round(p, 4)})
    probs.sort(key=lambda x: -x["value"])
    return probs


def main():
    next_dt = next_fomc()
    event = None
    probs = []
    try:
        event = find_fed_event(next_dt) if next_dt else None
        probs = extract_probabilities(event)
    except Exception as exc:
        print(f"WARNING: Polymarket lookup failed: {exc}", file=sys.stderr)

    snapshot = {
        "next_meeting": next_dt.isoformat() if next_dt else None,
        "probabilities": probs,
        "event_title": event.get("title") if event else None,
        "event_slug": event.get("slug") if event else None,
        "source_url": ("https://polymarket.com/event/" + event["slug"]) if event and event.get("slug") else None,
        "fetched_at_utc": datetime.utcnow().isoformat() + "Z",
        "calendar_source": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }

    os.makedirs("data", exist_ok=True)
    with open("data/fed.json", "w") as f:
        json.dump(snapshot, f, indent=2)

    # Append to history (deduped by probability values, trimmed to last 90 days)
    history_path = "data/fed_history.json"
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history = json.load(f) or []
        except (json.JSONDecodeError, IOError):
            history = []

    new_entry = {
        "timestamp": snapshot["fetched_at_utc"],
        "next_meeting": snapshot["next_meeting"],
        "event_slug": snapshot["event_slug"],
        "probabilities": probs,
    }

    # Always append so the chart has a heartbeat data point, even when prices are stable.
    # Only skip if we appended within the last 10 minutes (guards against duplicate workflow triggers).
    should_append = True
    if history and probs:
        last = history[-1]
        try:
            last_ts = datetime.fromisoformat(last.get("timestamp", "").replace("Z", ""))
            if (datetime.utcnow() - last_ts).total_seconds() < 600:
                should_append = False
        except (TypeError, ValueError):
            pass

    if should_append and probs:
        history.append(new_entry)

    # Trim to last 90 days
    cutoff = datetime.utcnow() - timedelta(days=90)
    def in_window(h):
        try:
            ts = h.get("timestamp", "").replace("Z", "")
            return datetime.fromisoformat(ts) >= cutoff
        except (TypeError, ValueError):
            return True
    history = [h for h in history if in_window(h)]

    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    print(f"Next FOMC: {snapshot['next_meeting']}, Polymarket event: {snapshot['event_title']}, outcomes: {len(probs)}, history entries: {len(history)}")


if __name__ == "__main__":
    main()
