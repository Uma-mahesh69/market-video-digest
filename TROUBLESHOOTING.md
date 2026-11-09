# Troubleshooting

Every problem below actually happened while building and running this project. Each has its cause and a fix that
was tested. **Verified** means the fix was run on a real PC and the problem went away.

**First step for any problem:** open PowerShell and run

```
cd $env:USERPROFILE\market-digest
python digest.py --check
```

It tests each channel, the Gemini key and the Gmail login, and prints `FAILED` next to anything broken. For
scheduled runs, also read `digest.log` in the same folder (open it with Notepad).

---

## Installing

### "Windows protected your PC" when opening install.bat
- **Cause:** Windows warns about any script downloaded from the internet.
- **Fix:** click **More info**, then **Run anyway**.

### "...is missing next to install.bat. Unzip the whole folder first"
- **Cause:** install.bat was opened from inside the zip without extracting, or files were moved out of the folder.
- **Fix:** right-click the zip > **Extract All**, then run install.bat from the extracted folder.

### "Python is not installed" or "Python did not install"
- **Cause:** the PC has no Python and no `winget` to install it automatically.
- **Fix:** install Python from https://www.python.org/downloads/windows/ (tick **Add python.exe to PATH**), then run
  install.bat again.

### The Gemini key was saved wrongly: later `Gemini error 400: Bad Request` (Verified)
- **Cause:** older versions asked for the key in a hidden terminal prompt, where **Ctrl+V does not paste**; it saved an
  invisible control character instead of the key. On our test PC the saved "key" was 1 character long.
- **Fix:** open **Market Digest > Settings**, paste the key into the Gemini box (Ctrl+V works there; **Show** reveals
  it), click **Test the key**, then **Save**. The settings page replaced the terminal questions.

### The settings page did not open during installation
- **Cause:** the browser did not start by itself.
- **Fix:** copy the address the installer window shows (`http://127.0.0.1:8765/settings?setup=1`, or another port)
  into your browser. The installer waits until you click **Finish** on the page; if you closed the page, press
  Ctrl+C in the installer window and run it again.

### "Market Digest stopped responding" or the page does not load
- **Cause:** the small Market Digest window was closed, which stops the page.
- **Fix:** double-click **Market Digest** on the desktop again. Keep its window open (you can minimise it).

### The home page says "this computer has no schedule for it"
- **Cause:** the daily task (Windows) or launchd job (Mac) was removed, or the program folder moved.
- **Fix:** open **Settings** and click **Save**. Saving sets the schedule again.

### The zip could not be sent by email
- **Cause:** Gmail blocks attachments that contain `.bat` files, even inside a zip.
- **Fix:** share the zip through Google Drive (Share > add the person > Viewer).

---

### Mac: "install-mac.command cannot be opened" (unidentified developer, or Apple cannot check it)

macOS shows this for files downloaded from the internet. **Right-click** the file, choose **Open**, then **Open**
again; macOS remembers this. If Finder says you do not have permission to open it (a zip made on Windows does not
keep the "can be run" flag), start it from Terminal instead: type `bash ` (with a space), drag the file into the
Terminal window, press Return. A folder made with `git clone` does not have either problem.

### Mac: "Python cannot check web certificates" or `CERTIFICATE_VERIFY_FAILED`

Python from python.org needs its certificates installed once. The installer tries this itself. If it still fails:
open **Applications > Python 3.x**, double-click **Install Certificates.command**, then run the installer again.

### Mac: the JSON file is not appearing in Google Drive

Run `cd ~/market-digest && python3 digest.py --check` and look at the `JSON folder:` line. Google Drive for desktop
must be running and signed in, and its folder is under `~/Library/CloudStorage/GoogleDrive-<your email>/My Drive`.
If macOS asked whether Terminal may access Google Drive, it needs **Allow** (System Settings > Privacy & Security >
Files and Folders). Not yet tested on a real Mac: whether the scheduled (launchd) run is allowed to write there
without asking. Check `digest.log` after the first scheduled run.

## No digest email

