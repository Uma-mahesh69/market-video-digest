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
- **Cause:** the key prompt hides what you type. In that prompt, **Ctrl+V does not paste**; it saves an invisible
  control character instead of the key. On our test PC the saved "key" was 1 character long.
- **Fix:** run install.bat again, answer `y` to "Enter them again?", and **paste with a right-click**. The installer
  now rejects a Ctrl+V paste or a too-short key and asks again.

### The zip could not be sent by email
- **Cause:** Gmail blocks attachments that contain `.bat` files, even inside a zip.
- **Fix:** share the zip through Google Drive (Share > add the person > Viewer).

---

### Mac: "install-mac.command cannot be opened because it is from an unidentified developer"

macOS shows this when the file is double-clicked. Start it from Terminal instead: type `bash ` (with a space),
drag the file into the Terminal window, press Return. The same works if Finder says you do not have permission to
open it (a zip made on Windows does not keep the "can be run" flag).

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
  missing, run install.bat again. The next run covers everything since the last digest (up to 7 days), so days the
  PC was off are not lost.

### `Email: FAILED to log in`
- **Cause:** the normal Gmail password was used, or the app password was mistyped or revoked.
- **Fix:** create a new app password (Google Account > Security > 2-Step Verification > App passwords) and run
  install.bat again to enter it.

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

### `FAILED to read the uploads feed`
- **Cause:** YouTube's public feed was unreachable for a moment, or the channel id is wrong.
- **Fix:** open the link printed under the error in a browser. If it shows a list of videos, try again later. If it
  shows an error, check the channel link.

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

### "The chat page is already running" / changes don't seem to take effect (Verified)
- **Cause:** an older chat window is still open and holding the page (port 8765), still running the old code.
- **Fix:** close every black chat window (or press Ctrl+C in it), then double-click **Digest chat** again.

### "The chat page stopped responding. Is the black chat window still open?"
- **Cause:** the black window was closed.
- **Fix:** double-click **Digest chat** again.

### The video list in the chat is empty, or a new video is missing
- **Cause:** the chat only knows videos the digest has already summarised.
- **Fix:** run a digest first (`python digest.py --open`), then refresh the chat page.

### A citation shows as plain text like `[V1 3:33, 10:13]` (Verified, fixed)
- **Cause:** older versions only linked citations where every time had its own `V1`.
- **Fix (built in now):** a bare time uses the video number before it. Update to the latest version.

---

## Still stuck?

Send a screenshot of the error, plus the last 20 lines of `digest.log` and the output of `python digest.py --check`.
**Never send `digest_config.json`**: it contains your key and password.
