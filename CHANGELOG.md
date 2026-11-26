# Changes

Installed copies update themselves: Market Digest shows **Update now** on its Home page when a new version is out.

## Cloud version: private beta (22 Nov 2026)

- **Invitation only.** Only the Google addresses in the `BETA_MEMBERS` secret can use the site. The database rules
  check the members list on every read and write, so anyone else who signs in reads nothing and saves nothing, and
  sees a plain "invitation-only" page. Signed-out visitors no longer see any live data: the front page says it is a
  private beta and shows what members get instead of today's signals.
- The list is a secret, not a file, because the repository is public. Each engine run copies it into Firestore;
  taking someone off removes their access on that run, and a broken secret changes nothing.
- Only members get emails and have their stocks covered.
- Tests: 168 unit tests; the browser test (60 checks) now covers a stranger, a member, and someone taken off the list.

## Cloud version: what happened, in plain words (21 Nov 2026)

Ideas taken from Google Finance, made from our own data:

- **"In short" on every stock page**: one paragraph saying where the analysts stand and why (supporting facts first,
  what goes against them after "though"), how the price moved, the bull and the bear case in the analysts' words,
  and what is coming (earnings). Written by the engine from the card, so it never disagrees with the numbers.
- **The day's big moves first**: Home opens with "NVDA fell 14.0% on Friday · analysts say WAIT", one click from what
  the analysts say. The daily email says it too.
- **Your stocks always in view**: the side menu lists them with their signal and the day's move.
- **Prices a day late, fixed**: a stock fetched before the close was out (Friday's close missing on Saturday morning)
  was not asked again that day, so NVDA's 14% fall did not show. A stock now counts as up to date only once it has
  the latest finished trading day. And every stock in the engine's list gets its price, not only the first 80.

## Cloud version: trust and polish (21 Nov 2026)

- **Signals you can believe.** One vote an analyst (their latest call), recent calls count most, Wall Street's
  usual Buy is no longer a Yes by itself, and confidence follows how one-sided the views are. Before, NVDA showed
  YES at 87% on 32 bullish and 26 bearish calls; it is now a Wait. Clearly bullish stocks keep their high confidence.
- **Dividend yields fixed.** TipRanks gives them in percent already; they were multiplied by 100 again (NVDA showed 34.5%).
- **A new front page**: live numbers (videos read, calls, analysts), one real stock with everything behind its signal,
  how it works, and why the signal can be checked. The example now has the market card too.
- **Look**: the Inter typeface (named before but never loaded), lighter headings, a share image and app icons for
  phones, and no "New" tag beside every analyst not yet rated.
- **Emails**: each stock links to its page, and the inbox preview line says what changed.

## Cloud version (in `cloud/`)

- **A hosted product**: customers open a website, sign in with Google, pick their stocks (a starter list, search, or
  paste) and see their dashboard. No install, no keys, no settings.
- **One shared engine** reads the videos once for everyone (Gemini watches the YouTube link), fetches prices and
  TipRanks ratings within the free allowance, and writes a card for each stock.
- **Pages**: My stocks (signals, "For you today", portfolio value), a stock page (price chart with analyst calls
  marked, signal and its history, Wall Street's rating, target and Smart Score, key numbers, bulls and bears, every
  call with its result), Ideas, Analysts with ratings, Calendar, Account.
- **Emails** from one address to the address signed in with: a daily brief (every weekday, or only when a signal
  changes) and a weekly summary.
- Free tiers only: Firebase (hosting, sign-in, database) and GitHub Actions.

## 1.4.0 (first release)

- **Your own Google Finance data.** "Connect Google" keeps your stocks in a Google Sheet in your own Drive, priced
  live by Google Finance. Edit it in Google Sheets (on your phone too) or in Market Digest; both stay the same.
  Market Digest can see only that one file. No server: your computer talks to Google directly.
- **A check-up of every stock you own or watch**, on the new Overview page: are the analysts positive, mixed or
  cautious, and why, in plain words (points for and against, whose calls have been good, Wall Street's rating, the
  price), what to watch (earnings, disagreements), and notes on your portfolio as a whole (too much in one stock).
- The Overview is the first page; the old home page is now **Digests**. A glossary explains the terms.
- Import your stocks from an existing tracker (CSV or Excel), with the price you paid, to see your gain.
- **The Overview is a table, like a Google Finance watchlist**: for each of your stocks, **Invest? Yes / No / Wait**,
  a **confidence** percentage, the analysts' calls, Wall Street's rating and target, a price chart and the 52-week
  range. Click a stock for its key numbers and the facts behind the signal. Tabs: Ideas, Analysts, Calendar & videos.
  Far less text. The weekly digest and Claude's `my_stocks` carry the same signal.
- **Simpler first run**, about two minutes: **Get my free key** and **Paste my key** (checked by itself), then
  paste your stocks straight from google.com/finance; three popular channels are already chosen. No links, no other keys.
- On a Mac with no Python, the installer sets up a private copy by itself.
- Google Finance without signing in (Settings > Extras): copy the Market Digest template sheet, publish it, paste its link; your shares stay in the app.
- The weekly digest starts with your stocks' check-up; Claude gets a `my_stocks` tool.

## 1.3.0

- **Dashboard**: a Dashboard page in Market Digest that fills itself from your own digests: what matters now, the
  stocks the analysts talked about (and which way they lean), how their calls did against the S&P 500, each
  analyst's record, your holdings by weight, the mood day by day, and what is coming up. 7, 30 or 90 days.
- **Weekly and monthly digests** on top of the daily one (Saturdays, and the 1st of the month): the period's
  most-discussed stocks, how the calls did, the analysts' records and what to watch next.
- **Your stocks in the app**: type your watchlist, and the shares you own if you like. Prices are fetched by your
  computer, with no Google Sheet and no account. Share counts never leave your computer.
- **Email with only your address**: confirm it with a 6-digit code and the Market Digest email service sends your
  digests. No Gmail app password needed (your own Gmail still works if you prefer).
- Claude gets a `market_overview` tool with the dashboard's numbers.

## 1.2.0

- Three-step setup, no terminal questions, no email needed (a notice on screen and the digest opens in the browser).
- No console window; a Quit button; one-click updates.
- Connect to Claude: tools that read your digest on your computer.

## 1.1.0

- Market Digest app: settings in the browser with a Test button for each, a home page that shows whether the digest
  ran. Analysts to follow; leave out videos not about markets.

## 1.0.0

- The daily digest by email, the chat, the JSON files for the Econova hub, Google Finance prices, TipRanks, Mac support.
