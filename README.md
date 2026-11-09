# Market Video Digest

A daily email that tells you what the finance YouTube channels you follow said, so you don't have to watch them,
plus **Market Digest**, a page on your computer that shows whether today's digest ran, holds all the settings, and
has a chat for questions about those videos.

Every morning it:

1. checks your channels for new videos,
2. reads each video's captions,
3. has Google Gemini pull out what matters: the main points, stocks and each channel's view on them, market
   levels quoted, predictions, risks and upcoming events,
4. emails you one digest, where every point links to the exact moment in the video where it was said.

It runs on your own Windows PC or Mac, uses only free services, and keeps your keys and data on your computer.

Optional extras, each set up once (USER_GUIDE.md, sections 3 and 5a):

- **Only the analysts you follow**: list the people whose views matter (Dan Ives, Tom Lee, ...) and only videos where
  they speak go into the digest. Other uploads are left out before Gemini reads them, so more channels cost nothing.

- **Prices**: a Google Sheet of Google Finance prices puts your watchlist's moves next to the analysts' calls.
- **The Econova dashboard**: each run saves the day's notes as JSON in a Google Drive folder; a Claude dashboard reads
  them with live prices, scores whether past calls beat the S&P 500, and shows your own holdings.
- **Wall Street's view**: with a TipRanks API key, one look-up a weekday adds the professional consensus, price
  targets and earnings dates, inside TipRanks' free 50 calls a month.

## Quick start (Windows or Mac)

You need a **Gemini API key** (free, from https://aistudio.google.com/apikey) and, to receive emails, a **Gmail app
password** (https://myaccount.google.com/apppasswords). The settings page links to both. On a Mac you also need
**Python 3.9 or newer** (https://www.python.org/downloads/macos/; the installer tells you if it is missing).

1. Get the files: unzip `market-digest-setup.zip`, or on GitHub click **Code > Download ZIP** (or `git clone` it).
2. Double-click the installer in that folder: **`install.bat`** on Windows, **`install-mac.command`** on a Mac.
   - Windows says "Windows protected your PC"? Click **More info > Run anyway**.
   - macOS says it cannot check the file? Right-click it > **Open** > **Open**.
3. **The settings page opens in your browser.** Paste your key, add your channels and (optionally) your email, test
   each with its **Test** button, click **Save**, then **Make a test digest**, then **Finish**.

That's it. The digest arrives by email every day at the time you chose, and **Market Digest** is on your desktop:
it shows whether the last digest worked, lets you change any setting, and has the chat.

## Everyday use

| I want to... | Do this |
|---|---|
| Read today's digest | Open the email, or **Market Digest** > Recent digests. |
| Know whether it ran, and why not | **Market Digest** (desktop). The home page shows the last run, in plain words. |
| Change channels, email, keys or time | **Market Digest** > Settings. Each setting has a Test button. |
| Ask about the videos | **Market Digest** > Chat. Keep its small window open while you use it. |
| Get a digest right now | **Market Digest** > Make today's digest now |
| Check everything works | The **Test** buttons in Settings (or `python digest.py --check` in the program folder) |
| Feed the Econova hub | Each run also saves `video-digest_YYYY-MM-DD.json` in `json_dir` (set it to a Google Drive for desktop folder to share it). See [ARCHITECTURE.md](docs/ARCHITECTURE.md) §3. |
| See prices for my stocks next to the analysts' calls | Set up the watchlist sheet: USER_GUIDE.md, section 5a. |
| Add past days to the JSON folder | `python email_backfill.py digests\digest-*.html` (USER_GUIDE.md, 5a) |
| See the dashboard | Open it in Claude (the link is in the Drive folder's START HERE doc). Every number has an (i) that explains it. |
| Add Wall Street's view | Get a key at https://mcp.tipranks.com/ (Keys) and paste it in Settings > TipRanks |
| Update to the newest version | `git pull` (or a new zip), then double-click the installer again and click **Finish** (settings are kept) |

## Documents

- **[USER_GUIDE.md](USER_GUIDE.md)**: installation, settings, daily use, updating and removing it.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**: what to do when something goes wrong.
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)**: how it works inside, for developers. *(In `docs/`, not in the setup zip.)*
- **[PRESENTATION.md](docs/PRESENTATION.md)**: a 6-slide overview of the project. *(In `docs/`, not in the setup zip.)*

## Good to know

- Captions are automatic and can mishear names and numbers. Unclear figures are marked "(check)", and every point
  links to its moment in the video so you can check it.
- The digest reports what each channel said. **It is not investment advice.**
- The PC must be on for the digest to run. If it was off at the scheduled time, it runs when the PC is next on and
  includes everything since the last digest.
- Web search in the chat needs a Gemini key with billing turned on. On the free key, the chat answers from your
  videos only and says so.
