# Putting Econova online

This takes about 30 minutes, once. Everything used is free. You need the Google account that will own the product
and this GitHub repository. Do the steps in order; each says exactly where to click.

> **Never paste a key or password into a chat, an email or a file in this repository.** They go only into GitHub's
> "Secrets" page (step 3), where nobody can read them back.

## What you are setting up

| Piece | What it does | Where it lives |
|---|---|---|
| The website | What customers see: sign-in, dashboard, stock pages | Firebase Hosting (`https://YOUR-PROJECT.web.app`) |
| Sign-in | "Continue with Google" | Firebase Authentication |
| The database | Each customer's list; the shared stock cards | Firebase Firestore |
| The engine | Every hour: reads new videos once for everyone, updates signals, sends emails | GitHub Actions (this repository) |

## Step 1. Create the Firebase project (10 minutes)

1. Open https://console.firebase.google.com and click **Create a project** (or **Add project**).
   - Name it, for example `market-digest`. Under the name, Firebase shows the **project ID**: it becomes your
     address (`https://that-id.web.app`), so click the pencil and choose a good one now. It cannot be changed later.
   - Google Analytics: turn it **off**. Click **Create project**.
2. **Sign-in:** left menu **Build > Authentication > Get started**. On the **Sign-in method** tab click **Google**,
   switch **Enable** on, choose your support email, **Save**.
3. **Database:** left menu **Build > Firestore Database > Create database**.
   - Location: choose the one nearest your customers (for India, `asia-south1 (Mumbai)`). It cannot be changed later.
   - Choose **Start in production mode**, then **Create**.
4. **A key for the engine:** click the gear (top left) **> Project settings > Service accounts > Generate new private
   key > Generate key**. A `.json` file downloads. Keep it private; you paste its contents into GitHub in step 3.
5. **Let that key publish the website:** open https://console.cloud.google.com/iam-admin/iam and pick your project at
   the top. Find the row whose name starts with `firebase-adminsdk`, click its pencil, then **Add another role**
   three times and add **Firebase Admin**, **Service Usage Consumer** and **API Keys Viewer**. **Save**.

## Step 2. Get the three other keys (10 minutes)

