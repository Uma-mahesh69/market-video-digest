# User Guide: Market Video Digest

This guide is for the person using the digest. No programming knowledge is needed. Commands you need to type are
shown in grey boxes. Copy them exactly.

**Contents**
1. What you get
2. Before you install
3. Installing
4. Your settings
5. Everyday use: the email
6. Everyday use: the chat page
7. Useful commands
8. Changing, updating and removing it
9. If something goes wrong

---

## 1. What you get

- **A daily email digest** of new videos from the YouTube channels you follow. It contains:
  - **Overview**: what today's videos say about the markets, in a few sentences.
  - **Themes today** and **Where channels disagree** (when more than one video is new).
  - **Stocks mentioned**: each stock, whether each channel is bullish, bearish, neutral or mixed, and why.
  - **Market levels and data quoted**: indexes, yields, rates and so on, as stated in the videos.
  - **Coming up**: earnings, data releases and meetings the videos mention.
  - **Video by video**: a summary, key points, sectors, predictions and risks for each video.
  - **Not included**: videos that could not be read (usually Shorts with no captions).
  - Every point has a time like **[12:34]** that opens the video at that moment.
- **A chat page** on your PC for questions such as "Which stocks came up most this week?" or "What did they say
  about Treasury yields?". Answers cite the video and moment, like **TheStreet 12:34**.

## 2. Before you install

You need three things.

| What | Where to get it | Notes |
|---|---|---|
| A Windows 10 or 11 PC | | It must be on (or turned on later that day) for the digest to run. |
| A **Gemini API key** | https://aistudio.google.com/apikey, sign in with Google, click **Create API key** | Free. Starts with `AIza`. Keep it private. |
| A **Gmail app password** (only if you want emails) | Google Account > **Security** > **2-Step Verification** > **App passwords** | 16 letters. Your normal Gmail password will **not** work. 2-Step Verification must be on. |

The installer gets Python and the caption reader (yt-dlp) for you if they are missing.

## 3. Installing

1. Save `market-digest-setup.zip` somewhere, for example your Downloads folder.
2. Right-click it and choose **Extract All**, then **Extract**.
3. In the extracted folder, double-click **`install.bat`**.
   - If you see **"Windows protected your PC"**, click **More info**, then **Run anyway**. Windows shows this for
     any script downloaded from the internet.
4. A blue window walks you through these steps:

| Step | What happens | What you do |
|---|---|---|
| 1. Python | Finds Python, or installs Python 3.13 for you. | Wait. This can take a few minutes the first time. |
| 2. Program files | Copies the program to `C:\Users\<you>\market-digest`. | Nothing. |
| 3. yt-dlp | Downloads the official caption reader if it is missing. | Nothing. |
| 4. Settings | Asks your questions (see below). | Answer them. |
| 5. Testing | Tests your channels, your Gemini key and your Gmail login. | Read the results. Everything should say it works. |
| 6. Daily schedule | Creates the Windows task "Market video digest". | Nothing. |
| 7. Shortcut | Adds **Digest chat** to your desktop. | Nothing. |
| Test digest | Offers to make a digest of the last 3 days. | Type `y`. It opens in your browser and is not emailed. |

**The questions in step 4:**

- **Gemini API key**: paste it with a **right-click**. You will not see it as you paste; that is normal.
  Ctrl+V does not work in this prompt. If you press it anyway, the installer notices and asks again.
- **YouTube channels**: paste channel links separated by commas, for example
  `https://www.youtube.com/@TheStreet, https://www.youtube.com/@CNBCtelevision`. `@handles`, `/channel/UC...`
  links and `music.youtube.com` links all work. Press Enter to keep the suggested TheStreet.
- **Email address that should receive the digest**: one address, or several separated by commas. Leave empty if
  you only want the digest saved as a file.
- **Gmail address that sends it**: the Gmail account that owns the app password. It can be the same as the
  receiving address.
- **Gmail app password**: paste with a right-click.
- **Time**: when to make the digest each day, in 24-hour form, for example `07:30`.

If step 5 says **FAILED**, the installer stops before scheduling anything. Read the message, then run
`install.bat` again and re-enter the setting that failed. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) explains each
message.

## 4. Your settings

The installer saves your answers in `C:\Users\<you>\market-digest\digest_config.json`. **This file contains your
key and password. Never send it to anyone.** The easiest way to change settings is to run `install.bat` again.
If you prefer to edit the file in Notepad, these are the settings:

| Setting | Meaning | Default |
|---|---|---|
| `channels` | The YouTube channels to follow (links or @handles). | TheStreet |
| `gemini_api_key` | Your Gemini key. | |
| `models` | Gemini models to try, in order. If one is busy or out of free quota, the next is used. | 3.7 Flash, 3.6 Flash, 3 Flash, 3.5 Flash Lite, 3.1 Flash Lite |
| `lookback_hours` | How far back the very first run looks, or a run with `--hours`. Later runs cover everything since the last digest (up to 7 days). | 26 |
| `max_videos` | The most videos in one digest (newest first). | 20 |
| `email_to` | Who receives the digest. | |
| `smtp_user`, `smtp_password` | The Gmail account that sends it, and its app password. | |
| `smtp_host`, `smtp_port` | The mail server. Leave as is for Gmail. | smtp.gmail.com, 465 |

