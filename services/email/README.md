# The Market Digest email service

With this service, people who use Market Digest only type **their own email address** and a code to get their
digests by email. The emails come from the developer's Gmail, through a small Google Apps Script. Nobody needs a Gmail
app password, and no password ships with the app.

It is set up **once, by the developer** (about 5 minutes). Users never see this page.

## How it works

1. In Market Digest > Settings, a user ticks **Also email it to me**, types their address and clicks **Email me a code**.
2. The service emails a 6-digit code to that address. The user types it in. Only the owner of the inbox can do that,
   so nobody can use the service to send mail to someone else.
3. The service gives that user's computer its own secret key. Each digest (daily, weekly, monthly) is sent with it.

Limits, so a copy of the app cannot run up your account: 3 codes and 8 emails a day per address, 40 codes a day in
all. Gmail itself allows **100 emails a day** from a personal account through Apps Script (1,500 with Google
Workspace), so a personal account suits about 30 to 50 daily users. Every email sent also appears in the account's
**Sent** folder.

## Setting it up

You need: the Google account the emails should come from (naravaumamahesh@gmail.com).

1. Open the spreadsheet **Market Digest email service (private)** in that account's Google Drive (already made: it
   has a **Users** tab). Keep it private: it will list your users' email addresses.
2. In it: **Extensions > Apps Script**. Delete what is in the editor, paste the whole of
   [`Code.gs`](Code.gs), and click **Save** (the disk icon).
3. Click **Deploy > New deployment**. Click the gear next to "Select type" and choose **Web app**. Set:
   - Description: `Market Digest email service`
   - **Execute as: Me**
   - **Who has access: Anyone**

   Click **Deploy**.
4. Google asks to authorize: choose your account. On "Google hasn't verified this app", click **Advanced >
   Go to (project name) (unsafe)**: it is your own script. Allow it to send email and use the spreadsheet.
5. Copy the **Web app URL** (it ends in `/exec`). Open it in a browser: it should say
   "Market Digest email service is running."
6. Put the URL in `app/service.json` in the project, as `"email_service": "https://script.google.com/macros/s/.../exec"`,
   commit it, and raise `VERSION`. Every installed copy picks it up with its next update.

## Looking after it

- **See who uses it:** the Users tab. `status` is `pending` until the code is typed in, then `confirmed`.
- **Stop an address:** type `blocked` in its `status` cell.
- **Change the script:** edit it in Apps Script, then **Deploy > Manage deployments > (pencil) > Version: New
  version > Deploy**. The URL stays the same.
- **How much quota is left today:** the app's Settings shows it if a send fails; or run
  `MailApp.getRemainingDailyQuota()` in the Apps Script editor.
- `APP_TOKEN` in `Code.gs` must match `email_service_token` in `app/service.json`. It identifies the app; it is not a
  password (the app is public). The protection is the code sent to each address.
