# Market Video Digest

Every morning, a digest of what the finance YouTube channels you follow said, so you don't have to watch them. It
comes with **Market Digest**, an app on your computer with a **dashboard** of the analysts' calls and how they turned
out, **weekly and monthly** summaries, your settings, and a chat about the videos.

Every morning it:

1. checks your channels for new videos (only those with the analysts you follow, if you choose),
2. reads each video's captions,
3. has Google Gemini pull out what matters: the main points, stocks and each analyst's view on them, market
   levels quoted, predictions, risks and upcoming events,
4. shows you one digest (on screen, in your browser, and by email if you like), where every point links to the
   exact moment in the video where it was said.

It runs on your own Windows PC or Mac and keeps your data there. The only key you need is a free Gemini key.

What you get in Market Digest:

- **Dashboard**: what matters now, the stocks the analysts talked about and which way they lean, how their calls did
  against the S&P 500, each analyst's record, your holdings by weight, the mood day by day, what is coming up.
- **Weekly and monthly digests**: the period's story, the most-discussed stocks, the best and worst calls.
- **Your stocks**: type your watchlist (and shares, if you like); prices are fetched by your computer.
- **Email with just your address**: confirm it with a code; no Gmail password needed.
- **Claude**: one click lets the Claude desktop app answer questions from your own digest.
- **Extras** for advanced use: a Google Drive folder of daily JSON files (the Econova hub), a Google Finance prices
  sheet, and Wall Street's view from TipRanks.

## Quick start (Windows or Mac)

You need a **Gemini API key** (free, from https://aistudio.google.com/apikey) and, to receive emails, a **Gmail app
password** (https://myaccount.google.com/apppasswords). The settings page links to both. On a Mac you also need
**Python 3.9 or newer** (https://www.python.org/downloads/macos/; the installer tells you if it is missing).

1. Get the files: unzip `market-digest-setup.zip`, or on GitHub click **Code > Download ZIP** (or `git clone` it).
2. Double-click the installer in that folder: **`install.bat`** on Windows, **`install-mac.command`** on a Mac.
   - Windows says "Windows protected your PC"? Click **More info > Run anyway**.
   - macOS says it cannot check the file? Right-click it > **Open** > **Open**.
3. **The setup page opens in your browser: three short steps.** Paste your Gemini key, click the channels and analysts
   you want, pick a time. Then **Save and finish** and **Make my first digest now**.

That's it. Each morning's digest opens in your browser with a notice on screen (email is optional), and
**Market Digest** is on your desktop: it shows whether the last digest worked, holds the settings, has the chat, and
updates itself in one click when a new version is out.

## Everyday use

| I want to... | Do this |
|---|---|
| Read today's digest | It opens by itself when ready (or **Market Digest** > Home > Recent digests, or the email). |
| See how the analysts' calls are doing | **Market Digest** > **Dashboard** (7, 30 or 90 days). |
| Weekly and monthly summaries | Arrive by themselves on Saturdays and on the 1st (Settings > How you get the digest). |
| Add my stocks | **Settings > Your stocks**: tickers, and shares if you want your holdings on the dashboard. |
| Know whether it ran, and why not | **Market Digest** (desktop). The home page shows the last run, in plain words. |
| Change channels, email, keys or time | **Market Digest** > Settings. Each setting has a Test button. |
| Ask about the videos | **Market Digest** > Chat. Or connect the Claude desktop app (Settings > Ask Claude) and ask Claude. |
| Get a digest right now | **Market Digest** > Make today's digest now |
| Check everything works | The **Test** buttons in Settings (or `python digest.py --check` in the program folder) |
| Feed the Econova hub | Each run also saves `video-digest_YYYY-MM-DD.json` in `json_dir` (set it to a Google Drive for desktop folder to share it). See [ARCHITECTURE.md](docs/ARCHITECTURE.md) §3. |
| See prices for my stocks next to the analysts' calls | Set up the watchlist sheet: USER_GUIDE.md, section 5a. |
| Add past days to the JSON folder | `python email_backfill.py digests\digest-*.html` (USER_GUIDE.md, 5a) |
| See the dashboard | Open it in Claude (the link is in the Drive folder's START HERE doc). Every number has an (i) that explains it. |
| Add Wall Street's view | Get a key at https://mcp.tipranks.com/ (Keys) and paste it in Settings > TipRanks |
| Update to the newest version | **Market Digest** > Home > **Update now** (shown when a new version is out; settings are kept) |
| Close it | **Quit** at the top right of the page. The daily digest still runs. |

## Documents

- **[USER_GUIDE.md](USER_GUIDE.md)**: installation, settings, daily use, updating and removing it.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**: what to do when something goes wrong.
- **[CHANGELOG.md](CHANGELOG.md)**: what changed in each version.
- **[email_service/README.md](email_service/README.md)**: setting up the email service (once, by the developer).
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
