# Architecture

How the Market Video Digest works inside. Written for a developer joining the project, but each section starts with
a plain-language summary.

## 1. The big picture

> In one sentence: a scheduled Python script finds new YouTube videos, reads their captions, asks Gemini to turn
> each one into structured notes, and emails a digest; a small local web server lets you chat over the same notes.

```
                         every morning (Windows Task Scheduler)
                                         |
                                         v
 YouTube channel  --RSS feed-->  digest.py  --ytmd + yt-dlp-->  captions  ("[12:34] text")
 (public uploads feed,              |
  no API key)                       |  one request per video
                                    v
                              Google Gemini  --JSON notes-->  digest_cache/<video>.json
                                    |
                                    |  one request for the day's overview
                                    v
                          HTML digest  --SMTP (Gmail)-->  your inbox
                                    \--> digests/digest-YYYY-MM-DD-HHMM.html

 You  --browser-->  chat.html  --HTTP 127.0.0.1:8765-->  chat.py
                                                         |  notes + matching caption passages
                                                         v
                                                   Google Gemini  --> answer with [V2 12:34] citations
                                                         \--> chats.json
```

## 2. Components

| Component | File | What it does |
|---|---|---|
| **Digest pipeline** | `digest.py` | The daily job: find new videos, get captions, summarise with Gemini, render, email. Also `--check` and `--rebuild`. |
| **Chat server** | `chat.py` | A small web server on `127.0.0.1:8765` (this PC only). Builds context from saved notes and captions, calls Gemini, saves chats. |
| **Chat page** | `chat.html` | The browser interface: chat list, scope selectors, answers with clickable citations. |
| **Caption reader** | `ytmd` (external, MIT licence, v0.7.0) | Downloads captions through yt-dlp and stores them in a SQLite full-text index at `%USERPROFILE%\ytmd`. Provides `add`, `read`, `search`, `info`, `doctor`. |
| **yt-dlp** | `bin\yt-dlp.exe` or already installed | Fetches caption files from YouTube for ytmd. |
| **Installer** | `install.bat` + `install.ps1` (Windows), `install-mac.command` (Mac) | One-step setup: Python, yt-dlp, settings, tests, daily schedule (Task Scheduler on Windows, a launchd agent on a Mac), desktop shortcut. |
| **Packager** | `make_package.bat` | Builds `market-digest-setup.zip` from an explicit allow-list of files, so settings and keys can never be included. |
| **Launchers** | `run_digest.bat`, `run_chat.bat` (Windows); `run_digest.sh`, `run_chat.command` (Mac) | Written by the installer with the computer's own Python path, and `bin` on PATH. On a Mac, `run_digest.sh` also retries a failed run every 30 minutes, 3 times, as Task Scheduler does on Windows. |
| **JSON export** | `digest_export.py`, `digest_schema.json`, `tickers.json` | Builds, checks and saves the day's JSON file for the Econova hub. |
| **Watchlist** | `market_data.py`, `market_schema.json`, `watchlist_template.csv` | Reads the watchlist sheet (Google Finance prices), finds the insight cards, saves the market-data file; `--coverage` counts recent mentions per stock. |
| **Backfill** | `email_backfill.py` | Turns digests already sent (saved HTML or the email) back into the day's JSON file, through the same export. |
| **Dashboard page** | `docs/econova_dashboard/` | The Analyst Video Digest page that reads the daily files and the watchlist sheet live from Google Drive. |
| **Tests** | `tests/test_digest_export.py`, `tests/test_digest_run.py` | `python -m unittest` in the project folder runs them; no network needed. |
| **Earlier prototype** | `ask.py` (workshop folder only) | The first Q&A tool (one question, cited answer). Not part of the installed product. |

## 3. The daily run, step by step (`digest.py`, `main()`)

1. **Wait for the internet** (`wait_for_internet`): tries `www.youtube.com:443` every 30 s for up to 15 minutes.
   A run started as the PC wakes would otherwise find and send nothing. If it gives up, it exits with code 1 so Task
   Scheduler retries.
2. **Find new videos** (`channel_id`, `latest_uploads`): each channel link becomes a `UC...` id (looked up once and
   remembered in `digest_state.json`), then the public Atom feed
   `youtube.com/feeds/videos.xml?channel_id=...` lists the latest 15 uploads. No API key needed.
   - **Window:** everything since the last digest that went out (minus 1 hour), capped at 7 days. First run, or with
     `--hours`: `lookback_hours` (26).
   - Already-done videos are skipped. At most `max_videos` (20), newest first.
   - One broken channel does not stop the run. It is listed in a warning banner in the digest.
