"""New videos on the channels we follow, and Gemini's notes for each: read once, for every user.

YouTube refuses caption downloads from cloud servers ("sign in to confirm you're not a bot"; tested from a GitHub
runner on 16 Nov 2026), so the captions are not fetched at all: Gemini is given the video's link and watches it on
Google's side. The uploads list still comes from YouTube's public feed, which does answer cloud servers.
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from . import ROOT  # noqa: F401  (puts app/ on the path)
import digest as dg

NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "m": "http://search.yahoo.com/mrss/"}
MARKET_WORDS = re.compile(r"\b(stocks?|shares?|market|rally|sell-?off|earnings|price target|upgrade|downgrade|bull(ish)?|bear(ish)?|"
                          r"buy|sell|valuation|s&p|nasdaq|dow|fed|rates?|inflation|recession|ai|chips?|nvidia|apple|tesla|"
                          r"analyst|strategist|portfolio|investors?|outlook|forecast|guidance|revenue)\b", re.I)
NOT_MARKETS = re.compile(r"\b(live:|full episode|trailer|weather|sports?|recipe|celebrity|shorts?)\b", re.I)

VIDEO_SYSTEM = (dg.EXTRACT_SYSTEM
                .replace("You turn the transcript of one finance or markets video into a briefing",
                         "You watch one finance or markets video and turn it into a briefing")
                .replace("- Use only what the transcript says.", "- Use only what is said or shown in the video.")
                .replace('- Each transcript line starts with its time, like [12:34]. For every item, give "time" as the time of the line where it is said, copied exactly.',
                         '- For every item, give "time" as the moment in the video where it is said, as m:ss.')
                .replace("- Copy numbers as spoken. Captions are automatic and can mishear names and figures; if a figure is unclear, keep it and set \"unclear\": true.",
                         "- Copy numbers as spoken. Take speakers' names and firms from the on-screen captions when they are shown; "
                         "if a figure is unclear, keep it and set \"unclear\": true."))
assert "watch one finance" in VIDEO_SYSTEM and "moment in the video" in VIDEO_SYSTEM, "digest.EXTRACT_SYSTEM changed: update VIDEO_SYSTEM"


def feed(cid, text=None):
    """A channel's latest uploads from YouTube's public feed, with each video's description."""
    root = ET.fromstring(text if text is not None else dg.fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", "", NS)
        link = e.find("a:link", NS)
        if not re.fullmatch(r"[\w-]{11}", vid or ""):
            continue
        out.append({"id": vid, "title": e.findtext("a:title", "", NS), "channel": e.findtext("a:author/a:name", "", NS),
                    "published": e.findtext("a:published", "", NS), "url": f"https://www.youtube.com/watch?v={vid}",
                    "short": bool(link is not None and "/shorts/" in link.get("href", "")),
                    "description": (e.findtext("m:group/m:description", "", NS) or "")[:600]})
    return out


def rank(video, analysts):
    """How much a video is worth one of the day's few Gemini readings: a named analyst first, then talk of stocks."""
    text = f"{video['title']} {video.get('description', '')}"
    score = 0
    for name in analysts:
        last = name.split()[-1]
        if re.search(rf"\b{re.escape(name)}\b", text, re.I) or (len(last) > 4 and re.search(rf"\b{re.escape(last)}\b", video["title"], re.I)):
            score += 5
            break
    score += min(4, len(set(m.group(0).lower() for m in MARKET_WORDS.finditer(video["title"])))) * 1.5
    score += min(3, len(set(m.group(0).lower() for m in MARKET_WORDS.finditer(video.get("description", ""))))) * 0.5
    if NOT_MARKETS.search(video["title"]):
        score -= 4
    return score


def discover(sources, state, now, log=print, fetch_feed=feed):
    """The videos worth reading now, best first: new, not a Short, from the last lookback_hours, not seen before."""
    seen = set(state.get("seen") or [])
    ids = state.setdefault("channel_ids", {})
    cutoff = now - timedelta(hours=sources["limits"]["lookback_hours"])
    found = []
    for ch in sources["channels"]:
        try:
            ups = fetch_feed(dg.channel_id(ch["url"], {"channel_ids": ids}))
        except Exception as err:   # one channel down must not stop the others
            log(f"  {ch['name']}: could not list uploads ({type(err).__name__}: {str(err)[:120]})")
            continue
        for v in ups:
            when = parse_time(v["published"])
            if v["short"] or v["id"] in seen or not when or when < cutoff:
                continue
            v["channel"] = v["channel"] or ch["name"]
            v["rank"] = rank(v, sources["analysts"])
            if v["rank"] > 0:   # nothing in the title or description says markets: not worth one of the day's readings
                found.append(v)
    found.sort(key=lambda v: v["published"], reverse=True)   # newest first...
    found.sort(key=lambda v: -v["rank"])                      # ...within the same worth (the sort keeps that order)
    return found


def parse_time(text):
    try:
        d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def body_for(video, limits, plain=False):
    part = {"fileData": {"fileUri": video["url"]}}
    config = {"temperature": 0.2, "responseMimeType": "application/json"}
    if not plain:   # fewer frames and smaller frames: the talking is what matters, and it keeps a video inside the free quota
        part["videoMetadata"] = {"endOffset": f"{int(limits['max_video_minutes']) * 60}s", "fps": limits.get("video_fps", 0.2)}
        config["mediaResolution"] = "MEDIA_RESOLUTION_LOW"
    head = f"Video: {video['title']}\nChannel: {video['channel']}\nPublished: {video['published']}"
    return {"system_instruction": {"parts": [{"text": VIDEO_SYSTEM}]},
            "contents": [{"role": "user", "parts": [part, {"text": head}]}], "generationConfig": config}


def read(cfg, video, limits, call=None):
    """Gemini's notes for one video, in the same shape the rest of the code has always used.
    Raises dg.Skip for a video that can never be read (private, a live stream, removed)."""
    call = call or dg.call_gemini
    try:
        data = call(cfg, body_for(video, limits), timeout=300)
    except dg.GeminiError as err:
        if err.code != 400:
            raise
        try:   # the frame settings are the likeliest thing a model refuses: once more without them
            data = call(cfg, body_for(video, limits, plain=True), timeout=300)
        except dg.GeminiError as again:
            if again.code == 400:
                raise dg.Skip(f"Gemini cannot open this video: {str(again)[:160]}")
            raise
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", "".join(p.get("text", "") for p in parts).strip())
    try:
        notes = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("Gemini did not return valid JSON: " + raw[:200])
    if not isinstance(notes, dict):
        raise RuntimeError("Gemini returned a list where notes were expected")
    notes = dg.clean_notes(notes, 0)
    notes["_video"] = {k: video.get(k) for k in ("id", "title", "channel", "published", "url")}
    return notes


def read_new(cfg, sources, state, store, now, log=print, reader=read, pause=13):
    """Read as many of the waiting videos as today's allowance lets us. Returns the notes just made."""
    limits = sources["limits"]
    day = now.strftime("%Y-%m-%d")
    used = state.setdefault("videos_read", {})
    if used.get("day") != day:
        used.update(day=day, count=0)
    waiting = discover(sources, state, now, log)
    room = min(limits["videos_per_run"], limits["videos_per_day"] - used["count"])
    log(f"Videos: {len(waiting)} new, reading up to {max(room, 0)} ({used['count']} of {limits['videos_per_day']} read today)")
    made, seen = [], state.setdefault("seen", [])
    for video in waiting[:max(room, 0)]:
        try:
            notes = reader(cfg, video, limits)
        except dg.Skip as err:
            log(f"  skipped for good: {video['title'][:60]} ({err})")
            seen.append(video["id"])
            continue
        except Exception as err:   # quota, a model down: leave it unseen so the next run tries again
            log(f"  not read this time: {video['title'][:60]} ({type(err).__name__}: {str(err)[:140]})")
            if isinstance(err, dg.GeminiError) and err.code == 429:
                break   # out of quota: the rest would fail the same way
            continue
        used["count"] += 1
        seen.append(video["id"])
        store.set("videos", video["id"], {"published": video["published"], "channel": video["channel"], "title": video["title"],
                                          "notes": json.dumps(notes, ensure_ascii=False, separators=(",", ":"))})
        made.append(notes)
        log(f"  read: {video['channel']}: {video['title'][:70]} ({len(notes.get('stocks') or [])} stock calls)")
        if pause:
            time.sleep(pause)   # each free model takes 5 requests a minute
    del seen[:-800]   # the feeds only reach back 15 videos a channel
    return made


def as_pairs(notes_list):
    """[(video, notes)] newest first, the shape insights.py works on."""
    out = []
    for notes in notes_list:
        v = dict(notes.get("_video") or {})
        v["when"] = parse_time(v.get("published"))
        if v.get("id") and v["when"]:
            v.setdefault("url", f"https://www.youtube.com/watch?v={v['id']}")
            out.append((v, notes))
    return sorted(out, key=lambda vn: vn[0]["when"], reverse=True)
