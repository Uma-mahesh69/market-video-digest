# Before charging customers

The product works on free tiers and is fine for a private beta with people you know. These are the things to settle
before a public, paid launch. None of them is a coding task; most need a decision or a signature.

## 1. Regulation: is this investment advice?

A public "Invest? Yes / No" per stock may count as investment advice or research, which is regulated:

- **India:** SEBI's Research Analyst and Investment Adviser regulations.
- **United States:** the SEC's investment adviser rules (there is an exemption for publishers of general,
  impersonal commentary, with conditions).

The product is built to stay on the "general information" side: the same signal for everyone, described as what
analysts said, with a disclaimer on every page and in every email, and terms that say so. That helps and is not a
guarantee. **Get a written opinion from a securities lawyer in each country you sell in.**

## 2. Data licences

| Data | Today | Needed for a paid product |
|---|---|---|
| **TipRanks** ratings, targets, Smart Score | A free developer key (50 calls a month) | A commercial licence that allows showing their data to your customers. Ask TipRanks. |
| **Prices** | Yahoo Finance's public chart data (no contract) | A licensed feed with display rights (Polygon, Twelve Data, Finnhub, EOD Historical Data). `app/prices.py` has one function to replace. |
| **Videos** | Gemini reads public YouTube links; the site links to the moment and stores only short notes | Check YouTube's terms and each channel's for commercial summarising. Linking and brief quotation is the usual safe ground. |
| **Gemini** | Free tier | On the free tier Google may use what is sent to improve its products, and the daily limits are low. Use a paid key. |

## 3. Privacy and terms

`cloud/web/privacy.html` and `terms.html` are honest first drafts that match what the code does. Have a lawyer read
them. If you have users in the EU or UK (GDPR) or serve Indian users at scale (DPDP Act), you also need a named
contact for data requests, which the pages already point to.

## 4. Things not built yet

- **Payments.** There are no plans or billing. Everyone is "free during the beta". Razorpay or Stripe needs a small
  server-side piece (Firebase's paid plan, or a check in the engine) to mark who has paid.
- **Monthly summary email.** Daily and weekly exist.
- **Brokerage import.** Customers pick, search or paste; nothing connects to a broker.
- **An admin screen.** Channels and analysts are edited in `cloud/sources.json`.
- **Monitoring.** `#/status` shows the last run; GitHub emails you when a run fails. There is no uptime alerting.
- **Backups.** Firestore's scheduled backups need the paid plan. The shared data can be rebuilt by the engine; users'
  lists cannot.

## 5. Make it yours

- **The sign-in window's name.** Google Cloud console > APIs & Services > OAuth consent screen: set the app name
  and logo, or it shows the project's address.
- **Your own domain.** Firebase Hosting > Add custom domain.
- **Email from your domain.** Gmail is limited to 500 a day and shows a Gmail address. An email service with your
  domain (and SPF/DKIM set) delivers better.
- **App Check.** Firebase's App Check stops other sites from using your database quota.