| Key | Where | Notes |
|---|---|---|
| **Gemini** (reads the videos) | https://aistudio.google.com/apikey > **Create API key** | Free. About 40 videos a day. |
| **TipRanks** (Wall Street's ratings) | https://mcp.tipranks.com > sign in > create a key | Free: 50 look-ups a month. It starts with `tr_live_`. Optional: without it those columns stay empty. |
| **Gmail app password** (sends the emails) | https://myaccount.google.com/apppasswords | For the Gmail address the emails should come from. That account needs 2-Step Verification on. Name it "Market Digest"; Google shows 16 letters. Optional: without it no emails are sent. |

## Step 3. Put the keys into GitHub (5 minutes)

In this repository on GitHub: **Settings > Secrets and variables > Actions > New repository secret**. Add each of
these (the name exactly as written, the value pasted):

| Name | Value |
|---|---|
| `FIREBASE_SERVICE_ACCOUNT` | Open the `.json` file from step 1.4 in Notepad, select everything, copy, paste. |
| `GEMINI_API_KEY` | The Gemini key. |
| `TIPRANKS_API_KEY` | The TipRanks key. |
| `SMTP_USER` | The Gmail address the emails come from. |
| `SMTP_PASSWORD` | The 16-letter app password. |
| `BETA_MEMBERS` | Who may use the site (a private beta): their Google email addresses, separated by commas. Put your own first. |

Optional, on the **Variables** tab next to Secrets: `CONTACT_EMAIL` (shown on the privacy and terms pages; the
sending address is used if you leave it out), `MAIL_FROM_NAME` (default "Econova"), `SITE_URL` (only when you
add your own domain later).

Then delete the `.json` file from your Downloads folder.

## Step 4. Switch it on (2 minutes)

The engine's hourly timer only works from the `master` branch, so the new code has to be merged into it:

1. Open https://github.com/Uma-mahesh69/market-video-digest/compare/master...feature/cloud?expand=1
2. Click **Create pull request**, then **Merge pull request**, then **Confirm merge**.

Copies of the old desktop app that are already installed keep working exactly as they are. They will not be offered
this version as an update, because the program's files moved to the `app/` folder; to move one to the newest desktop
version, run its installer again from a fresh download.

## Step 5. Check, publish, start (10 minutes, mostly waiting)

On GitHub click the **Actions** tab. In the list on the left:

1. **Check setup > Run workflow > Run workflow.** After a minute or two, open the run. The summary lists five checks.
   Firebase, YouTube and Gemini must say **OK**. If one says FAILED, the line says why; fix it and run again.
2. **Deploy website > Run workflow.** When it is green, the summary shows your address.
3. **Engine > Run workflow.** The first run takes 10 to 15 minutes. After that it runs by itself every hour.

## Step 6. Try it

Open your address. You should see the front page with a table of example stocks. Click **Continue with Google**,
pick your stocks, and you are on your dashboard.

- **Signals fill in over the first days.** The engine reads up to 8 videos an hour and 40 a day; a stock needs a few
  analyst calls or a Wall Street rating before it shows Yes or No. Prices appear after the first run.
- **`#/status`** (Account > Service status) shows how the last run went.
- To send yourself the daily email now: **Actions > Engine > Run workflow**, and choose `daily` in the box.

## What the free tiers allow

| Limit | Roughly means | First thing to upgrade when you hit it |
|---|---|---|
| Firestore: 50,000 reads a day | 1,500 to 2,500 dashboard visits a day | Firebase "Blaze" plan (pay as you go; a few dollars at this size) |
| Gemini: about 40 videos a day | The 6 channels' most relevant videos | A paid Gemini key: more channels, every video |
| TipRanks: 50 look-ups a month | Each stock's rating refreshed every few days, users' stocks first | A paid TipRanks plan (also needed to show their data commercially) |
| Gmail: 500 emails a day | 500 customers on the daily email | An email service (Brevo, Resend) with your own domain |
| GitHub Actions | Free and unlimited for a public repository | Nothing; note the timer pauses after 60 days with no commits |

## Changing things later

- **Channels and analysts:** edit `cloud/sources.json` on GitHub (pencil icon), commit. The next run uses it.
- **When the email goes out:** `email.hour_utc` in the same file (2 = 02:00 UTC = 7:30 am in India).
- **The website:** any change under `cloud/web/` on `master` is published automatically.
- **Your own domain:** Firebase console > Hosting > Add custom domain, then set the variable `SITE_URL` to it.
- **Who may use it (the private beta):** edit the secret `BETA_MEMBERS` (Settings > Secrets and variables > Actions >
  `BETA_MEMBERS` > Update), one Google address per invitee, separated by commas. The next engine run applies it
  (Actions > Engine > Run workflow, to apply it at once). Someone taken off loses access on that run; what they saved
  stays theirs to download or delete. Anyone else who signs in sees an "invitation-only" page and can read nothing:
  the database rules check the list on every read and write, so it cannot be got round from the browser.
  To open the site to everyone later: set `PRIVATE_BETA = false` in `cloud/web/js/app.js` and change `member()`
  back to `signedIn()` in `cloud/firestore.rules` (and `public` back to `if true`).

## If something goes wrong

| What you see | What to do |
|---|---|
| Check setup: Firebase FAILED | The secret is not the whole `.json` file. Paste it again, from the first `{` to the last `}`. |
| Check setup: Gemini FAILED with 400 or 403 | The key is wrong or was copied with a space. Create a new one and replace the secret. |
| Check setup: Gemini FAILED with 429 | The day's free allowance is used up. Try again tomorrow; nothing is broken. |
| Deploy website fails with "permission" or "403" | Step 1.5 was missed or needs a few minutes to take effect. Check the three roles, wait five minutes, run again. If it still fails, add the role **Editor** to the same row and run again. |
| Sign-in window says the domain is not authorised | Firebase console > Authentication > Settings > Authorized domains: add the address you are opening. |
| The dashboard says "Fetching…" for a stock | It is new to the engine. It appears after the next hourly run. |
| No emails arrive | Check setup's Email line; then Account > Emails in the app; then the spam folder. |

For anything else, open the failed run under **Actions**, copy the red lines, and send them to whoever maintains the code.
