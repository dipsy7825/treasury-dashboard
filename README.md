# US Rates Dashboard

Live US Treasury yields, SOFR, and FOMC meeting odds on GitHub Pages. Auto-refreshes weekdays at ~5:30pm ET. Free, no API keys, mobile-friendly.

## What's on it

- **Treasury yields** (2Y, 5Y, 10Y, 30Y) — current, 1W / 1M / YTD / 52W averages, day-over-day bp change
- **SOFR** — overnight + 30D / 90D / 180D rolling averages from NY Fed
- **Next FOMC meeting** — decision date + Polymarket-implied probabilities
- **Yield curve** — current 1M through 30Y
- **YTD trend** — 10Y, 2Y, overnight SOFR

## Setup (5 minutes, in any browser)

You don't need a terminal — everything can be done in Safari, Chrome, or any browser.

1. **Create a new GitHub repo** at [github.com/new](https://github.com/new) — name it `treasury-dashboard` (or anything). Set to **Public** (Public Pages is free; Private Pages needs a paid plan).

2. **Upload these files** — on the new empty repo page, click **uploading an existing file**, then drag the entire `Treasury Dashboard` folder contents (everything from this folder, including the hidden `.github` folder). Commit directly to `main`. **Important: the `.github` folder must be uploaded too** — if Safari/Finder hides it, see the hidden-files note below.

3. **Allow Actions to write** — Settings tab → Actions → General → scroll to **Workflow permissions** → select **Read and write permissions** → Save.

4. **Enable Pages** — Settings tab → Pages → Source: **Deploy from a branch** → Branch: `main`, Folder: `/ (root)` → Save. Wait ~30 seconds, then a green check appears with the URL.

5. **Trigger first data pull** — Actions tab → **Update rates data** → **Run workflow** (button on the right) → Run on `main`. After ~30 seconds it commits the first real `data/yields.json`, `data/sofr.json`, and `data/fed.json`. Pages will then redeploy automatically.

6. **Open the URL** — `https://<your-username>.github.io/treasury-dashboard/`

### Hidden file note (Mac Safari / Finder)

The `.github` folder is hidden by default on Mac. In Finder, press **Cmd + Shift + .** to show hidden files, then drag the whole folder in. GitHub will preserve the folder structure on upload.

## Phone setup

### Option 1 — Home Screen icon (recommended, 30 seconds)

On iPhone Safari: open the URL → tap **Share** → **Add to Home Screen** → name it "Rates" → Add. You get an app-like icon that opens full-screen, no Safari chrome. The dashboard re-fetches fresh data every time you open it.

### Option 2 — True iOS widget (more setup)

iOS doesn't let arbitrary URLs become widgets natively, but you can build one using **Scriptable** (free app on the App Store):

1. Install Scriptable from the App Store
2. Create a new script that fetches `https://<your-username>.github.io/treasury-dashboard/data/yields.json` and renders a widget
3. Long-press home screen → tap **+** → Scriptable → pick your script → choose widget size

I can write the Scriptable JavaScript for you if you want — just ask. A sample widget shows the 10Y / 2Y current + day-over-day in a small/medium card.

### Option 3 — iOS Shortcuts

Apple Shortcuts can fetch JSON and display it. Less polished than Scriptable but no third-party app needed.

## How the live data works

| Source | Endpoint | Frequency |
|---|---|---|
| US Treasury yields | `home.treasury.gov/.../daily-treasury-rates.csv` | Daily by 5pm ET |
| SOFR (overnight + 30/90/180D avg) | `markets.newyorkfed.org/api/rates/secured/` | Daily ~8am ET |
| Next FOMC meeting | Hardcoded in `scripts/fetch_fed.py` (update annually) | — |
| FOMC consensus odds | `gamma-api.polymarket.com/events` | Hourly when active |

The GitHub Actions workflow at `.github/workflows/update-yields.yml` runs all three fetchers on a cron (Mon–Fri 21:30 UTC = ~5:30pm ET) and commits the JSON back to the repo. The dashboard reads from those files on load — same origin, no CORS issues.

## Files

```
treasury-dashboard/
├── index.html
├── README.md
├── .gitignore
├── data/
│   ├── yields.json        (auto-updated)
│   ├── history.json       (auto-updated, ~2yr daily)
│   ├── sofr.json          (auto-updated)
│   ├── sofr_history.json  (auto-updated, ~400 days)
│   └── fed.json           (auto-updated)
├── scripts/
│   ├── fetch_yields.py
│   ├── fetch_sofr.py
│   └── fetch_fed.py
└── .github/workflows/
    └── update-yields.yml
```

## Customization

- **Add more tenors** → edit `TABLE_TENORS` in `scripts/fetch_yields.py`
- **Change refresh cadence** → edit the `cron` line in `.github/workflows/update-yields.yml` (UTC; test at [crontab.guru](https://crontab.guru))
- **Update FOMC dates annually** → edit `FOMC_CALENDAR` list in `scripts/fetch_fed.py`, cross-check against [federalreserve.gov/monetarypolicy/fomccalendars.htm](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- **Add agency / mortgage spreads later** → drop in another `scripts/fetch_*.py`, add a workflow step, render another `<section>` in `index.html`

## Troubleshooting

- **"No data yet" banner shown** — workflow hasn't run. Actions tab → Run workflow.
- **Workflow fails with permissions error** — Settings → Actions → Workflow permissions = "Read and write".
- **Treasury CSV format changes** — edit `URL_TEMPLATE` in `scripts/fetch_yields.py`. Format has been stable since 2021.
- **Polymarket Fed event not found** — script falls back to showing meeting date with "No active market". This is expected between meetings or if Polymarket hasn't listed the next one yet.
