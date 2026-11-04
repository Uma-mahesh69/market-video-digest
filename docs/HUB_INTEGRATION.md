# Econova Dashboard Hub: reading the daily files

For whoever connects the hub's **Analyst Video Digest** page to the automation. The automation side is done; this
page says what it writes and how the hub's KPIs map onto it.

## A working page

[`econova_dashboard/`](econova_dashboard/) holds a working **Analyst Video Digest** page built on the Claude
Dashboard artifact type: `index.html` (the page, its loaders and its calculations) and `sources.json` (its live
sources). Everything is read through the Google Drive connector each time the page opens:

| Source | What it reads |
|---|---|
| `digests`, `market` | The newest 30 `video-digest_*.json` files and the newest `market-data_*.json` in the json folder |
| `watchlist` | The watchlist sheet (Google Finance prices of the 10 watched stocks, the S&P 500 and the 10-year) |
| `quotes`, `closes` | The **Market Digest Prices** sheet made by `price_sheet.py`: price, day change, 52-week high, P/E and 120 days of closes for every ticker in `tickers.json` |
| `holdings` | The reader's **Google Finance Investment Tracker** (downloaded as .xlsx; the tab whose header has Symbol and # Shares) |

Beyond the user story's KPIs, the page scores the calls against prices:

- **Did the calls work?** Each bullish or bearish call is scored from the close on its video's publish day to the
  latest close, against the S&P 500 over the same days. Edge = how far the stock beat the S&P 500 in the direction
  called. The page shows the hit rate and average edge of bullish and bearish calls, each named analyst's record,
  and the best and worst calls. First result (Oct 15 to Nov 3, 2026, 216 calls): 57 of 164 bullish calls beat the
  S&P 500 (average edge -2.5 points); 27 of 52 bearish calls were right (+1.7 points).
- **Today's calls against the prices**: each stock called today with its 1-month move, distance from the 52-week
  high, P/E and the record of earlier calls on it, flagged when bulls call a stock near its high or after a 10% fall.
- **Your holdings**: the Investment Tracker's holdings by weight (share counts are not shown), each with the last
  14 days of calls, its latest call and the record of earlier calls on it.
- **What matters today**: fixed rules turn the above into a few sentences, such as "Your holding GOOG: 15 bullish
  and 2 bearish calls in 14 days, but it moved -19.1% in a month; earlier calls on it were right 2 of 10 times."

Each live source runs with the reader's own Google Drive access. Claude runs connectors only for readers in the
account that owns the dashboard; for anyone invited from outside it, the page shows "Live data isn't available in
this view". Another person gets their own copy (Duplicate) pointed at Drive files they can read.

## What arrives each day

Two files, in the same folder (`json_dir` in the digest's settings, for example a shared Google Drive folder):

| File | What it holds | Schema |
|---|---|---|
| `video-digest_YYYY-MM-DD.json` | What the analysts said: videos, one row per stock call, themes, debates, levels, upcoming events. No prices. | `digest_schema.json` |
| `market-data_YYYY-MM-DD.json` | The watchlist with Google Finance prices, each stock's calls today and over 7 days, the S&P 500 and the 10-year yield, and up to 5 insight cards plus a "no new views" line. Only when a watchlist sheet is set up. | `market_schema.json` |

- Both files cover the same videos. A second run on the same day rewrites both for the whole day.
- A file is written once that run's email has gone out, so each video is in exactly one day's file.
- A day with no videos still gets a digest file with `video_count: 0`.
- A file is written only after it passes its schema, so a file that exists is complete.
- Past days are never changed, so the folder is the history (mood over time and so on).
- Both schemas accept any `1.x` version: 1.x may add optional fields, never rename or remove one. Read fields by name
  and ignore ones you don't know.

**Checked on real data:** applied to the real Oct 22, 2026 digest (TheStreet, 9 videos), these rules give the
user story's reference values exactly: mood 74% (58 vs 20), consensus buys GOOGL, AMZN, MU, split NVDA, AAPL, META,
CRWV, NFLX, avoid TSLA (2 bearish, 2 mixed), and Nvidia's 7 calls as 7 rows (`tests/test_reference_day.py`).

Days before the JSON export existed can be added from their digest emails or saved digests with
`python email_backfill.py digests/digest-*.html --out <folder>` (see the script's header for what an email can't hold).

Sample files to build against: [`samples/`](samples/). Their analyst calls are made up; the prices are the ones
Google Finance gave on 29 Oct 2026.

## The hub's KPIs (from the user story), mapped to the files

| KPI | Rule | Where the data is |
|---|---|---|
| Analyst mood | bullish ÷ (bullish + bearish) calls; neutral and mixed left out | `video-digest.mentions[].view` |
| Consensus buy | 2+ bullish calls and 0 bearish, per ticker | `mentions[]` grouped by `ticker` |
| Split | at least 1 bullish and 1 bearish | same |
| Avoid | 0 bullish, 1+ bearish or mixed; ranked by bearish + mixed | same |
| S&P target upside | each target ÷ latest S&P close − 1 | `video-digest.videos[].sp500_targets[]` and `market-data.benchmarks.sp500.value` |
| Rate headroom | 10-year concern level − current 10-year yield | `video-digest.levels[]` (unit `%`) and `market-data.benchmarks.us10y.value` |
| Theme strength | videos per theme ÷ `video_count` | `themes[].videos` |

Rows with `ticker: null` are names the lookup table does not know yet (they are listed in the run log); show them
by `name` or leave them out of per-ticker KPIs.

The S&P close and the 10-year yield were the two numbers the user story's KPIs needed but the digest file could not
contain. `market-data.benchmarks` now provides them.

## The insight cards

`market-data.insights[]` is ordered by priority. The first entry is the "no new views" line whenever any watchlist
stock had no calls today. Each card has:

- `type`: `no_new_views`, `experts_vs_price`, `sentiment_shift`, `split`, `catalyst`, `target_upside`,
  `rate_headroom` or `new_views`.
- `tickers`: the stocks it is about; empty for market-wide cards.
- `text`: the sentence to show.
- `look_at_next`: what to look at next. Cards never say buy or sell.
- `video`, `timestamp`, `url`: where to watch it; `url` already includes the `&t=` seconds.

The rules behind each type are in [ARCHITECTURE.md](ARCHITECTURE.md), section 3, step 7.

## Showing prices

`source` holds the line to show with any price: Google Finance via `GOOGLEFINANCE()`, delayed up to 20 minutes,
for information only. All price fields can be `null` (for example a ticker Google Finance does not know).
