 HANDOFF: YouTube knowledge base, Ask Keeper, and Market Video Digest

Written 2026-10-12 for Claude Code. It records what was said and built. Nothing is invented.

**Labels used**
- **[CONFIRMED]** the user said it, or the user ran it and reported the result.
- **[BUILT]** code exists and I tested it only against mocks or in the sandbox.
- **[SUGGESTED]** I proposed it and the user has not clearly accepted it.
- **[OPEN]** unresolved or unknown.

---

## 0a. Updates after this document was first written (2026-10-12) [CONFIRMED by the user]

- **Ask Keeper is dropped.** Ignore all Ask Keeper work (§1 item 3, §4 "Ask Keeper v0.6", the v0.x zips, extension tasks in §6). Focus is the **daily digest + chat over the digest**.
- **Anil would install and run it on his own device.** This replaces the "laptop only" assumption. Consequences, not yet decided: the digest, the cache and the chat must all live on the same machine, and that machine must be on at the scheduled time. Anil would need Python, `ytmd`, a Gemini key and email settings. A one-step installer would be a likely task.

---

## 0. Read this first

- The user is **Narava Uma Mahesh (GTTECH)**. It was his **first day as an AI engineering intern** at the early-stage startup **Nugenix AI**. He said he does not know much, and he wants to learn by doing.
- His manager is **Anil Peketi** (contact@nugenix-ai.com). The user calls him "sir".
- The user works on **Windows**. His folders are `C:\Users\user\yt-kb\` (scripts), `C:\Users\user\ytmd\` (transcript library) and `C:\Users\user\Downloads\ask-keeper\ask-keeper\` (loaded Chrome extension).
- The cloud sandbox **cannot reach YouTube or Gemini**. Nothing that needs them has been run by me. The user runs those parts and pastes back the output or a screenshot.
- The latest code exists **only** in the delivered files in `/mnt/user-data/outputs/`: `market-digest.zip`, `digest.py`, `chat.py`, `chat.html`, `run_chat.bat`, `ask.py`, and `ask-keeper-v0.2.zip` to `ask-keeper-v0.6.zip` (v0.6 is latest; `ask-keeper.zip` is v0.1).
- My scratch trees (`/tmp/ak`, `/tmp/dg`) and the Playwright tests are **gone**. See §8.
- **Never commit or print secrets.** `digest_config.json` holds the Gemini key and a Gmail app password.

---

## 1. Vision, goals, users

### Original task [CONFIRMED]
A screenshot of a task doc from Anil, with these acceptance criteria:
1. Given a YouTube URL, produce transcript chunks with metadata (title, URL, timestamp).
2. Given a sample question, return the relevant chunks.
3. (Stretch) A Q&A demo that cites its source.

Out of scope in that doc:
- a production vector database
- ingesting content without a copyright / terms-of-service check
- an advisor-facing "Econova" feature (this is internal tooling)

### How the work evolved [CONFIRMED]
1. **Transcript pipeline** (`ytmd` plus `ask.py`). The user demoed it.
2. **Second use case: YouTube Shorts transcripts**, from TheStreet shorts. The three methods in §6 were to be tried on 10 Shorts.
3. **Ask Keeper**, a Chrome extension. It captures YouTube's native Ask Q&A into a local library, for the user plus 5–6 workspace colleagues. No public distribution.
4. **After the demo, Anil said it was "not at all enough".** He wants to catch up on finance/market news **without watching or querying videos**: trends, market parameters, stocks, and the channel's take. The delivery is a daily digest or newsletter covering every YouTube channel he follows, and each new upload should flow through automatically.
5. **Chat over the digest.** Questions, comparisons and analysis grounded in the videos **plus outside-world (web) information**, in a "clean, neat interface for all the chats". The user's decision: "keep it simple, integrated to the digest".

### Target users
- Primary: **Anil**, a finance-oriented reader.
- Secondary: the user, and 5–6 colleagues for the extension.
- [OPEN] Anil's exact channel list. The user chose "Start with **TheStreet**" only.

---

## 2. Requirements

### Functional
- **Pipeline (`ask.py`)** [BUILT, live-verified by the user]
  - Transcript → timestamped chunks with title, URL and time.
  - Keyword retrieval.
  - Gemini answers with `[C#]` citations.
  - It refuses with `NOT_FOUND` when the evidence is missing.
- **Ask Keeper** [CONFIRMED requirements]
  - Record **only when a question was sent and an answer received**.
  - Store locally, with no backend and no extra model.
  - Searchable, organised by video, channel, chapter and playlist.
  - Notes, subjects, review mode and export.
  - Later additions the user asked for: side-thread follow-ups, thumbnails, channel pictures, day/time grouping, and a sidebar where each channel opens out to its videos and chats.
- **Daily digest** [CONFIRMED]
  - Covers the channels he follows, automatic per new upload, delivered **by email**.
  - Runs on the user's **laptop**, uses **Gemini**, and starts with **TheStreet**.
- **Chat over the digest** [CONFIRMED]
  - Digest videos plus the web, with a simple chat interface integrated with the digest.

### Non-functional
- Prefer **no private/undocumented endpoints**. YouTube's terms were to be assessed [OPEN, see §6].
- Minimal dependencies. All Python is **stdlib only** except the external `ytmd` CLI.
- Beginner-runnable on Windows: `.bat` launchers, a Task Scheduler recipe.
- Captured text is rendered with `textContent` only (XSS safety).
- Citations are resolved **by code, not by the model**. Invalid markers are dropped.
- No model call when retrieval finds nothing.

---

## 3. Decisions and reasoning

| Decision | Status | Reasoning |
|---|---|---|
| Use existing **ytmd** (gvkhosla/ytmd, MIT) instead of building on the GitHub repo `Anirudh2627/YouTube-RAG` | [CONFIRMED] | The user asked for the most-matched existing tool. ytmd gave chunks, metadata and FTS5 search directly. |
| Run ytmd with `python ytmd` (single file) | [CONFIRMED] | `pipx install` failed (setuptools flat-layout, several top-level packages). |
| yt-dlp rather than `youtube-transcript-api` | [CONFIRMED, explained to user] | ytmd's own docs prefer it. The user asked for this reasoning to explain to his manager. |
| **Gemini**, not Claude | [CONFIRMED] | The user has a Gemini API key. He said "doesn't matter claude or gemini". Gemini was chosen for the digest. |
| LLM on top of keyword search | [CONFIRMED] | The user asked why. The LLM turns passages into a readable, cited answer. It adds nothing if the user only wants chunks. |
| Ask Keeper reads the **page DOM** after a question is sent | [CONFIRMED] | It avoids private endpoints. It captures only on a sent question with an answer received. |
| Ask Keeper is a Chrome MV3 extension with `chrome.storage.local` + `unlimitedStorage` | [CONFIRMED] | No backend. Data is local. |
| Share the extension as an unpacked folder | [CONFIRMED] | Only 5–6 colleagues. The "Load unpacked" steps were given. |
| Digest runs on the **laptop** by Task Scheduler, delivers by **email**, uses **Gemini**, starts with **TheStreet** | [CONFIRMED] | These were the user's answers to my questions. |
| Mark videos "done" only **after** the email is sent | [BUILT] | A crash must not lose videos. Email failure leaves them for the next run. |
| Videos with no captions are recorded as "skipped" and not retried; temporary failures are retried | [BUILT] | Uses ytmd's `PERMANENT` error codes. |
| Chat is a local web page (`chat.py` on 127.0.0.1:8765) | [CONFIRMED by the user's "keep it simple, integrated to the digest"] | The user picked the laptop chat page. See the access problem in §6. |
| Web information through Gemini **Google Search grounding** | [BUILT, unverified live] | One API and one key. |
| Replying to the digest email as the manager's way to ask questions | [SUGGESTED] | The simplest way for Anil to ask without access to the laptop. The user has not decided. |
| Try Gemini for a week, then re-evaluate Claude vs Gemini (about 10 Oct) | [OPEN] | Stated in an earlier exchange. No outcome recorded. |

---

## 4. Architecture

```
Transcript KB (ask.py)
  URL ──ytmd add──> SQLite FTS5 (~/ytmd, override YTMD_DIR) ──ytmd search──> passages
  question ──> ask.py ──> Gemini (numbered passages, cite [C1]) ──> answer + timestamp links

Ask Keeper (Chrome MV3)
  youtube.com Ask panel ──content.js (MutationObserver)──> chrome.storage.local ──> popup / library page

Market digest
  channel list ──RSS feeds──> new video ids ──ytmd (captions)──> transcript ("[m:ss] text")
     ──Gemini JSON extraction──> digest_cache/<id>.json ──Gemini day overview──> HTML email (SMTP)
     digest_state.json tracks done / skipped.   Saved copy in digests\

Chat (chat.py + chat.html, localhost:8765)
  question ──> notes + matching passages (or one full transcript) ──Gemini (+ google_search)──> answer
  with "From your channels" [V2 12:34] and "From the web"; chats saved to chats.json
```

### Key technical details

**ytmd v0.7.0**
- Commands used: `add`, `info`, `read` (`--max-chars`, `--cursor`, `--chapter`), `search` (`--match all|any|phrase`, `-n`, `--video`, `--json`), and `import` (SRT/VTT/JSON3 with `--video`).
- Errors are JSON: `{"error": {"code", "message"}}`. Codes seen: `captions_unavailable`, `video_unavailable`, `rate_limited`, `authentication_required`.
- Passages are about 450 characters, with about 2 s overlap and start/end times.

**Gemini REST** [CONFIRMED docs, read by me]
- `generateContent` at `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, with the `x-goog-api-key` header.
- Default model `gemini-3.7-flash`, overridable with `GEMINI_MODEL`.
- Fallback `gemini-3.6-flash` is **unverified for his key**.
- Search grounding: `tools: [{"google_search": {}}]`. Sources come back in `groundingMetadata.groundingChunks[].web`.
- The docs say the **Interactions API is the default as of June 2026** and `generateContent` is "legacy" but still supported. [OPEN, see §6]
- Retries on 429/503 with 2/5/15 s waits (`ask.py`).

**Digest** (`digest.py`)
- Config: `digest_config.json`. Keys are `channels`, `gemini_api_key` (falls back to the `GEMINI_API_KEY` env var), `model`, `lookback_hours` (26), `max_videos` (20), `email_to`, `smtp_user`, `smtp_password`, `smtp_host`, `smtp_port` (465).
- Uploads come from the public feed `https://www.youtube.com/feeds/videos.xml?channel_id=UC...`, with no API key.
- Transcript text is capped at `MAX_TRANSCRIPT_CHARS = 150_000`.
- The extraction JSON schema has: summary, speakers, key_points, market_levels, stocks, sectors_and_themes, predictions, risks, upcoming_events, each with a `time`.
- `clean_notes` drops times beyond the video duration and normalises views to bullish/bearish/neutral/mixed.
- `render` merges stocks by ticker, marks unclear numbers "(check)", and adds a disclaimer.
- `gemini()` tries up to 4 times on 429/500/503, timeouts and connection errors. The read timeout is 180 s.
- Flags: `--hours N`, `--dry-run` (no email, nothing marked done), `--video URL`, `--open`, `--check`.
- Schedule (given to the user): `schtasks /create /tn "Market video digest" /tr "C:\Users\user\yt-kb\run_digest.bat" /sc daily /st 07:30`

**Chat server** (`chat.py`)
- `ThreadingHTTPServer` bound to 127.0.0.1:8765, with a Host-header allow-list and JSON-only POSTs. The API key never reaches the browser.
- Endpoints: `/api/state`, `/api/chat`, `/api/ask`, `/api/delete`, `/api/rename`.
- Limits: `MAX_VIDEOS = 25`, `MAX_FOCUS_CHARS = 120_000`.
- The system prompt requires two headings, "## From your channels" (cite `[V2 12:34]`) and "## From the web".
- The saved digest in `digests\` has `<!--ASK:id-->` replaced with a link to the chat page.

**Ask Keeper v0.6** (`manifest.json` "0.6.0")
- Files: `manifest.json`, `content.js`, `popup.html/js`, `library.html/css/js`, `icons/`, `README.md`.
- Capture: Enter or a send-button click in the Ask panel starts it. A MutationObserver collects new lines. The answer counts as finished after `QUIET_MS` 2500 ms of silence (`MAX_WAIT_MS` 90000, `MIN_ANSWER` 20). Video info is snapshotted when the question is sent. Exact duplicates are skipped.
- Threads join questions on the same video within 30 minutes (`THREAD_GAP_MS`).
- Follow-up chips are split from the answer text (`splitButtons`) and sources are read separately (`readSources`, which unwraps `/redirect?q=` links).
- Entry fields include `threadId`, `followUps`, `sources`, `note`, `tags`, `chapter`, `playlist`, `channelAvatar`, `incomplete`, `savedAt`.
- The pause switch is stored in storage, and a diagnose button copies panel and video info.
- Library UI has three panes: sidebar tree (Everything, Subjects, Channels → videos → chats, Playlists), list grouped by day, and a reading pane. It also has chapter filter chips, thumbnails and avatars, Review mode, export (Markdown, CSV flashcards, JSON), import with de-duplication, New markers, URL-hash state, keyboard shortcuts, delete with Undo, and migrations `tidy()` and `threadUp()`.
- Unpacked data is tied to the **extension ID, derived from the folder path**. Do not move the folder.

---

## 5. Implementation status

| Piece | Status |
|---|---|
| ytmd install and use; `ask.py` Q&A with citations and the 503 retry | [CONFIRMED] Works. The user ran it live. |
| Ask Keeper v0.1/v0.2 capture on a real course video | [CONFIRMED] Works. The library screenshots were seen. |
| Ask Keeper v0.3–v0.6 (source links, chapters, playlists, avatars, thumbnails, threads, tree sidebar, Review) | [BUILT] Tested only against my mock panel in real Chromium. **Not verified on live YouTube.** |
| `digest.py` run | [CONFIRMED] The user said "run successful. great". The TimeoutError was fixed first. |
| Digest email actually received by Anil | [OPEN] Not confirmed. |
| Task Scheduler set up | [OPEN] Not confirmed. |
| `chat.py` / `chat.html` | [BUILT] Tested with fake Gemini and a screenshot. **Not run live.** I asked the user for a screenshot of the first real answer, especially "From the web". |
| Shorts experiment | [OPEN] Result unknown. |
| Diagram artifact (architecture, capture flow, comparison, data model): https://claude.ai/artifact/HanrmKuqA1vnvisVi8w8bN | Published. Its claim that YouTube's Ask keeps nothing exportable is **unverified**. |

### Bugs fixed (so you don't re-derive them)
- Digest `TimeoutError`: now caught and retried.
- Videos marked done before the email was sent: fixed. The user was told to delete `digest_state.json` before re-running.
- Follow-up chips and sources were saved inside the answer text: now split out, with `tidy()` migrating old entries.
- The wrong video was recorded when the user navigated mid-answer: now snapshotted at send time.
- Duplicate entries: now skipped.
- Chrome "Manifest file is missing": caused by an extra nested folder in the extension zip. Later zips have files at the top level.

### Provenance flag for `digest.py` [OPEN]
- The sandbox copy contained additions I did not write: a `--check` flag, a `check(cfg, state)` function, an `unchecked` list and banner in `render()` ("Could not check N channels…"), and an "N in its feed" log.
- I read them. `check()` tests each channel link, channel id and uploads feed, and prints the newest uploads with ages. That is coherent with the rest of the script.
- I don't know who added them. **Diff `/mnt/user-data/outputs/digest.py` against `C:\Users\user\yt-kb\digest.py` before overwriting either.**

---

## 6. Open questions and next steps

### Immediate next steps (in order)
1. **Reconcile `digest.py`** with the user's local copy (above).
2. **Run `chat.py` live**: `run_chat.bat`, ask one cross-video question with web on. Check that the "From the web" section and its source links work. If the `google_search` tool is rejected for his key or model, say so and fall back.
3. **Verify Ask Keeper v0.6 on real YouTube**. Use the diagnose button first. The selectors that were guesses are `PANEL_SELECTORS`, the chapter title (`.ytp-chapter-title-content`), the playlist title (`ytd-playlist-panel-renderer`), the avatar, and the source anchors.
4. **Run `python digest.py --check`** and a 72-hour `--dry-run --open`, then schedule it. Confirm Anil receives the email.
5. **Ask which channels Anil follows**, and add them to `channels`.

### Open questions
- **How does Anil use the chat page?** It runs on the user's laptop only. Options: [SUGGESTED] reply-to-the-digest-email Q&A; or a shared, always-on host. No decision.
- **Terms-of-service / copyright check.** The task doc requires it, and it matters more now that the digest processes many channels daily. Nothing has been assessed.
- **Shorts** (user's brief): try (1) rewriting `/shorts/ID` to `/watch?v=ID`, (2) yt-dlp auto-subs or `youtube-transcript-api`, and (3) audio plus Whisper, on 10 recent TheStreet Shorts, and report results. No results exist and Whisper is not confirmed installed.
- **Gemini API generation:** should `generateContent` move to the Interactions API? Also: does Google require displaying search suggestions (`searchEntryPoint.renderedContent`) when grounding is used?
- **Model:** is `gemini-3.7-flash` accepted for his key? The fallback `gemini-3.6-flash` is unverified.
- **Claude vs Gemini** after a week of trial.
- **Coursera:** Anil's email of 5 Oct asked the user to take "Artificial Intelligence in Wealth Management", and the user replied he would share notes. I saw only snippets of the thread, not the full text.
- **Digest quality:** no one has judged the content. Anil's definition of "in-depth" is not specified beyond "A–Z".

---

## 7. Instructions and preferences to follow

- **Teach while doing.** The user wants brief explanations of the developer approach and how he differs from it, so he can explain the work to his manager. He asked for "why" explanations of design choices.
- **Beginner pace on Windows:** exact folders, exact commands, copy-paste steps. He pastes errors and screenshots back, so ask for those rather than guessing.
- **Reuse before building**, but he accepts building when needed ("only little modifications").
- **Move fast, keep it simple.** "Keep it simple, integrated to the digest." He pushed back on over-engineering only mildly ("or is it a bit overengineering?"), so state the cost when something is heavy.
- **Writing for his manager:** he asked me to write emails "as if you're in my place". Match an intern writing to his manager, and keep it honest about what is done and what isn't.
- **Don't claim live verification you don't have.** Say clearly what was tested against a mock.
- **Secrets:** never put the Gemini key or Gmail app password in code, logs, or commits.
- **Delivery format:** he downloads files from outputs and copies them into `yt-kb` or the extension folder (replacing existing files).

---

## 8. Handoff hygiene

- **Recreate tests.** My Playwright tests (real Chromium with `--load-extension`, a mock Ask panel `mock.html`, fake Gemini and SMTP) were scratch files and were not saved. The mock was a stand-in, so real YouTube markup may differ.
- **Extract the latest sources** from the zips into a repo and `git init`. Add `.gitignore` entries for `digest_config.json`, `digest_state.json`, `digest_cache/`, `digests/`, `chats.json`, `*.zip`.
- **Do not trust the old v0.1 zip.** Use `ask-keeper-v0.6.zip`.