### TipRanks: "refused the API key", "skipped", or an empty Wall Street table
- **"refused the API key (HTTP 401)"**: the key is mistyped or was revoked. A key is 40 characters and starts with
  `tr_live_`; add it again with a right-click paste, or make a new one at https://mcp.tipranks.com/ (Keys).
- **"TipRanks: skipped (...)"** in the log is normal: weekends, a look-up already made today, or the month's calls
  nearly used (3 are always kept spare). The quota resets on the 1st (UTC). `--tipranks-check` shows TipRanks' count.
- **Empty "Wall Street's view" on the dashboard**: no `tipranks_*.json` in the json folder yet. Check that
  `tipranks_api_key` is set and that the log has a "Saved ...tipranks_" line after a weekday run.

### The dashboard says "Live data isn't available in this view" or "Failed to load"
- **"Live data isn't available in this view"**: the dashboard was opened from another Claude account. Claude runs
  connectors only for the account that owns the dashboard, so open it from that account, or have the other person
  Duplicate it into their own account and point it at Drive files they can read.
- **"Failed to load"**: that account's Google Drive connector cannot read the json folder or one of the sheets
  (Market Digest Watchlist, Market Digest Prices, Investment Tracker). Open the Sources panel to see which, and check
  that the connector is signed in with the Google account that owns them.
- A file or sheet moved to another folder keeps working: the dashboard finds them by their Drive ids. Renaming or
  moving the json folder itself breaks the PC's daily writes, not the dashboard.

### A backfilled day has `video_count: 0` though its email had videos (Verified, fixed 4 Nov 2026)
- **Cause:** `email_backfill.py` was given only `market-digest\digests`, but that day's digests were made by runs
  started in the project folder, so they were saved in its own `digests` folder. The backfill found only an empty
  run's page and wrote an empty day (Oct 22 and Oct 26).
- **Fix:** delete the empty file from the json folder, then run the backfill again with both folders' patterns.
  Oct 22 and Oct 26 were rebuilt from their digest emails.

### A failed run was not tried again on Windows (Verified, fixed 3 Nov 2026)
- **Cause:** the log said "tries again in 30 minutes", but Task Scheduler's "restart on failure" ignores the
  program's exit code, so nothing ran until the next day. On 31 Oct, Gmail refused the email (451) after that day's
  JSON was saved; the queued videos then went into the 1 Nov file as well.
- **Fix:** `run_digest.bat` now retries itself every 30 minutes, 3 times, and the JSON is saved only after the email
  goes out. Run `install.bat -Unattended` once to get the new launcher (settings are kept).

### Nothing arrived, and `digest.log` says `getaddrinfo failed` (Verified)
- **Cause:** the PC had just been switched on. Windows started the catch-up run before Wi-Fi was connected, so the
  run could reach neither YouTube nor Gmail.
- **Fix (built in now):** the digest waits up to 15 minutes for the internet before starting. If a run still fails,
  Windows retries it every 30 minutes, 3 times. Nothing is lost: videos stay queued until an email goes out.
- **To get the digest now:** Task Scheduler > Market video digest > right-click > **Run**, or
  `python digest.py --open`.

### `digest.log` says `Nothing new today, so no email was sent`
- **Cause:** the channels had no new videos since the last digest. This is normal.
- **Fix:** nothing. To see a digest anyway: `python digest.py --hours 72 --dry-run --open`.

### No line for today in `digest.log` at all
- **Cause:** the PC was not on at any point after the scheduled time, or the task is missing.
- **Fix:** check the task exists in Task Scheduler > Task Scheduler Library > **Market video digest**. If it is
  missing, open Market Digest > Settings and click Save. The next run covers everything since the last digest (up to 7 days), so days the
  PC was off are not lost.

### `Email: FAILED to log in`
- **Cause:** the normal Gmail password was used, or the app password was mistyped or revoked.
- **Fix:** create a new app password at https://myaccount.google.com/apppasswords, paste it in Market Digest >
  Settings > Email, click **Send a test email**, then **Save**.

### The email was sent (`Emailed to ...` in the log) but you can't find it
- **Cause:** when you send to your own Gmail address, Gmail may not put it in the Inbox.
- **Fix:** look in **All Mail** and **Spam**. Search for "Market video digest".

---

## Channels

