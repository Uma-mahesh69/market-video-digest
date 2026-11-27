# The mentor's list, 20 to 30 November: what we found and what we built

Five items came out of the mentor review. Each was explored against one question: does it make Econova more useful
to an investor, without turning it into something we are not allowed or not able to be? Written 27 November 2026.

| Item | Verdict | In the product |
|---|---|---|
| Trading APIs (Public.com, Robinhood) | **Not now.** Link out, do not trade | Nothing new; "Google Finance" link-out already on every stock |
| Prediction markets (Kalshi, Polymarket) | **Yes, Kalshi, read-only** | "What the money says" card: Home and Calendar |
| First-principles framework ("what if I have $10k?") | **Yes, as evidence, never as advice** | "Before you decide" on every stock page; five principles on the practice page |
| Historical data and backtesting | **Yes** | Track record replay, plus "What $10,000 would have become" |
| Paper trading | **Yes** | Practice portfolio: $10,000 of pretend money at real prices |
| E2E and platform testing | **Yes** | Automated suites, plus the manual plan in [TEST_PLAN.md](TEST_PLAN.md) for Anil and Uma |

## 1. Trading APIs: Public.com and Robinhood

**What exists.**
- **Public.com** has an official Trading API for stocks, options and crypto: orders, accounts and market data.
  It is granted per person, on request, and its agreement says it is for **personal, non-commercial use**, so a
  product cannot place trades for its users through it.
- **Robinhood** has **no official stock-trading API**. Its official API covers crypto only. The stock libraries on
  GitHub reverse-engineer the private app API, which breaks Robinhood's terms and can stop working at any time.

**Why not now.**
- **Regulation.** Taking orders for users makes us a broker or an adviser. In India that needs SEBI registration, and
  buying US stocks from India also runs under RBI's Liberalised Remittance Scheme.
- **Reach.** Neither broker serves our first users, who are mostly in India.
- **Positioning.** Econova's trust comes from describing what experts said and scoring it. Selling the trade would
  give it a reason to push people to act.

**Later, if we want it.** A plain "Open in your broker" link next to the Google Finance one; or, for US users,
an *investment adviser* partnership with a broker that allows it (Alpaca's Broker API is built for apps). Both need
legal advice first.

## 2. Prediction markets: Kalshi and Polymarket

**What exists.** Both publish their market data openly, with no key and no account:
- **Kalshi**, a US exchange regulated by the CFTC: the Fed's next rate decision, CPI, jobs reports, recessions,
  S&P 500 levels, even what a company will say on its earnings call.
- **Polymarket**: similar markets, settled in crypto; more political and world events.

**Why it adds value.** Econova's whole idea is accountability: who has been right? A prediction market is a crowd
that is held to account every day by its own money. Putting "the experts on TV say the Fed will cut" next to
"people betting real money give it 35%" is exactly the kind of second opinion our users cannot get easily.

**What we built.** A once-a-day read of four Kalshi markets: the Fed's next decision, the next CPI reading, the next
jobs report, and a US recession next year. They show as "What the money says" on Home and the Calendar, with
the date each one settles. Kalshi only, because it is regulated and its markets map onto what moves stocks;
Polymarket adds little for this and is crypto-settled.

**Before charging money.** Read Kalshi's data terms for commercial display, or license the data.

## 3. A first-principles framework: "what should I invest in if I have $10k?"

**The trap.** Answering that question directly is personal investment advice. In India that needs a SEBI
registration; it also cannot be done well without knowing the person's goals, time and other money.

**What we do instead.** We present the data an investor needs to decide for themselves, question by question:

1. What do the experts say? (the signal, its confidence, the top-rated experts' view)
2. Have they been right about it before? (their record on this stock)
3. Do the experts on air and Wall Street agree?
4. How has the price moved? (a month's move, distance from the 1-year high, P/E)
5. What could move it soon? (results dates)
6. How much of your money is (or would be) in it?

That is **"Before you decide"** on every stock page. The practice page adds five general principles (the market
as yardstick, spreading money, thinking in years, writing down why, checking who says it). And the $10k question
gets two honest, data-based answers: what $10,000 would have become following our signal, and a $10,000 practice
portfolio to try one's own ideas.

## 4. Historical data and backtesting

**What we have.** A year of daily prices for every stock we cover, and four months of read videos (every call,
dated). Wall Street's ratings are only current, not historical.

**What we built.**
- **The replay** (Track record page): every week over the past months, the signal worked out from the calls known
  *at that time*, then judged on the month after against the S&P 500. No hindsight: Wall Street's rating and the
  experts' stars are left out, because using today's values for past weeks would be cheating.
- **What $10,000 would have become**: split equally across that week's Bullish picks, held a month, rolled into the
  next month's picks, next to $10,000 left in the S&P 500. No costs or taxes.

**Limits, said on the page.** A few months is a small sample. The record grows by itself every day.

**Next.** More history (older videos can be read once, at a cost), and a record per expert: "$10,000 following
Dan Ives".

## 5. Paper trading

**What we built.** A practice portfolio on each member's account: $10,000 of pretend money, buy and sell any stock we
cover at its latest close, see the result against the S&P 500 over the same days and the experts' view on each
holding. A warning when one stock is more than a quarter of it. Start again any time.

**Why it adds value.** It answers "what if I have $10k?" by letting people try, with no money at risk and no advice
given. It also teaches the habits in the principles card, and it is a reason to come back.

**Next.** Compare your picks with following the signal; a members' leaderboard once the beta is bigger.

## 6. E2E and platform testing

Already automated: 188 unit tests and an 82-check browser test that runs the whole product (sign-in, every page,
the practice portfolio, the security rules, a phone screen) against a local copy of Firebase. A smoke test checks
the live site. The manual part for Anil and Uma, on real phones and browsers, is in [TEST_PLAN.md](TEST_PLAN.md).

## Sources

- Public.com Trading API: https://public.com/get/api, terms: https://public.com/documents/individual-api-program,
  docs: https://public.com/api/docs
- Robinhood crypto API: https://docs.robinhood.com/crypto/trading
- Kalshi market data, no key needed: https://docs.kalshi.com/getting_started/quick_start_market_data
- Polymarket market data: https://docs.polymarket.com/market-data/overview
