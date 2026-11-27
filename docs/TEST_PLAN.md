# Test plan: E2E and platform testing (Anil and Uma)

The automated tests cover the logic and one desktop and one phone browser. This plan covers what only people can
check: real devices, real Google accounts, real emails, and whether it makes sense to a new member.

## Before each release (automated, about 10 minutes)

| What | How | Must be |
|---|---|---|
| Unit tests | `python -m pytest -q tests` | all pass (188) |
| Whole product in a browser | start the emulators, load demo data, `node cloud/tests/e2e.cjs` (see cloud/README.md) | 82 of 82 |
| The live site | `node cloud/tests/live.cjs` | all pass |

## Platforms (manual)

Split the list: Anil takes the Android and Windows rows, Uma the iPhone and Mac rows. Tick each cell.

| | Chrome | Safari | Edge | Firefox |
|---|---|---|---|---|
| Windows laptop | | n/a | | |
| Mac | | | n/a | |
| Android phone | | n/a | n/a | n/a |
| iPhone | | | n/a | n/a |
| iPad or tablet | | | n/a | n/a |

On each: sign in, open Home, a stock page, Track record and the practice portfolio; rotate the phone; try dark
mode (Account, Appearance). Note anything cut off, overlapping or slow.

## Journeys (manual, on a phone and on a laptop)

Use a test Google account that is on the members list, and one that is not.

1. **A stranger.** Not on the list: sees the invitation page, nothing else. Signs out cleanly.
2. **First visit.** On the list: picks a starter pack, searches a stock, pastes a Google Finance watchlist, reaches
   Home. Is it clear what Bullish, Split and Bearish mean without reading the help?
3. **A stock.** Open one you know. Read "In short" and "Before you decide". Does each answer match the numbers
   below it? Click a "watch" link: does the video open at the right moment?
4. **Experts.** Open the Experts page, open an expert, follow them. They appear on Home under "From the experts you
   follow".
5. **Track record.** Do the numbers on Home match the Track record page? Is "What $10,000 would have become" clear?
6. **Practice.** Start, buy two stocks, sell one, start again. Cash and value add up?
7. **Emails.** Next morning: the daily email arrives, the links open the right stock, "Change or stop these emails"
   works. Switch to "Only when something changes" and check the next day.
8. **Feedback.** Send a note; it reaches the team's mailbox after the next engine run.
9. **Account.** Download my data (the file has the list, follows and practice portfolio). Delete the account on the
   test login: signing in again starts from nothing.
10. **Taken off the list.** Remove the test address from `BETA_MEMBERS`, run the engine: the next visit shows the
    invitation page.

## Reporting a problem

One line each in the shared sheet: date, device and browser, page, what you did, what you expected, what happened,
a screenshot. Severity: **blocker** (cannot use it), **wrong** (shows something false), **rough** (works, but
confusing or ugly).