3. **Read captions** (`transcript`): `ytmd add` then `ytmd read` (paged), giving lines like `[12:34] text` so every
   point can link to its moment. Capped at 150,000 characters. Runs **one at a time** (a lock), because ytmd writes a
   single SQLite file.
   - Videos with no captions raise `Skip` and are recorded as permanently skipped. Other errors count as temporary and
     are retried the next day.
   - ytmd is started with `PYTHONUTF8=1`, because Windows otherwise returns its output in the local code page and
     titles with ’ break the reading.
4. **Summarise** (`extract`): one Gemini request per video, with a fixed JSON schema (summary, speakers, key points,
   market levels, stocks with view and reason, sectors, predictions, risks, upcoming events, each with a time).
   **Three videos at a time** (`WORKERS = 3`). Results are cached in `digest_cache/<id>.json`, so a video is never
   paid for twice.
   - `clean_notes` drops malformed items, drops times beyond the video's length, and forces views to
     bullish/bearish/neutral/mixed.
5. **Overview** (`day_summary`): one more request turns all the notes into an overview, themes and disagreements.
   Video numbers are validated by code.
6. **Render** (`render`): HTML built in code from the notes. The stock table is grouped by ticker in code, not
   written by the model. Unclear figures are marked "(check)". All text is HTML-escaped.
