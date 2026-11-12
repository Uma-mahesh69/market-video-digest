# User Guide: Market Video Digest

This guide is for the person using the digest. No programming knowledge is needed. Commands you need to type are
shown in grey boxes. Copy them exactly.

**Contents**
1. What you get
2. Before you install
3. Installing
4. Your settings
5. Everyday use: the email
   - 5a. Extras: a prices sheet, the Econova hub and TipRanks
6. Everyday use: Market Digest (overview, digests, chat and settings)
   - 6a. The Overview: your stocks' check-up, and the dashboard
   - 6d. Your stocks and Google Finance
   - 6e. Privacy: where your data is
   - 6b. Weekly and monthly digests
   - 6c. Ask Claude about your digest
7. Useful commands
8. Changing, updating and removing it
9. If something goes wrong

---

## 1. What you get

- **A daily digest** of new videos from the YouTube channels you follow (on screen, in your browser, and by email if
  you like). It contains:
  - **Overview**: what today's videos say about the markets, in a few sentences.
  - **Themes today** and **Where channels disagree** (when more than one video is new).
  - **Stocks mentioned**: each stock, whether each channel is bullish, bearish, neutral or mixed, and why.
  - **Market levels and data quoted**: indexes, yields, rates and so on, as stated in the videos.
  - **Coming up**: earnings, data releases and meetings the videos mention.
  - **Video by video**: a summary, key points, sectors, predictions and risks for each video.
  - **Not included**: videos that could not be read (usually Shorts with no captions).
  - Every point has a time like **[12:34]** that opens the video at that moment.
- **Market Digest** on your desktop: a page in your browser that shows whether today's digest ran, lets you change
  any setting with a Test button beside it, and has a **chat** for questions such as "Which stocks came up most this
  week?". Answers cite the video and moment, like **TheStreet 12:34**.
- **A dashboard** of what the digests add up to: the stocks talked about, how the analysts' calls did against the
  S&P 500, each analyst's record, your holdings, what is coming up (section 6a).
- **Weekly and monthly digests** on Saturdays and on the 1st (section 6b).

## 2. Before you install

| What | Where to get it | Notes |
|---|---|---|
| A Windows 10/11 PC or a Mac | | It must be on (or turned on later that day) for the digest to run. |
| A **Gemini API key** | https://aistudio.google.com/apikey, sign in with Google, click **Create API key** | Free. Starts with `AIza`. Keep it private. |
| A **Gmail app password** (only if you want emails) | https://myaccount.google.com/apppasswords | 16 letters. Your normal Gmail password will **not** work. 2-Step Verification must be on. |

You can get these during setup too: the settings page links to each one. The installer gets Python and the caption
reader (yt-dlp) for you on Windows; on a Mac it tells you if Python is missing.

## 3. Installing

**Get the files** in one of two ways:
- the setup zip: right-click `market-digest-setup.zip` > **Extract All** (Windows), or double-click it (Mac); or
- GitHub: open https://github.com/Uma-mahesh69/market-video-digest, click **Code > Download ZIP** and unzip it, or
  `git clone` it.

**Start the installer** by double-clicking it in the unzipped folder:
- **Windows:** `install.bat`. If you see **"Windows protected your PC"**, click **More info**, then **Run anyway**.
- **Mac:** `install-mac.command`. If macOS says it cannot check the file, **right-click** it, choose **Open**, then
  **Open** again. (This happens once, for files downloaded from the internet.)

A window shows the steps. You only act at step 4:

| Step | What happens |
|---|---|
| 1. Python | Finds Python. If there is none, it installs it (Windows: Python 3.13; Mac: a private copy in the program folder). This can take a few minutes. |
| 2. Program files | Copies the program to `C:\Users\<you>\market-digest` (Windows) or `~/market-digest` (Mac). |
| 3. yt-dlp | Downloads the official caption reader if it is missing. |
| 4. Settings | **The setup page opens in your browser: three short steps, about two minutes** (below). |
| 5. Daily schedule | Sets the daily run at the time you chose. |
| 6. Desktop | Adds **Market Digest** to the desktop. |

**The three setup steps:**

1. **Your free Gemini key.** Click **Get my free key**: Google AI Studio opens in a new tab. Sign in with your Google
   account, click **Create API key**, then **Copy**. Come back and click **Paste my key** (or press Ctrl+V, Cmd+V on a
   Mac, in the box). The key is checked with Google by itself, and the page moves on when it works; if it is wrong,
   the page says so in plain words.