After editing, run `python digest.py --check` (see section 7) to test your changes.

## 5. Everyday use: the email

- The digest arrives every day at your chosen time. The subject looks like
  *"Market video digest, 19 Oct 2026: 4 new videos"*.
- **If your PC was off at that time**, the digest runs as soon as the PC is on. It waits up to 15 minutes for
  the internet to connect and covers every video since the last digest, so no days are lost.
- **No email on a day?** Usually there were no new videos (nothing is sent when there is nothing new), or the PC
  was off all day. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- If you send it to your own address, Gmail may file it under **All Mail** instead of the Inbox.
- Every digest is also saved as a web page in `C:\Users\<you>\market-digest\digests\`. The saved copy has an
  extra **"Ask a question about this video"** link under each video, which opens the chat page.

**How to read it safely:** captions are made automatically and can mishear names and numbers. A figure Gemini was
unsure of is marked **(check)**. Click the time next to any point to hear it said in the video. The digest
reports each channel's opinion. It is not investment advice.

## 6. Everyday use: the chat page

1. Double-click **Digest chat** on the desktop. A black window opens, then the chat page opens in your browser at
   `http://127.0.0.1:8765`.
2. **Keep the black window open** while you chat. Closing it stops the chat page.
3. At the top, choose which videos to ask about:
   - **Last 3 / 7 / 30 days**, or **All saved videos**, or
   - **one video** from the second list. The chat then reads that video's full transcript.
4. **Also search the web**: needs a Gemini key with billing turned on. On a free key, leave it ticked or not;
   either way the answer says web search was not available and uses only your videos.
5. Type your question and press **Enter** (Shift+Enter for a new line). Answers take 10 to 40 seconds.

Each answer has two parts: **From your channels**, with citations like **TheStreet 12:34** that open the video at
that moment, and **From the web**. Past chats are listed on the left. Click one to continue it. **Delete chat** asks
you to click twice so nothing is deleted by accident.

The chat page only works on the PC where it is installed. Other computers and phones cannot open it.

Good questions to start with:
- *What did my channels say about the market this week?*
- *Which stocks came up most this week, and was each channel bullish or bearish on them?*
- *Where do the channels disagree?*
- *Explain the points about Treasury yields in plain terms.*

## 7. Useful commands

Open **PowerShell** (Start menu > type PowerShell > Enter), then go to the program folder:

```
cd $env:USERPROFILE\market-digest
```

| Command | What it does |
|---|---|
| `python digest.py --check` | Tests every channel, the Gemini key, the JSON folder and the Gmail login. Sends nothing. |
| `python digest.py --open` | Makes and emails a digest now, then opens it in the browser. |
| `python digest.py --hours 48 --open` | The same, covering the last 48 hours. |
| `python digest.py --hours 72 --dry-run --open` | A test digest of the last 3 days: **not emailed**, and videos are not marked as done. |
| `python digest.py --video https://www.youtube.com/watch?v=... --dry-run --open` | A digest of one video. |
| `python digest.py --rebuild 2026-10-22 --dry-run` | The Econova JSON file for an earlier day's digest, written to `digests\` to look at. Without `--dry-run` it goes to the JSON folder, unless that day already has a file. |

To run the scheduled task exactly as Windows would: open **Task Scheduler**, click **Task Scheduler Library**,
right-click **Market video digest**, choose **Run**. Its log is in `digest.log` in the program folder.

## 8. Changing, updating and removing it

- **Change channels, email, key or time:** run `install.bat` again and answer `y` to "Settings already exist.
  Enter them again?". Answer `n` to keep the settings and only change the time.
- **Update to a new version:** unzip the new `market-digest-setup.zip` and run its `install.bat`. Your settings,
  saved digests and chats are kept. Close any open **Digest chat** window first, then open it again afterwards so
  it uses the new version.
- **Remove it completely:**
  1. In Command Prompt: `schtasks /delete /tn "Market video digest" /f`
  2. Delete the folder `C:\Users\<you>\market-digest`.
  3. Delete the **Digest chat** shortcut from the desktop.
  4. Optional: delete `C:\Users\<you>\ytmd` (the saved transcripts).

## 9. If something goes wrong

Run `python digest.py --check` first. It names the part that failed. Then see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md), which lists each problem we have actually seen, its cause and the fix.

The five most common:

| You see | Fix |
|---|---|
| `Gemini key: FAILED: Gemini error 400` | The key was pasted wrongly (often Ctrl+V). Run `install.bat` again and paste with a right-click. |
| `Email: FAILED to log in` | Use a Gmail **app password**, not your normal password. |
| No email today | Check `digest.log`. `Nothing new today` means there were no new videos. |
| "The chat page is already running" | An old chat window is still open. Use it, or close it and open Digest chat again. |
| The chat says web search was not available | Normal on a free Gemini key. Web search needs billing. |
