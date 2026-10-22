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
| **Digest pipeline** | `digest.py` | The daily job: find new videos, get captions, summarise with Gemini, render, email. Also `--check`. |
| **Chat server** | `chat.py` | A small web server on `127.0.0.1:8765` (this PC only). Builds context from saved notes and captions, calls Gemini, saves chats. |
| **Chat page** | `chat.html` | The browser interface: chat list, scope selectors, answers with clickable citations. |
| **Caption reader** | `ytmd` (external, MIT licence, v0.7.0) | Downloads captions through yt-dlp and stores them in a SQLite full-text index at `%USERPROFILE%\ytmd`. Provides `add`, `read`, `search`, `info`, `doctor`. |
| **yt-dlp** | `bin\yt-dlp.exe` or already installed | Fetches caption files from YouTube for ytmd. |
| **Installer** | `install.bat` + `install.ps1` | One-step Windows setup: Python, yt-dlp, settings, tests, scheduled task, desktop shortcut. |
| **Packager** | `make_package.bat` | Builds `market-digest-setup.zip` from an explicit allow-list of files, so settings and keys can never be included. |
| **Launchers** | `run_digest.bat`, `run_chat.bat` | Written by the installer with the PC's own Python path, and `bin\` on PATH. |
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
7. **Send** (`send`): Gmail over SMTP SSL (port 465) with an app password; HTML plus a plain-text version.
8. **Remember** (`digest_state.json`): videos are marked done, and `last_sent` updated, **only after** the email goes
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
- The YouTube terms-of-service and copyright check required by the original task has not been done yet.