2. **Your stocks.** On **google.com/finance**, open your watchlist or portfolio, press **Ctrl+A** then **Ctrl+C**
   (Cmd+A, Cmd+C on a Mac), and paste it into the box (Ctrl+V), then **Find my stocks**: Market Digest picks out the
   tickers. You can also type tickers (NVDA, AAPL), or **Import from a file**. Add the shares you own to see your
   holdings' value (they stay on this computer). Below it, three **popular channels** are already chosen (CNBC
   Television, Bloomberg Television, Yahoo Finance); click others (TheStreet, Fox Business, Schwab Network) or add any
   channel's address if you like. **Next** checks each channel on YouTube.
3. **Finish.** Everything is already set to sensible defaults; change what you like. Pick the daily time. By default a notice appears on your screen and the digest opens
   in your browser when it is ready, so **no email setup is needed**. To get it by email too, tick **Also email it to
   me**, type your address, click **Email me a code** and type the 6-digit code from that email. That's all: the
   Market Digest email service sends it. (**Send from my own Gmail account instead** is there if you prefer; it needs
   a Gmail app password.) The **weekly** and **monthly** digests are on unless you untick them.

Click **Save and finish**, then **Make my first digest now**: a digest of the last 3 days opens in your browser.
Then click **Finish**. The installer window says **Done**; you can close it.

Everything else (only the analysts you choose, TipRanks, a Google Finance sheet, a shared folder, connecting Claude)
is optional and lives in **Settings** afterwards, each with a **Test** button that answers in plain words.

What is different on a Mac:

- The daily run is a **launchd** job (`~/Library/LaunchAgents/com.nugenix.market-digest.plist`) instead of a Task
  Scheduler task. It runs while you are logged in. If the Mac is asleep at that time, it runs when it wakes; if
  it is shut down, the next run covers everything since the last digest.
- **Market Digest** on the desktop is a small app. It starts in the background (no Terminal window) and opens the
  page. If it ever does not start, double-click `run_app.command` in `~/market-digest` instead.
- If macOS asks whether Terminal may access your Desktop or Google Drive, click **Allow**.

On both, a failed run is retried every 30 minutes, 3 times. If all fail, a desktop notice says so, and the
Market Digest **Digests** page shows why.

## 4. Your settings

