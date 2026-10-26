# Market Video Digest: Presentation Outline

Six slides, about 10 minutes plus questions. Each slide has what goes on the slide and what to say.

---

## Slide 1: The problem

**On the slide**
- Market insight is spread across many YouTube channels and hours of video every day.
- Watching, or even searching, all of it is not practical for a busy executive.
- The need: **the trends, market levels, stocks and each channel's view, without watching the videos.**
- And a way to ask follow-up questions and compare channels.

**Say**
> "After the first demo you said a search tool was not enough. You wanted to catch up on what the finance channels
> are saying without watching or querying videos, every day, automatically. That is what I built."

---

## Slide 2: The solution

**On the slide**
- **A daily email digest**, made automatically from every new video on the channels you follow.
- **A chat page** to ask questions across the videos, with answers that link to the exact moment.
- **Runs on your own Windows PC.** Installed with one double-click. Your keys and data stay on your machine.
- **Costs nothing today:** it uses the free tier of Google Gemini.

**Say**
> "Each morning it checks the channels, reads every new video's captions, has Gemini pull out what matters, and
> emails one digest. Every point has a time stamp you can click to hear it said in the video, so nothing has to be
> taken on trust."

---

## Slide 3: Features

**On the slide**

| In the daily email | In the chat |
|---|---|
| Overview of what today's videos say | "Which stocks came up most this week?" |
| Themes, and where channels **disagree** | Compare channels, or ask about one video in depth |
| **Stocks:** bullish / bearish / neutral per channel, and why | Every claim cited, e.g. *TheStreet 12:34*, linked to the moment |
| Market levels and data quoted, upcoming events | Chats saved, so you can continue later |
| Video-by-video summary, predictions, risks | |
| Unclear figures marked **(check)** | |

Reliability: catches up after days the PC was off, waits for Wi-Fi, retries failed runs, and switches models when one
is busy.

**Say**
> "The stock table and the links are built by code from the notes, not written freely by the AI, so a citation always
> points to a real video and moment. It reports what each channel said. It is not investment advice."

---

## Slide 4: How it works

**On the slide**

```
 YouTube channels --> new videos (public feed) --> captions --> Gemini --> structured notes
                                                                              |
                                              daily email <-- digest <--------+
                                              chat page   <-- questions over the same notes
```

- Python standard library only; nothing extra to buy or maintain.
- Gemini models are tried in order: if one is busy or out of free quota, the next is used at once.
- Notes are saved per video, so nothing is paid for twice.
- Windows Task Scheduler runs it daily. The chat runs only on your PC.

**Say**
> "Speed was a real issue. Google's main model was often overloaded, and one run took over 20 minutes. I changed it
> to switch models instead of waiting and to summarise three videos at a time. Now 4 videos take about a minute and a
> half." (Full detail: ARCHITECTURE.md.)

---

## Slide 5: Live demonstration

**On the slide**
- 1. Today's digest email
- 2. Click a time stamp: the video opens at that moment
- 3. Ask the chat a question across this week's videos
- 4. (If asked) the one-click installer

**Demo script (about 4 minutes)**
1. **Open the email** "Market video digest, <date>". Walk through Overview, then Stocks mentioned. Point out a
   bullish/bearish view and its reason.
2. **Click a time** like [12:34] next to a stock. The video opens at that moment, which proves the point.
3. **Open Digest chat** from the desktop (start it before the meeting; keep its black window open). Choose
   **Last 7 days** and ask: *"Which AI stocks did the channels like this week, and why?"*. The answer takes about
   30 seconds. Click one citation.
4. **Optional:** show `install.bat`: one double-click, a few questions, done.

**Before the meeting:** run `python digest.py --open` in the install folder so a fresh digest exists, and open
Digest chat once to check it starts. Have a saved digest page (in the `digests` folder) ready in case the internet
fails.

---

## Slide 6: Next steps and decisions

**On the slide**

**Decisions needed from you**
1. **Your channel list.** Today it follows TheStreet only.
2. **Turn on Gemini billing?** It unlocks web search in the chat ("what's happening now") and removes the free-tier
   limit of 20 high-quality summaries a day per model. Expected to be small at this volume; to be confirmed against
   Google's pricing.
3. **Your feedback after a week:** is it deep enough? What's missing?

**Planned work**
- Terms-of-service and copyright check for using the channels' videos (required before adding many channels).
- Later, if useful: move it to an always-on server so it runs when your PC is off and the chat works from your phone.

**Say**
> "It works end to end today: installed, scheduled, emailing, and chat working. The three things that would make it
> most useful are your channel list, a decision on billing for web search, and your feedback after a few days of
> using it."

---

### Honest status (for questions)
- **Working and tested on a real PC:** install, daily schedule, email delivery, catch-up after missed days, chat with
  citations.
- **Not available yet:** web search in the chat (needs billing); channels other than TheStreet (needs your list).
- **Not yet judged:** digest depth and quality. That needs your feedback.
