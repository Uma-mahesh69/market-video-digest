# Setting up "Connect Google" (once, by the developer)

"Connect Google" lets each user keep their stocks in a Google Sheet in **their own** Drive, priced by Google Finance,
which Market Digest on their computer reads and updates. There is no server: each user's computer talks to Google
directly, signed in as that user. For this, Google needs to know the app: a free **Google Cloud project** with an
**OAuth client** of type **Desktop app**. It takes about 15 minutes, once. Users never see any of it.

## What users are asked to allow

Only one permission: **"See, edit, create and delete only the specific Google Drive files you use with this app"**
(`drive.file`). Market Digest can open the spreadsheet it creates for that user, and nothing else in their Drive.
Google classes this permission as non-sensitive, so the app does **not** need Google's security review, and users do
not see an "unverified app" warning once the app is published (step 5).

## Steps

1. **Project.** Go to https://console.cloud.google.com/, sign in with the account that should own the app
   (naravaumamahesh@gmail.com or a company account), and create a project named `Market Digest`.
2. **APIs.** In **APIs & Services > Library**, enable **Google Sheets API** (and **Google Drive API**).
3. **Consent screen.** In **APIs & Services > OAuth consent screen** (called **Google Auth Platform** in newer
   consoles):
   - User type: **External**.
   - App name: `Market Digest`; user support email and developer contact: your address.
   - Optional but better: an app logo, and links to a home page and privacy policy (the GitHub README works as
     the home page; the "Privacy" section of USER_GUIDE.md can be the policy).
   - **Scopes / Data access:** add `.../auth/drive.file` only.
4. **Client.** In **APIs & Services > Credentials > Create credentials > OAuth client ID**, choose **Desktop app**,
   name it `Market Digest desktop`. Copy the **Client ID** (ends in `.apps.googleusercontent.com`) and the
   **Client secret**.
5. **Publish.** Back on the consent screen (**Audience** in newer consoles), click **Publish app** so its status is
   **In production**. While it is "Testing", only the test users you list can connect, and their sign-in expires
   after 7 days.
6. **Into the app.** Put both values in `service.json` in the project:

   ```json
   {
     "email_service": "...",
     "email_service_token": "...",
     "google_client_id": "1234-abc.apps.googleusercontent.com",
     "google_client_secret": "GOCSPX-..."
   }
   ```

   Commit it and raise `VERSION`. Installed copies get it with **Update now**; the Settings page then shows
   **Connect Google** instead of "not set up in this version".

Is it all right that the client secret is in a public repository? For a **Desktop app** client, yes: Google states that
installed apps cannot keep a secret, and treats it as public. The sign-in is protected by PKCE (a one-time proof made
on the user's computer) and by the user's own consent, and the sign-in result goes only to that computer.

## How it works, for developers

- `google_link.start()` sends the browser to Google with `drive.file`, `access_type=offline` and a PKCE challenge;
  Google returns to `http://127.0.0.1:<port>/oauth/callback` on the user's own computer (loopback redirects are
  allowed for Desktop clients on any port).
- The refresh token is saved in that user's `digest_config.json` as `google_token` and is never sent to any page.
- On first connection the app creates **Market Digest - My portfolio**: a "My stocks" tab (ticker, shares, price
  paid, then GOOGLEFINANCE columns filled by one `MAP` formula each), a "Prices" tab the app keeps (the S&P 500 and
  the stocks the analysts call), and an "About" tab.
- Each daily run reads "My stocks" (the sheet is the source of truth) and the Prices tab, and records each day's
  prices in `prices.json`. Google does not let apps read GOOGLEFINANCE's **history** through the API, so the history
  is built day by day and filled in from Yahoo Finance or Stooq.
- Saving stocks in the app writes them to the sheet.
- Limits: the Sheets API allows 300 requests a minute per project and 60 per user; Market Digest makes a handful a day
  per user.