To change anything later, double-click **Market Digest** on the desktop and click **Settings**. The less common
settings are folded under **Extras** at the bottom. Saved keys and
passwords are never shown again: the page only says they are saved (with a key's last 4 characters). Leave a box
empty to keep what is saved; paste a new one to replace it.

The settings live in `digest_config.json` in the program folder. **This file contains your key and password. Never
send it to anyone.** You can also edit it in a text editor; these are the settings:

| Setting | Meaning | Default |
|---|---|---|
| `channels` | The YouTube channels to follow (links or @handles). | TheStreet |
| `gemini_api_key` | Your Gemini key. | |
| `models` | Gemini models to try, in order. If one is busy or out of free quota, the next is used. | 3.7 Flash, 3.6 Flash, 3 Flash, 3.5 Flash Lite, 3.1 Flash Lite |
| `lookback_hours` | How far back the very first run looks, or a run with `--hours`. Later runs cover everything since the last digest (up to 7 days). | 26 |
| `max_videos` | The most videos in one digest (newest first). | 20 |
| `analysts` | Only videos with these people (full names; other spellings after a slash: `"Tom Lee / Thomas Lee"`). Empty = every video. Left-out videos are listed at the bottom of the email in small print. | empty |
| `markets_only` | Leave out videos with no stocks, market levels, sectors or predictions in them. | true |
| `watchlist` | Your stocks, as tickers. Prices are fetched by this computer each day. | empty |
| `holdings` | Shares you own, by ticker, for the weights on the dashboard. Never leaves this computer. | empty |
| `weekly`, `monthly` | The weekly digest (Saturdays) and the monthly digest (the 1st). | true, true |
| `email_key` | Set when you confirm your address with the email service. Never shown on the page. | |
| `notify` | Show a notice on screen when a new digest is ready. | true |
| `open_when_ready` | Open each new digest in the browser. | on while email is off |
| `email_to` | Who receives the digest by email. Empty = no email. | |
| `smtp_user`, `smtp_password` | The Gmail account that sends it, and its app password. | |
| `smtp_host`, `smtp_port` | The mail server. Leave as is for Gmail. | smtp.gmail.com, 465 |
| `daily_time`, `schedule_on` | When the daily run happens, and whether it is on. Change these on the settings page, which also updates the system's schedule. | 07:30, on |
| `watchlist_csv` | The CSV link of your watchlist Google Sheet (see section 5a), or the path of a CSV file. Empty = no watchlist. | |
| `json_dir` | Folder for the daily JSON file (`video-digest_YYYY-MM-DD.json`) that feeds the Econova hub. Use a Google Drive for desktop folder to share it. | `digest_json` in the program folder |
| `tipranks_api_key` | Your TipRanks API key (section 5a). Empty = no TipRanks. | |

After editing the file by hand, open Market Digest > Settings and use the **Test** buttons (or run
`python digest.py --check`, section 7).

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

## 5a. Extras: a prices sheet, the Econova hub and TipRanks

*Most people do not need this section.* Your watchlist and holdings go in **Settings > Your stocks**, and prices are
fetched by the app. What follows is for advanced use: a Google Finance prices sheet instead, the shared JSON folder
that feeds the Econova hub, and TipRanks.

Optional. With a watchlist, every digest starts with a **Your watchlist** section: today's price and the week's move
for each of your stocks, what the analysts said about them, and up to five short notes such as:

- *Experts stayed bullish on GOOGL (2 of 2 calls this week), but the stock fell 12.7% this week.*
- *Experts turned cautious on NFLX: 0 of 2 calls bullish this week, against 3 of 3 the week before.*
- *Experts split on NVDA today: 1 bullish, 1 bearish.* (with a link to each side's moment in the video)
- *NVDA: 'Nvidia earnings' (2026-11-19) was flagged in video #1.*
- *Sam Stovall's year-end S&P 500 target of 8,050 is +4.5% from today's level (7,706).*
- *No new expert views today on 4 of your 6 stocks: ...*

Each note ends with **Look at next** (watch the clip, check the news, note a date). It never says buy or sell: the
digest reports what analysts said and what prices did.

Google Finance cannot export a watchlist, so the list lives in a Google Sheet whose `GOOGLEFINANCE()` formulas fetch
the prices. To set it up once:

1. Open https://sheets.new (a new Google Sheet), then **File > Import > Upload** and choose `tools/watchlist_template.csv` (in the project)
   from the program folder. Choose **Replace current sheet** and **Convert text to numbers, dates, and formulas**.
2. Change the tickers in column **B** to your own stocks (keep column A as `watch`). Add or delete rows as you like.
   Keep the two last rows (`sp500` and `us10y`): they give the S&P 500 level and the 10-year Treasury yield.
   Non-US stocks need Google Finance's form, for example `KRX:000660` for SK Hynix.
3. **File > Settings > Calculation > Recalculation: On change and every minute**, so the prices stay fresh.
4. **File > Share > Publish to web**: choose the sheet, **Comma-separated values (.csv)**, tick **Automatically
   republish when changes are made**, click **Publish**, and copy the link.
5. Open Market Digest > **Settings**, paste the link under **Watchlist**, click **Test the sheet**, then **Save**. Or put
   it in `digest_config.json` as `watchlist_csv`. Then run `python digest.py --check`: it should say
   `Watchlist sheet: 10 stocks, 10 with prices`.

**Privacy:** a published link can be opened by anyone who has it. The sheet holds only tickers and public prices,
not how many shares you own. Do not add quantities or values to it.

**Google's own "Investment Tracker" template works too** (its Watchlist tab: Symbol, Current Price, % Change). The
digest never reads its "# Shares" or "Current Value" columns, but publishing that tab would show them to anyone with
the link, so the sheet above is the safer choice. It also gives the week's change, which some notes need.
Share classes are matched: a watchlist with `GOOG` picks up the analysts' calls on Alphabet (`GOOGL`).

Each digest also saves `market-data_YYYY-MM-DD.json` next to the digest's JSON file, for the Econova hub.

### Feeding the Econova dashboard

The dashboard reads the two daily files from the Google Drive folder **Econova / Video Digests / json**.

1. Install **Google Drive for desktop** (https://www.google.com/drive/download/) and sign in. Your Drive then shows up
   as a drive letter on Windows (often `G:\My Drive`) or under `~/Library/CloudStorage/GoogleDrive-<you>/My Drive` on a Mac.
2. Open Market Digest > **Settings** and choose that folder under **Shared folder** (or type it), for example
   `G:\My Drive\Econova\Video Digests\json`. `python digest.py --check` should say the JSON folder can be written.
3. To add days from before the JSON export existed, from their saved digests:
   `python <project>\tools\email_backfill.py digests\digest-2026-10-*.html --out "G:\My Drive\Econova\Video Digests\json"`.
   Several digests on one day become one file, and a day that already has a file is left as it is. Saved digests
   sit in the folder the run started from: `market-digest\digests` for scheduled runs, and the project folder's
   `digests` for runs you started there. Give both patterns in one command, or a day can come out empty.

### Scoring the calls, and your holdings, on the dashboard

The dashboard also checks the calls against prices and shows your own holdings. It needs two more Google Sheets,
read through Google Drive (nothing is published):

1. **Market Digest Prices**: Google Finance prices and 120 days of closes for every ticker in `tickers.json`. Make
   it with `python tools\price_sheet.py --extra GOOG > price_sheet.csv` (in the project folder) (add any holding that `tickers.json` lacks after
   `--extra`), then in Google Sheets **File > Import > Upload**, **Replace spreadsheet**, with **Convert text to
   numbers, dates, and formulas**. When `tickers.json` gains tickers, import a fresh CSV over the same sheet.
2. **Google Finance Investment Tracker**: Google's template (Sheets > Template gallery > Investment tracker). Put
   your stocks in its Watchlist tab and the number you hold in **# Shares**. The dashboard weights your holdings by
   shares times price and shows the weights, never the counts.

Each sheet's file id goes into the dashboard's `quotes`/`closes` and `holdings` sources
(`docs/econova_dashboard/sources.json`). The dashboard then shows:

- **What matters today**: a few sentences, such as *Your holding GOOG: 15 bullish and 2 bearish calls in 14 days, but
  it moved -19.1% in a month; earlier calls on it were right 2 of 10 times.*
- **Your holdings**: weight, day and 1-month move, distance from the 52-week high, calls in the last 14 days and the
  latest call on each.
- **Today's calls against the prices**: each stock called today with its 1-month move, 52-week-high distance, P/E
  and the record of earlier calls on it.
- **Did the calls work?**: each call scored from the close on its video's day to the latest close, against the
  S&P 500; the hit rate and average edge of bullish and bearish calls, each analyst's record, and the best and worst
  calls.

**Coverage check:** to see how often your stocks came up in the videos lately, run
`python market_data.py --coverage` (last 14 days) or `python market_data.py --coverage --days 28`. It lists the calls
per stock (bullish, bearish, neutral, mixed) and says whether most of your stocks come up every week.

### Wall Street's view from TipRanks (optional)

TipRanks collects professional analysts' ratings and price targets. With a TipRanks API key, the digest looks up all
your stocks in **one** call (the watchlist and the stocks called most that day) and saves `tipranks_YYYY-MM-DD.json`
next to the other daily files. The dashboard then shows Wall Street's consensus (all analysts, and the top-rated ones
alone), price-target upside, Smart Score and the next earnings date next to the YouTube calls, and flags stocks
where the two disagree or that report earnings within 14 days.

TipRanks counts every tool call against a monthly quota, and keeps two separate pools: an **API key** gets 50 calls
a month on the free tier, and the **claude.ai connector** gets 10 on a free or basic TipRanks plan. Before each
look-up the digest asks TipRanks how many calls are left (that question is free). With 40 or more a month it looks
up once a weekday (about 22 calls); with fewer, once a week. It always leaves 3 calls spare. A skipped look-up is
logged; the digest itself is never held up.

1. Signed in at https://mcp.tipranks.com/, open **Keys** and create a key. It starts with `tr_live_` and is shown only
   once, so copy it straight into step 2. (The claude.ai connector is separate: it is for asking Claude about stocks.)
2. Open Market Digest > **Settings**, paste the key under **TipRanks**, click **Check the key (free)**, then **Save**.
   (Or put it in `digest_config.json` as `tipranks_api_key`. `tipranks_every_days` sets the pace by hand.)
3. **Test with TipRanks** connects, reads Apple's analyst data and uses 1 call. (The same as
   `python digest.py --tipranks-check`.)

## 6. Everyday use: Market Digest (overview, digests, chat and settings)

Double-click **Market Digest** on the desktop. The page opens in your browser at `http://127.0.0.1:8765`; no other
window appears. Only this computer can open it. **Quit** at the top right closes Market Digest (the daily digest
still runs at its time); double-clicking the desktop icon opens it again. It opens on the **Overview**, the check-up of
your stocks (section 6a). The other parts:

**Digests** answers "did it work?":
- **Every day at 07:30. Next: tomorrow at 07:30.** A green dot means the daily run is set; amber means it is turned
  off; red means the settings say on but the computer has no schedule (click **Save** in Settings to set it again).
- **Last digest today at 07:31: 5 new videos, emailed.** Red if the last run failed, with the reason in plain words
  and what to check.
- **Make today's digest now** does what the daily run does, including the email. **Preview the last 3 days** makes
  a test digest that is only shown, not emailed. Progress appears below the buttons.
- **Recent digests** opens any of the last 8 digests. **Where things go** lists who gets the email, where the data
  files are saved, and how many TipRanks look-ups this month used. **Show the log** shows what each run did.

When a newer version is out, a blue bar on the Digests page says so: **Update now** installs it in a few seconds and keeps
your settings, videos and chats.

**Settings** has everything from the setup, filled in, each with a Test button.

**Chat** answers questions about your videos:
1. At the top, choose which videos to ask about: **Last 3 / 7 / 30 days**, **All saved videos**, or **one video**
   from the second list (the chat then reads that video's full transcript).
2. **Also search the web**: needs a Gemini key with billing turned on. On a free key, the answer says web search was
   not available and uses only your videos.
3. Type your question and press **Enter** (Shift+Enter for a new line). Answers take 10 to 40 seconds.

Each answer has two parts: **From your channels**, with citations like **TheStreet 12:34** that open the video at
that moment, and **From the web**. Past chats are listed on the left. Click one to continue it. **Delete chat** asks
you to click twice so nothing is deleted by accident. The **"Ask a question about this video"** link in a saved digest
opens the chat on that video (start Market Digest first).

Good questions to start with:
- *What did my channels say about the market this week?*
- *Which stocks came up most this week, and was each channel bullish or bearish on them?*
- *Where do the channels disagree?*
- *Explain the points about Treasury yields in plain terms.*

## 6a. The Overview: your stocks' check-up, and the dashboard

Market Digest opens on the **Overview**. It starts with **Your stocks**: what your stocks are worth (if you gave the
shares you own) and a card for each stock you own or watch, the ones that need attention first:

- **A verdict in plain words**: *Analysts are positive*, *mixed*, *cautious*, or *Not enough analyst views yet*.
  It weighs the bullish and bearish calls in your channels' videos (a call counts more from an analyst whose calls
  have beaten the S&P 500, and less from one whose have not) together with Wall Street's rating from TipRanks.
  "Based on ..." says what it rests on.
- **+ points for**, **− points against** (including too much of your money in one stock), **◷ what to watch**
  (earnings soon, the videos and Wall Street disagreeing), and under **More**: things worth knowing (the price far
  from its high, how earlier calls on it turned out) and the latest calls, each linked to the moment in the video.
- Above the cards, notes on your portfolio as a whole: one stock taking a big share, few stocks, stocks with no
  analyst views.

It is a summary to help you decide, not advice to buy or sell. Below your stocks, **What the analysts said** shows
what your digests add up to, for the last 7, 30 or 90 days. It updates by itself after every digest. Every section
starts with a line saying what it shows; in short:

- **The four numbers at the top**: how many videos were read; the mood (the share of bullish calls among bullish and
  bearish ones); and how often the **bullish calls beat the S&P 500** and the **bearish calls lagged it**.
- **What matters now**: a few sentences picked by code: your holdings that analysts turned bearish on, stocks where
  the videos and Wall Street disagree, calls that are working or not, the analyst with the best record.
- **Your holdings** (if you typed share counts): each stock's weight, its price moves, and the calls on it.
- **Stocks the analysts talked about**: each stock's calls (green bullish, red bearish, grey neutral or mixed), which
  way they lean, the latest call with its reason and a link to the moment, and the price move since the first call.
- **Mood, day by day**, **Analysts** (calls, how many were right, average edge over the S&P 500), **Best and worst
  calls**, **Coming up** and **Latest videos**.

How a call is scored: from the first close after the video to the latest close, once 3 trading days have passed. A
bullish call is right if the stock did better than the S&P 500; a bearish call, if it did worse. Prices are daily
closes from Yahoo Finance (or Stooq), fetched by your computer with each digest; they can be delayed. It reports what
analysts said and what prices did; it is not investment advice.

## 6b. Weekly and monthly digests

On **Saturdays** (or the first time the computer runs after one) you get a digest of the week, Saturday to Friday;
on the **1st of the month**, one of the month before. They arrive the same way as the daily one (notice, browser,
email). Each has: a short opening written by Gemini from the numbers, how the calls did against the S&P 500, what
matters, the stocks talked about most, the analysts' records, the best and worst calls, the themes, and what is coming
up. A period with fewer than 2 videos is skipped. Turn them off in Settings > How you get the digest. To make one now:
`python period.py --week --dry-run` (or `--month`) in the program folder.

## 6c. Ask Claude about your digest (optional)

If you use the **Claude desktop app**, Market Digest can give Claude a set of tools that read your saved videos on
this computer. You then ask Claude in plain words, and it answers from *your* digest, with links to the moment in
each video:

- *"What did the analysts I follow say about Nvidia this week?"*
- *"Give me a morning briefing."* (also in Claude's **+** menu as **morning-briefing**, with **stock-view** and
  **weekly-dashboard**)
- *"Build me a dashboard of this week's calls."* (or *"How did my analysts' calls do this month?"*, from the same numbers
  as the Overview page)
- *"Add Bloomberg Television to my channels and follow Mike Wilson."* (Claude asks before changing anything.)

To turn it on: **Market Digest > Settings > Ask Claude about your digest > Connect to Claude**, then quit the Claude
app completely and open it again. **Disconnect** removes it the same way.

What to know:
- The tools run on your computer and read only the Market Digest folder. Your keys and passwords are never given
  to Claude.
- What Claude reads to answer a question (video notes, analyst calls) is sent to Claude as part of that
  conversation, like anything else you type to it.
- It works with the Claude desktop app (Windows or Mac), on any Claude plan that allows local tools. In Claude Code,
  use `claude mcp add market-digest -- python mcp_server.py` from the program folder.
- Claude's answers are information, not investment advice.

## 6d. Your stocks and Google Finance

You can give Market Digest your stocks in several ways (Settings > **Your stocks**). The easiest is the first.

0. **Paste from google.com/finance.** Click **Paste from Google Finance…**, copy your watchlist or portfolio page there
   (Ctrl+A, Ctrl+C) and paste it in. Market Digest picks out the tickers; prices then come by themselves (Yahoo
   Finance, Stooq). Do it again whenever your list changes.
1. **Connect Google**, when this version offers it (Settings shows a **Google Finance** card). Click **Connect Google**, sign in, and allow Market Digest to use
   "only the specific Google Drive files you use with this app". It creates **Market Digest - My portfolio** in your
   Drive, with the stocks you had typed. In its **My stocks** tab, type a ticker (NVDA, or NASDAQ:NVDA), the shares
   you own (empty if you only watch it) and the price you paid; Google Finance fills in the name, price, today's
   change, value, gain, 52-week range and P/E. Edit it in Google Sheets (on your phone too) or in Market Digest:
   saving in Market Digest updates the sheet, and the sheet is read with every digest (or **Update from the sheet
   now**). Do not edit the **Prices** tab: Market Digest keeps it.
2. **A Google Finance sheet of your own, without signing in** (Settings > **Extras** > "A Google Finance sheet of your own"):
   click **Make your own copy of the Market Digest sheet**, type your tickers in its **My stocks** tab (not your
   shares), then **File > Share > Publish to web**, choose **My stocks** and **Comma-separated values (.csv)**,
   **Publish**, and paste the link into Market Digest and **Save**. Market Digest reads it each morning and uses
   Google Finance's prices. Type your shares in Market Digest: a published sheet can be opened by anyone with its link.
3. **Type them in Settings**: ticker, shares, price paid. Prices then come from Yahoo Finance.
4. **Import from a file**: in your current tracker (Google Sheets, Excel), download the tab with your stocks as .csv
   or .xlsx (Google Sheets: File > Download) and choose it under **Import from a file**. It reads the Ticker or Symbol
   column, and Shares and Cost columns if there are any. Check the rows, then **Save**.

Tickers: US stocks as they are (AAPL, BRK-B). Elsewhere, either Google's form (KRX:005930, LON:VOD) or Yahoo's
(005930.KS, VOD.L); Market Digest converts between them.

**Your stocks on google.com/finance?** Google does not let any app read the watchlists and portfolios on the Google
Finance website. Bring them over once: open your watchlist or portfolio on google.com/finance, press Ctrl+A then
Ctrl+C (Cmd on a Mac), and in Market Digest > Settings > Your stocks click **Paste from Google Finance…**, paste, and
**Find my stocks**. It picks out the tickers (stocks priced in rupees are taken as NSE). Add the shares you own,
check the list, and **Save**. From then on, keep them in Market Digest or in your Google Finance sheet.

## 6e. Privacy: where your data is

- **On your computer**: your settings and keys (`digest_config.json`), your stocks and share counts, the saved
  videos, digests and chats, and the prices. Nothing is sent to a Market Digest server: there is none.
- **In your Google account**, if you connect Google: your portfolio sheet. Market Digest can open only the files it
  created; it cannot see anything else in your Drive. Google Account > Security > Third-party access shows and can
  remove it; **Disconnect** in Settings does the same (the sheet stays yours).
- **Sent to Google Gemini**: each video's captions and the numbers behind the weekly opening, to be summarised.
  Your stocks and share counts are not.
- **Sent to TipRanks**, if you add a key: the tickers to look up.
- **The email service**, if you use it: your address, and each digest it sends (a copy stays in the sender's Sent
  folder). The digest email lists your watchlist's prices but never your share counts.

## 7. Useful commands

Everything below can also be done on the Market Digest page; these are for when you prefer typing.
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
| `python app.py` | Opens Market Digest (the same as the desktop shortcut). |
| `python digest.py --rebuild 2026-10-22 --dry-run` | The Econova JSON file for an earlier day's digest, written to `digests\` to look at. Without `--dry-run` it goes to the JSON folder, unless that day already has a file. |

To run the scheduled task exactly as Windows would: open **Task Scheduler**, click **Task Scheduler Library**,
right-click **Market video digest**, choose **Run**. Its log is in `digest.log` in the program folder.

**On a Mac**, open Terminal, run `cd ~/market-digest`, and use the same commands with `python3` instead of `python`,
for example `python3 digest.py --check`. To start the scheduled run now:
`launchctl kickstart gui/$(id -u)/com.nugenix.market-digest`. Its log is `~/market-digest/digest.log`.

## 8. Changing, updating and removing it

- **Change channels, email, keys or time:** Market Digest > **Settings**, then **Save**. Saving also updates the
  daily schedule. To pause the digest, untick **Make the digest every day** and save.
- **Update to a new version:** open Market Digest. When a newer version is out, a blue bar on the Digests page says so; click
  **Update now**. It takes a few seconds and keeps your settings, saved digests and chats. (By hand: get the new
  files and double-click the installer again; the page opens with your settings filled in, click **Finish**.
  `install.bat -Unattended` does the same without opening the page.)
- **Remove it from Windows:**
  1. In Command Prompt: `schtasks /delete /tn "Market video digest" /f`
  2. Delete the folder `C:\Users\<you>\market-digest`.
  3. Delete the **Market Digest** shortcut from the desktop. If you connected Claude, click **Disconnect** in Settings first.
  4. Optional: delete `C:\Users\<you>\ytmd` (the saved transcripts).
- **Remove it from a Mac:** in Terminal run
  `launchctl bootout gui/$(id -u)/com.nugenix.market-digest; rm ~/Library/LaunchAgents/com.nugenix.market-digest.plist`,
  then delete the folders `~/market-digest` and (optional) `~/ytmd`, and `Market Digest` from the desktop.

## 9. If something goes wrong

Open **Market Digest** > **Digests**. It says whether the last run worked and, if not, why. In **Settings**, click each
**Test** button: the one that fails names the problem. Then see [TROUBLESHOOTING.md](TROUBLESHOOTING.md), which lists
each problem we have actually seen, its cause and the fix.

The most common:

| You see | Fix |
|---|---|
| "Google says this key is not valid" | Copy the key again from Google AI Studio and paste the whole key. |
| "Gmail did not accept this address and app password" | Use a Gmail **app password** (16 letters), not your normal password. |
| No email today | Market Digest > Digests says why. "No new videos" means the channels posted nothing new. |
| "Market Digest stopped responding" | It was closed (Quit, or the computer restarted). Double-click **Market Digest** again. |
| The chat says web search was not available | Normal on a free Gemini key. Web search needs billing. |
