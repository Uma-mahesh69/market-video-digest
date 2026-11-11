"""Market Digest for Claude: your saved videos, analyst calls and settings as tools in the Claude app.

Claude starts this file itself once you click "Connect to Claude" in Market Digest > Settings (it adds this file to
the Claude desktop app's list of local tools). It speaks the Model Context Protocol over standard input and output.
It runs on this computer and reads only the Market Digest folder. Keys and passwords are never returned.
What a tool returns is sent to Claude as part of your conversation, like anything else you tell it.
Standard library only.

To try it by hand:  python mcp_server.py --list     (prints the tools)
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import app
import chat
import digest as dg
from digest_export import load_tickers, resolve_ticker

NAME = "market-digest"
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MAX_CHARS = 60_000   # the most text one tool call returns

INSTRUCTIONS = """Market Digest runs on this person's own computer. Every day it reads new videos from the finance YouTube
channels they follow and saves notes on each one: summary, stock calls (who said what, bullish or bearish, and why),
market levels, predictions and risks. These tools read those saved notes.

How to use them well:
- Start with digest_overview to see what is followed, how many videos are saved and whether the daily run is working.
- For "what did X say" or "what is the view on a stock", use stock_calls or list_videos, then get_video for detail.
- Every item has a "link" that opens the video at the moment it was said. Cite those links.
- Report each view as that analyst's or channel's view, with the date. Captions are automatic and can mishear names
  and numbers, so flag figures that look wrong. Where analysts disagree, say who says what.