### `FAILED to find the channel id` for a `music.youtube.com` link (Verified)
- **Cause:** the digest only knew how to read normal `www.youtube.com` channel pages.
- **Fix (built in now):** `music.youtube.com` and `m.youtube.com` links are converted automatically. If you still see
  this, open the channel in a browser, copy its `www.youtube.com/@name` link, and use that.

### A video appears under "Not included: captions too short to summarise", and its title contains ’ or “ (Verified)
- **Cause:** Windows returned the caption reader's output in a different text encoding, and titles with curly quotes
  broke the reading. The captions then looked empty, and the video was wrongly marked as never readable.
- **Fix (built in now):** the caption reader is forced to use UTF-8. Videos like "Here’s How" are now included.

### A video is under "Not included: captions unavailable"
- **Cause:** the video has no captions. Common for Shorts.
- **Fix:** none needed. Such videos are listed once and not retried.

### `FAILED to list its uploads` (was `FAILED to read the uploads feed`)
- **Cause:** from 3 Nov 2026 YouTube's public uploads feed answered 404 (also in a browser). The digest now falls
  back to yt-dlp, which reads the channel's Videos tab; the log says "listing the channel's videos with yt-dlp
  instead". This error appears only when both fail.
- **Fix:** open the link printed under the error in a browser. If it shows the videos, update yt-dlp
  (`yt-dlp -U`) and try again. If it shows an error, check the channel link.

---

## Gemini (the AI model)

### The digest is very slow, minutes per video (Verified)
- **Cause:** the main model (`gemini-3.7-flash`) was overloaded (`error 503`), and the old version retried it with
  long waits before giving up.
- **Fix (built in now):** a busy model is skipped for 10 minutes and the next model in `models` is used at once. On
  our PC, a 2-video run went from over 20 minutes to under a minute, and 4 videos took about 1.5 minutes.

### Log lines like `gemini-3.7-flash: error 503, switching to the next model`
- **Cause:** that model is overloaded at Google.
- **Fix:** none needed. This is the fallback working.

### `error 429` / "You exceeded your current quota"
- **Cause:** free-tier daily limits. On our key (checked 15 Oct 2026 at https://ai.dev/rate-limit): Flash models allow
  **20 requests a day each**, the Flash Lite models **500 a day**. Every video and every chat question uses one.
- **Fix:** the model list moves on to the next model automatically. Limits reset daily. To remove them, turn on billing
  for the Gemini project.

### `Gemini key: FAILED: Gemini error 400`
- **Cause:** the key is wrong or was pasted wrongly (see "Installing" above).
- **Fix:** get the key again from https://aistudio.google.com/apikey and re-enter it with install.bat (right-click to paste).

### `error 404 ... no longer available to new users`
- **Cause:** Google retired that model for new keys (seen with `gemini-2.5-flash`).
- **Fix:** remove it from `models` in `digest_config.json`.

---

## Chat page

### The chat says "Web search was not available for this question" (Verified)
- **Cause:** web search (Google Search grounding) has **no free quota** on our key. It was rejected with 429 on every
  model, including Flash Lite.
- **Fix:** the chat still answers from your videos and says so. To get web results, turn on billing for the Gemini
  project.

### "Market Digest is already running" / changes don't seem to take effect (Verified)
- **Cause:** an older Market Digest (or Digest chat) window is still open and holding the page (port 8765), still
  running the old code. After an update, the Settings tab may be missing for the same reason.
- **Fix:** close every Market Digest or Digest chat window (or press Ctrl+C in it), then double-click
  **Market Digest** again.

### The video list in the chat is empty, or a new video is missing
- **Cause:** the chat only knows videos the digest has already summarised.
- **Fix:** make a digest first (Market Digest > **Make today's digest now**), then refresh the chat page.

### A citation shows as plain text like `[V1 3:33, 10:13]` (Verified, fixed)
- **Cause:** older versions only linked citations where every time had its own `V1`.
- **Fix (built in now):** a bare time uses the video number before it. Update to the latest version.

---

## Still stuck?

Send a screenshot of the error, plus the last 20 lines of `digest.log` and the output of `python digest.py --check`.
**Never send `digest_config.json`**: it contains your key and password.
