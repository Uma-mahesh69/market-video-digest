# Market Video Digest

A daily email that tells you what the finance YouTube channels you follow said, so you don't have to watch them,
plus a chat page where you can ask questions about those videos.

Every morning it:

1. checks your channels for new videos,
2. reads each video's captions,
3. has Google Gemini pull out what matters: the main points, stocks and each channel's view on them, market
   levels quoted, predictions, risks and upcoming events,
4. emails you one digest, where every point links to the exact moment in the video where it was said.

It runs on your own Windows PC, uses only free services, and keeps your keys and data on your computer.

## Quick start (Windows)

You need: a **Gemini API key** (free, from https://aistudio.google.com/apikey) and, to receive emails, a **Gmail
address with an app password** (Google Account > Security > 2-Step Verification > App passwords).

1. Unzip `market-digest-setup.zip` (right-click > Extract All).
2. Double-click **`install.bat`**. If Windows says "Windows protected your PC", click **More info > Run anyway**.
3. Answer the questions. **Paste with a right-click**; Ctrl+V does not work in the hidden key prompts.
4. Say **yes** to the test digest at the end. It opens in your browser.

That's it. The digest arrives by email every day at the time you chose, and **Digest chat** is on your desktop.

## Everyday use

| I want to... | Do this |
|---|---|
| Read today's digest | Open the email. Or open the newest file in `%USERPROFILE%\market-digest\digests\`. |
| Ask about the videos | Double-click **Digest chat** on the desktop. Keep its black window open while you use it. |
| Get a digest right now | In PowerShell: `cd $env:USERPROFILE\market-digest` then `python digest.py --open` |
| Check everything works | `python digest.py --check` (in the same folder) |
| Change channels, email or time | Run `install.bat` again and answer `y` to "Enter them again?" |

## Documents

- **[USER_GUIDE.md](USER_GUIDE.md)**: installation, settings, daily use, updating and removing it.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**: what to do when something goes wrong.
- **ARCHITECTURE.md**: how it works inside, for developers. *(In the project's source folder, not in the setup zip.)*
- **PRESENTATION.md**: a 6-slide overview of the project. *(In the project's source folder, not in the setup zip.)*

## Good to know

- Captions are automatic and can mishear names and numbers. Unclear figures are marked "(check)", and every point
  links to its moment in the video so you can check it.
- The digest reports what each channel said. **It is not investment advice.**
- The PC must be on for the digest to run. If it was off at the scheduled time, it runs when the PC is next on and
  includes everything since the last digest.
- Web search in the chat needs a Gemini key with billing turned on. On the free key, the chat answers from your
  videos only and says so.