- This is information, not investment advice. Do not tell the person what to buy or sell.
- update_following changes what the daily digest covers. Say what you will change and get a yes before calling it.
- make_digest with preview false sends the email if one is set up. Only do that when asked."""


def text(value):
    return str(value or "").strip()


def moment(video, item):
    """A link to the moment an item was said, or to the video when its time is unknown."""
    s = item.get("seconds")
    return f"{video['url']}&t={int(s)}s" if isinstance(s, (int, float)) else video["url"]


def recent(days):
    lib = chat.library()
    if days:
        since = datetime.now(timezone.utc) - timedelta(days=int(days))
        lib = [vn for vn in lib if vn[0]["date"] and vn[0]["date"] >= since]
    return lib


def said_by(notes):
    return [s["name"] for s in dg.note_speakers(notes)]


def matches(needle, *hay):
    needle = text(needle).lower()
    return not needle or any(needle in text(h).lower() for h in hay)


def day_of(video):
    return video["date"].astimezone().strftime("%Y-%m-%d") if video["date"] else ""


# ---------------------------------------------------------------- the tools

def digest_overview():
    st = app.status()
    lib = chat.library()
    cfg = app.read_config()
    dates = [v["date"] for v, _ in lib if v["date"]]
    return {
        "set_up": st["configured"],
        "daily_run": {"on": st["schedule"]["on"], "time": st["schedule"]["time"], "next": st["schedule"]["next"]},
        "last_run": st["last_run"],
        "channels": cfg.get("channels") or [],
        "analysts_followed": cfg.get("analysts") or "none chosen: every video from the channels is included",
        "markets_only": st["markets_only"],
        "saved_videos": len(lib),
        "from": min(dates).strftime("%Y-%m-%d") if dates else None, "to": max(dates).strftime("%Y-%m-%d") if dates else None,
        "email": "on" if st["email_to"] else "off (digests are shown in the Market Digest app)",
        "version": app.version(),
    }


def list_videos(days=7, analyst="", channel=""):
    out = []
    for v, notes in recent(days):
        speakers = said_by(notes)
        if matches(channel, v.get("channel")) and matches(analyst, *speakers, *(text(s.get("analyst")) for s in notes.get("stocks") or [])):
            out.append({"video_id": v["id"], "date": day_of(v), "channel": v.get("channel"), "title": v.get("title"), "link": v["url"],
                        "speakers": speakers, "summary": notes.get("summary", ""),
                        "stocks": sorted({text(s.get("ticker") or s.get("name")) for s in notes.get("stocks") or []} - {""})})
    return {"videos": out, "count": len(out), "days": days}


def get_video(video_id):
    found = next(((v, n) for v, n in chat.library() if v["id"] == text(video_id)), None)
    if not found:
        raise ValueError(f"No saved video with the id {video_id!r}. list_videos shows the ids.")
    v, notes = found
    out = {"video_id": v["id"], "date": day_of(v), "channel": v.get("channel"), "title": v.get("title"), "link": v["url"],
           "speakers": dg.note_speakers(notes), "summary": notes.get("summary", "")}
    for key in ("key_points", "stocks", "market_levels", "sectors_and_themes", "predictions", "risks", "upcoming_events"):
        out[key] = [{**{k: val for k, val in item.items() if k not in ("seconds", "time") and val not in ("", None)}, "link": moment(v, item)}
                    for item in notes.get(key) or []]
    return out


def stock_calls(ticker="", days=14, analyst=""):
    tickers = load_tickers()
    want = text(ticker).upper()
    calls, table = [], {}
    for v, notes in recent(days):
        speakers = said_by(notes)
        for s in notes.get("stocks") or []:
            said = text(s.get("ticker"))
            symbol = resolve_ticker(text(s.get("name")) or said, said, tickers) or (said or text(s.get("name"))).upper()
            who = text(s.get("analyst")) or (speakers[0] if len(speakers) == 1 else "")
            if not symbol or not matches(analyst, who, *speakers):
                continue
            row = table.setdefault(symbol, {"ticker": symbol, "name": text(s.get("name")), "bullish": 0, "bearish": 0, "neutral": 0, "mixed": 0})
            row[s.get("view") if s.get("view") in row else "mixed"] += 1
            if want and want in (symbol, text(s.get("name")).upper()):
                calls.append({"date": day_of(v), "ticker": symbol, "view": s.get("view"), "reason": s.get("reason"), "analyst": who or None,
                              "channel": v.get("channel"), "video": v.get("title"), "link": moment(v, s)})
    if want:
        return {"ticker": want, "days": days, "calls": calls, "count": len(calls),
                "note": None if calls else "No calls on this stock in that period. Call stock_calls with no ticker to see which stocks came up."}
    rows = sorted(table.values(), key=lambda r: -(r["bullish"] + r["bearish"] + r["neutral"] + r["mixed"]))
    return {"days": days, "stocks": rows[:60], "count": len(rows), "note": "Counts of calls per stock. Give a ticker for each call with its reason and link."}


def search_captions(query, limit=10):
    words = chat.keywords(text(query))
    if not words:
        raise ValueError("Give a few words to search for.")
    videos = {v["id"]: v for v, _ in chat.library()}
    hits = dg.ytmd("search", *words, "--match", "any", "-n", str(max(1, min(int(limit), 30)) * 3))
    out = []
    for h in hits if isinstance(hits, list) else []:
        v = videos.get(h.get("video_id"))
        if v and len(out) < int(limit):
            out.append({"date": day_of(v), "channel": v.get("channel"), "video": v.get("title"), "said": h.get("text"),
                        "link": f"{v['url']}&t={int(h.get('start') or 0)}s"})
    return {"query": query, "passages": out, "count": len(out)}


def daily_digest(date=""):
    folder = app.json_folder(app.read_config())
    files = sorted(folder.glob("video-digest_*.json")) if folder.exists() else []
    if not files:
        raise ValueError("No daily digest file yet. One is saved after each daily run.")
    wanted = [f for f in files if text(date) in f.name] if text(date) else files
    if not wanted:
        raise ValueError(f"No digest for {date}. Days saved: {', '.join(f.stem.split('_')[1] for f in files[-14:])}")
    f = wanted[-1]
    day = f.stem.split("_", 1)[1]
    doc = json.loads(f.read_text(encoding="utf-8"))
    out = {"date": day, "digest": {k: doc.get(k) for k in ("summary", "video_count", "channels", "themes", "debates", "levels", "upcoming") if k in doc},
           "videos": [{"title": v.get("title"), "channel": v.get("channel"), "url": v.get("url")} for v in doc.get("videos", [])],
           "other_days": [x.stem.split("_", 1)[1] for x in files[-14:]]}
    for kind in ("market-data", "tipranks"):
        extra = folder / f"{kind}_{day}.json"
        if extra.exists():
            try:
                data = json.loads(extra.read_text(encoding="utf-8"))
                data.pop("raw", None)   # TipRanks' full answer is large; "rows" holds what matters
                out[kind.replace("-", "_")] = data
            except ValueError:
                pass
    return out


def update_following(add_channels=(), remove_channels=(), add_analysts=(), remove_analysts=()):
    saved = app.read_config()
    if not app.real(saved.get("gemini_api_key")):
        raise ValueError("Market Digest is not set up yet. Open Market Digest on the desktop and finish the setup first.")
    drop = lambda items, gone: [x for x in items if x.strip().lower() not in {g.strip().lower() for g in gone}]
    channels = list(dict.fromkeys(drop(saved.get("channels") or [], remove_channels) + [text(c) for c in add_channels if text(c)]))
    analysts = list(dict.fromkeys(drop(saved.get("analysts") or [], remove_analysts) + [text(a) for a in add_analysts if text(a)]))
    cfg, errors = app.merged({"channels": channels, "analysts": analysts}, saved)
    if errors:
        raise ValueError("Nothing was changed: " + " ".join(errors.values()))
    app.write_config(cfg)
    return {"channels": cfg["channels"], "analysts_followed": cfg["analysts"] or "none: every video is included",
            "note": "Saved. The next daily digest uses this."}


def make_digest(preview=True):
    if not app.real(app.read_config().get("gemini_api_key")):
        raise ValueError("Market Digest is not set up yet. Open Market Digest on the desktop and finish the setup first.")
    args = ["--hours", "72", "--dry-run"] if preview else []
    log = dg.HERE / ("preview.log" if preview else "digest.log")
    with open(log, "a" if not preview else "w", encoding="utf-8") as out:
        subprocess.Popen([app.console_python(), "-u", str(dg.HERE / "digest.py"), *args], cwd=dg.HERE, env=app.child_env(),
                         stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                         creationflags=0x08000000 if os.name == "nt" else 0, start_new_session=os.name != "nt")
    return {"started": True, "kind": "a preview of the last 3 days (not emailed)" if preview else "today's digest",
            "note": "It takes a few minutes. Call digest_overview and read last_run to see when it has finished."}


def tool(fn, description, props=None, required=()):
    return {"fn": fn, "spec": {"name": fn.__name__, "description": description,
                               "inputSchema": {"type": "object", "properties": props or {}, "required": list(required)}}}


DAYS = {"type": "integer", "description": "How many days back to look. 0 means every saved video.", "minimum": 0}
NAMES = {"type": "array", "items": {"type": "string"}}
TOOLS = {t["spec"]["name"]: t for t in [
    tool(digest_overview, "What Market Digest follows (channels, analysts), how many videos are saved and from when, and whether the daily run is on and worked last time. Call this first."),
    tool(list_videos, "The saved videos, newest first, each with its summary, speakers and the stocks discussed. Filter by analyst or channel name.",
         {"days": {**DAYS, "default": 7}, "analyst": {"type": "string", "description": "Part of a speaker's name, e.g. Ives"},
          "channel": {"type": "string", "description": "Part of a channel's name"}}),
    tool(get_video, "Everything noted from one video: key points, stock calls with reasons, market levels, predictions, risks. Each item links to its moment in the video.",
         {"video_id": {"type": "string", "description": "The video_id from list_videos"}}, ["video_id"]),
    tool(stock_calls, "Analyst calls on stocks. With a ticker: every call on it (bullish, bearish, neutral or mixed), who made it, why, and a link to the moment. Without one: how many calls each stock got.",
         {"ticker": {"type": "string", "description": "A ticker like NVDA, or a company name. Leave empty for the table of all stocks."},
          "days": {**DAYS, "default": 14}, "analyst": {"type": "string", "description": "Only calls by this person"}}),
    tool(search_captions, "Search the words spoken in the saved videos, for topics the notes may not list (e.g. tariffs, a product name). Returns passages with links.",
         {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 30}}, ["query"]),
    tool(daily_digest, "One day's digest as data: the overview, themes, where analysts disagree, and, if set up, the watchlist's prices and Wall Street's consensus from TipRanks. The latest day unless a date is given.",
         {"date": {"type": "string", "description": "YYYY-MM-DD. Empty for the latest."}}),
    tool(update_following, "Change which YouTube channels and which analysts the daily digest covers. Confirm the change with the person first.",
         {"add_channels": {**NAMES, "description": "Channel links or @handles to add"}, "remove_channels": NAMES,
          "add_analysts": {**NAMES, "description": "Full names, e.g. Dan Ives. Other spellings after a slash: Tom Lee / Thomas Lee"}, "remove_analysts": NAMES}),
    tool(make_digest, "Start making a digest now. preview true (the default) covers the last 3 days and is not emailed. preview false is the real daily digest and is emailed if email is set up.",
         {"preview": {"type": "boolean", "default": True}}),
]}

PROMPTS = {
    "morning-briefing": ("A briefing on the latest videos", [],
                         "Use the Market Digest tools to brief me on the newest videos (the last 2 days). Start with digest_overview. Give me: the "
                         "overall mood, the 5 stocks with the most calls and which way they lean, where the analysts I follow disagree, and anything "
                         "coming up this week. Link each point to its moment in the video. Keep it to one screen."),
    "stock-view": ("What the analysts say about one stock", [{"name": "ticker", "description": "A ticker, e.g. NVDA", "required": True}],
                   "Use stock_calls for {ticker} over the last 30 days, and get_video where a call needs context. Lay out the bullish case and the bearish "
                   "case, who makes each and when, with links. If daily_digest has TipRanks data for it, add Wall Street's consensus and price target. "
                   "No recommendation."),
    "weekly-dashboard": ("A one-page dashboard of the week", [],
                         "Build me a one-page dashboard of this week from the Market Digest tools: stock_calls (7 days) as a table of the most-called "
                         "stocks with bullish and bearish counts, list_videos (7 days) for who spoke, and daily_digest for themes and disagreements. "
                         "Make it an interactive page I can keep open, with every row linking to the video moment."),
}


# ---------------------------------------------------------------- the protocol (JSON-RPC 2.0, one message per line)

def call_tool(name, arguments):
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"There is no tool called {name}."}], "isError": True}
    try:
        result = TOOLS[name]["fn"](**(arguments or {}))
        body = json.dumps(result, ensure_ascii=False, indent=1, default=str)
        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS] + "\n... (cut short: ask for fewer days or one ticker)"
        return {"content": [{"type": "text", "text": body}], "isError": False}
    except (ValueError, TypeError) as err:
        return {"content": [{"type": "text", "text": str(err)}], "isError": True}
    except Exception as err:
        return {"content": [{"type": "text", "text": f"Market Digest could not do that: {err.__class__.__name__}: {err}"}], "isError": True}


def handle(msg):
    """The reply to one message, or None for a notification."""
    method, params, mid = msg.get("method"), msg.get("params") or {}, msg.get("id")
    if mid is None:
        return None
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok({"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[1],
                   "capabilities": {"tools": {}, "prompts": {}},
                   "serverInfo": {"name": NAME, "title": "Market Digest", "version": app.version()}, "instructions": INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [t["spec"] for t in TOOLS.values()]})
    if method == "tools/call":
        return ok(call_tool(params.get("name"), params.get("arguments")))
    if method == "prompts/list":
        return ok({"prompts": [{"name": n, "description": d, "arguments": a} for n, (d, a, _) in PROMPTS.items()]})
    if method == "prompts/get":
        if params.get("name") not in PROMPTS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "Unknown prompt"}}
        d, _, body = PROMPTS[params["name"]]
        filled = re.sub(r"\{(\w+)\}", lambda m: text((params.get("arguments") or {}).get(m.group(1))) or m.group(0), body)
        return ok({"description": d, "messages": [{"role": "user", "content": {"type": "text", "text": filled}}]})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    out = sys.stdout.buffer   # the protocol owns standard output; anything else printed goes to standard error
    sys.stdout = sys.stderr
    os.environ["PATH"] = str(dg.HERE / "bin") + os.pathsep + os.environ.get("PATH", "")
    dg.log = lambda msg: print(msg, file=sys.stderr, flush=True)
    if "--list" in sys.argv:
        for t in TOOLS.values():
            print(f"{t['spec']['name']}: {t['spec']['description']}", file=sys.stderr)
        return
    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(msg) if isinstance(msg, dict) else {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            out.flush()


if __name__ == "__main__":
    main()
