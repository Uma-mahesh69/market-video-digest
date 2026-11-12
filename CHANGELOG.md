# Changes

Installed copies update themselves: Market Digest shows **Update now** on its Home page when a new version is out.

## 1.4.0 (first release)

- **Your own Google Finance data.** "Connect Google" keeps your stocks in a Google Sheet in your own Drive, priced
  live by Google Finance. Edit it in Google Sheets (on your phone too) or in Market Digest; both stay the same.
  Market Digest can see only that one file. No server: your computer talks to Google directly.
- **A check-up of every stock you own or watch**, on the new Overview page: are the analysts positive, mixed or
  cautious, and why, in plain words (points for and against, whose calls have been good, Wall Street's rating, the
  price), what to watch (earnings, disagreements), and notes on your portfolio as a whole (too much in one stock).
- The Overview is the first page; the old home page is now **Digests**. A glossary explains the terms.
- Import your stocks from an existing tracker (CSV or Excel), with the price you paid, to see your gain.
- Google Finance without signing in: copy the Market Digest template sheet, publish it, paste its link; your shares stay in the app.
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
