# Econova Dashboard Hub: reading the daily files

For whoever connects the hub's **Analyst Video Digest** page to the automation. The automation side is done; this
page says what it writes and how the hub's KPIs map onto it.

## What arrives each day

Two files, in the same folder (`json_dir` in the digest's settings, for example a shared Google Drive folder):

| File | What it holds | Schema |
|---|---|---|
| `video-digest_YYYY-MM-DD.json` | What the analysts said: videos, one row per stock call, themes, debates, levels, upcoming events. No prices. | `digest_schema.json` |
| `market-data_YYYY-MM-DD.json` | The watchlist with Google Finance prices, each stock's calls today and over 7 days, the S&P 500 and the 10-year yield, and up to 5 insight cards plus a "no new views" line. Only when a watchlist sheet is set up. | `market_schema.json` |

- Both files cover the same videos. A second run on the same day rewrites both for the whole day.
- A day with no videos still gets a digest file with `video_count: 0`.
- A file is written only after it passes its schema, so a file that exists is complete.
- Past days are never changed, so the folder is the history (mood over time and so on).
- Both schemas accept any `1.x` version: 1.x may add optional fields, never rename or remove one. Read fields by name
  and ignore ones you don't know.

**Checked on real data:** applied to the real Oct 22, 2026 digest (TheStreet, 9 videos), these rules give the
user story's reference values exactly: mood 74% (58 vs 20), consensus buys GOOGL, AMZN, MU, split NVDA, AAPL, META,
CRWV, NFLX, avoid TSLA (2 bearish, 2 mixed), and Nvidia's 7 calls as 7 rows (`tests/test_reference_day.py`).

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