7. **JSON copy** (`digest_export.py`): the same content saved as `video-digest_YYYY-MM-DD.json` in `json_dir`
   (default `digest_json\`), for the Econova Dashboard Hub. The shape is fixed by `digest_schema.json` (schema 1.0):
   videos, one `mentions` row per stock call, themes, debates with sides, levels and upcoming events, each with its
   video number and timestamp. Stock names are merged into tickers with `tickers.json` (also trying the name without
   "Inc.", "Corporation" and the like); a name with no entry gets `ticker: null` and a line in `digest.log`.
   - **One file per day, covering the whole day.** A run only picks up videos not yet sent, so a second run on the
     same day (a manual `--open` after the morning run) adds its videos to the day's file from the saved notes and
     redoes the overview; it never replaces the morning's videos. The video ids in today's file are kept in
     `digest_state.json` (`json_day`). A run with nothing new leaves the file as it is. A day with no videos at all
     still gets a file with `video_count: 0`.
   - **Checked before saving.** On any schema problem, or if the folder cannot be written, nothing is saved and the
     reason is logged with the date. Earlier days' files are never touched. The schema accepts any 1.x file, because
     1.x may add optional fields.
   - **Tests and past days.** `--dry-run` and `--video` write to `digests\`, so a test cannot replace the real file.
     `--rebuild YYYY-MM-DD` writes the file for an earlier day's digest (the videos recorded as sent that day),
     summarising again any video whose notes were saved before the JSON fields existed. It refuses to overwrite an
     existing file; with `--dry-run` it writes to `digests\`.
   - Scoring (mood, consensus, upside) is done by the hub, not here.
   - **Watchlist and prices** (`market_data.py`, when `watchlist_csv` is set). The watchlist is a Google Sheet whose
     `GOOGLEFINANCE()` formulas give price, day and week change, 52-week range, P/E and market cap, plus two
     benchmark rows: the S&P 500 (`INDEXSP:.INX`) and the 10-year yield (`INDEXCBOE:TNX`, quoted as the yield
     times 10). The sheet is read as CSV from its "Publish to web" link (no API key, standard library only).
     `market_brief` joins it with the day's stock calls and with the last 14 days of calls in `digest_cache`, and
     applies fixed rules (no model call): experts vs price (the week's calls lean one way, the price moved 5% or
     more the other way), sentiment shift (this week's bullish share a third or more away from last week's), split
     today, a catalyst in "Coming up", S&P 500 target vs today's level, 10-year concern level vs today's yield, new
     calls today, and the stocks with no new views. Up to 5 cards, in that order of priority, go into the email's
     "Your watchlist" section and into `market-data_YYYY-MM-DD.json` (schema `market_schema.json`), saved next to
     the digest file and covering the same videos. Prices stay out of `video-digest_*.json`, which holds only what
     analysts said. A sheet that cannot be read gives a note in the email and no market file; the digest goes on.
8. **Send** (`send`): Gmail over SMTP SSL (port 465) with an app password; HTML plus a plain-text version.
9. **Remember** (`digest_state.json`): videos are marked done, and `last_sent` updated, **only after** the email goes
   out. If sending fails, nothing is marked, and the run exits with code 1 so Windows retries in 30 minutes.

## 4. Talking to Gemini (`call_gemini`)

- REST `generateContent` at `generativelanguage.googleapis.com/v1beta`, key in the `x-goog-api-key` header,
  JSON output for the digest. 120-second timeout.
- **Model chain:** models are tried in the order of `models` (default 3.7 Flash, 3.6 Flash, 3 Flash, 3.5 Flash Lite,
  3.1 Flash Lite). A model that returns 429/500/503, times out or drops the connection is **rested for 10 minutes** and
  the next one is tried immediately. If every model fails, wait 20 s and try them all once more. Errors 400, 401 and
  403 (bad request or bad key) stop at once, because every model would fail the same way.
- **Why:** on the free tier, Flash models allow 20 requests/day each and Flash Lite 500/day (measured 15 Oct 2026), and
  the Flash models are often overloaded. The old design (long retries on one model) took 20+ minutes per run and
  burned the daily quota on retries.

## 5. The chat (`chat.py` + `chat.html`)

1. The page asks `/api/state` for the saved videos (from `digest_cache/`) and past chats.
2. A question goes to `/api/ask` with a scope: last N days, all videos, or one video.
3. **Context** (`context`): numbered videos (V1, V2...) with their notes, plus either:
   - **one video:** its full transcript (up to 120,000 characters), or
   - **several videos:** caption passages matching the question's keywords (`ytmd search`, up to 12 passages).
4. Gemini answers under two headings: **From your channels** (citations like `[V2 12:34]`) and **From the web**.
5. With web search ticked, the first two models are tried once with Google Search grounding. If that fails (no free
   search quota), the answer is made from the videos only and says so.
6. The page turns `[V2 12:34]` into links to that moment. Citations to videos that don't exist are dropped.
   Web sources are listed as links. Google's search suggestions are shown in a sandboxed frame.
7. Chats are saved in `chats.json`.

**Endpoints:** `GET /` (page), `GET /api/state`, `GET /api/chat?id=`, `POST /api/ask`, `POST /api/delete`,
`POST /api/rename`.

## 6. Files and data

| Path (in the install folder) | Contents | Sensitive? |
|---|---|---|
| `digest_config.json` | Settings, Gemini key, Gmail app password | **Yes. Never share or commit.** |
| `digest_state.json` | Channel ids, done/skipped videos, `last_sent` | No |
| `digest_cache\<id>.json` | Gemini's notes per video | No |
| `digests\*.html` | Every digest as a web page | No |
| `digest_json\video-digest_YYYY-MM-DD.json` (or `json_dir`) | The day's digest as JSON for the Econova hub | No |
| `digest_json\market-data_YYYY-MM-DD.json` (or `json_dir`) | Watchlist prices, analyst calls per stock and the insight cards | No |
| `watchlist_template.csv` | The watchlist sheet's formulas, to import into Google Sheets | No |
| `tickers.json` | Company name to ticker lookup. Add a line when the log reports an unmatched name | No |
| `chats.json` | Saved chats | Private |
| `digest.log` | Output of scheduled runs | No |
| `%USERPROFILE%\ytmd\` | Transcripts and the search index (ytmd library) | No |

## 7. Dependencies

- **Python 3.9+** (the installer installs 3.13 if needed). **Standard library only**; there are no pip packages.
- **ytmd** (bundled) and **yt-dlp** (on PATH or downloaded to `bin\`).
- **Google Gemini API** (free tier works). **Gmail SMTP** for email (optional).
- **Windows Task Scheduler** and PowerShell 5.1 (built into Windows).

## 8. Reliability and safety choices

| Choice | Reason |
|---|---|
| Mark videos done only after the email is sent | A crash or failed email never loses videos. |
| Catch up since the last digest (up to 7 days) | Days the PC was off are not lost. |
| Wait for internet, exit code 1 on failure, task retries 3 x 30 min | A run started before Wi-Fi connects still delivers that day. |
| `StartWhenAvailable` on the task | A missed time runs when the PC is next on. |
| Model chain with resting | Fast despite overloaded models and small free quotas. |
| Cache Gemini notes per video | Re-runs and the chat cost no extra quota. |
| Chat server bound to `127.0.0.1`, Host-header check, JSON-only POSTs | Only this PC can use it; other web pages can't call it. |
| Key never sent to the browser | The chat page talks only to `chat.py`; `chat.py` talks to Gemini. |
| All model text HTML-escaped, citations resolved by code | Model output can't inject HTML or invent sources. |
| Packager uses an allow-list | `digest_config.json` cannot end up in the shared zip. |

## 9. Known limits

- Runs only when the PC is on, and the chat only works on that PC (no phone access).
- Free tier: about 20 Flash-quality summaries a day per model; beyond that, Flash Lite (lower quality) does the work.
- No web search in the chat without billing.
- Captions are automatic: names and numbers can be misheard.
- Shorts usually have no captions and are skipped.
- `generateContent` is Google's older ("legacy") API style; Google now recommends the Interactions API. It still works.
- Watchlist prices come from `GOOGLEFINANCE()`: delayed up to 20 minutes, US-centred, and Google says not for trading.
  It has no earnings dates, so the "catalyst" card relies on what the videos say. Whether a published sheet keeps
  recalculating when nobody has it open has not been checked over several days.
- The YouTube terms-of-service and copyright check required by the original task has not been done yet.
