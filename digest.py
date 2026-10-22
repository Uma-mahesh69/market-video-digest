"""Daily market video digest.

Every run: check the channels you follow for new uploads, read each new video's captions,
have Gemini pull out what matters (levels, stocks, the channel's view, predictions, risks),
then email one digest with a link to the exact moment for every point.

Setup: put this file next to the `ytmd` script, copy digest_config.example.json to
digest_config.json and fill it in. Then:
    python digest.py --hours 72 --dry-run      first test: no email, writes and opens the digest
    python digest.py                          normal daily run
    python digest.py --video <youtube url>    test one video
Standard library only.
"""
import argparse
import html
import json
import os
import re
import smtplib
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
YTMD = HERE / "ytmd"
CONFIG = HERE / "digest_config.json"
STATE = HERE / "digest_state.json"
OUT_DIR = HERE / "digests"
CACHE_DIR = HERE / "digest_cache"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MAX_TRANSCRIPT_CHARS = 150_000
# Tried in this order. On the free tier the Flash models allow 20 requests a day each and the Flash Lite ones 500.
DEFAULT_MODELS = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
WORKERS = 3   # videos summarised at the same time; each model allows 5 requests a minute


class Skip(Exception):
    """A video that can never be processed (for example, no captions). It is not retried."""


# ---------------------------------------------------------------- settings and memory

def load_config():
    if not CONFIG.exists():
        sys.exit(f"Missing {CONFIG.name}. Copy digest_config.example.json to {CONFIG.name} and fill it in.")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["gemini_api_key"] = os.environ.get("GEMINI_API_KEY") or cfg.get("gemini_api_key", "")
    chosen = cfg.get("models") or [cfg.get("model"), cfg.get("fallback_model")]
    cfg["models"] = list(dict.fromkeys(m for m in [*chosen, *DEFAULT_MODELS] if m))
    cfg.setdefault("lookback_hours", 26)
    cfg.setdefault("max_videos", 20)
    cfg.setdefault("smtp_host", "smtp.gmail.com")
    cfg.setdefault("smtp_port", 465)
    if not cfg["gemini_api_key"] or "PASTE" in cfg["gemini_api_key"]:
        sys.exit("Add your Gemini API key to digest_config.json (gemini_api_key).")
    return cfg


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"channel_ids": {}, "done": {}}


def save_state(state):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def log(msg):
    print(datetime.now().strftime("%H:%M:%S"), msg, flush=True)


def wait_for_internet(minutes=15):
    """A run that starts as the PC wakes can come before Wi-Fi connects, and would then find and send nothing."""
    deadline = time.time() + minutes * 60
    while True:
        try:
            socket.create_connection(("www.youtube.com", 443), timeout=10).close()
            return True
        except OSError:
            if time.time() > deadline:
                return False
            log("No internet yet; checking again in 30s")
            time.sleep(30)


# ---------------------------------------------------------------- 1. find new videos

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def channel_id(url, state):
    """Turn a channel link or @handle into its UC... id, once, and remember it."""
    url = url.strip()
    if url.startswith("@"):
        url = "https://www.youtube.com/" + url
    url = re.sub(r"^(https?://)?(m\.|music\.)?youtube\.com", "https://www.youtube.com", url)
    m = re.search(r"/channel/(UC[\w-]{22})", url)
    if m:
        return m.group(1)
    if url in state["channel_ids"]:
        return state["channel_ids"][url]
    page = fetch(url)
    for pat in (r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"',
                r'"externalId":"(UC[\w-]{22})"', r'"channelId":"(UC[\w-]{22})"'):
        m = re.search(pat, page)
        if m:
            state["channel_ids"][url] = m.group(1)
            return m.group(1)
    raise RuntimeError(f"could not find the channel id on {url}")


def latest_uploads(cid):
    """YouTube's public feed of a channel's latest uploads. No API key needed."""
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    root = ET.fromstring(fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
    out = []
    for e in root.findall("a:entry", ns):
        vid = e.findtext("yt:videoId", "", ns)
        link = e.find("a:link", ns)
        out.append({
            "id": vid,
            "title": e.findtext("a:title", "", ns),
            "channel": e.findtext("a:author/a:name", "", ns),
            "published": e.findtext("a:published", "", ns),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "short": bool(link is not None and "/shorts/" in link.get("href", "")),
        })
    return out


# ---------------------------------------------------------------- 2. read the captions

PERMANENT = {"captions_unavailable", "video_unavailable", "language_mismatch", "invalid_video"}


def ytmd(*args):
    # PYTHONUTF8: on Windows ytmd would otherwise print in the local code page, and titles with ’ break the reading.
    run = subprocess.run([sys.executable, str(YTMD), *args, "--json"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env={**os.environ, "PYTHONUTF8": "1"})
    if run.returncode == 0:
        return json.loads(run.stdout or "{}")
    # ytmd reports errors as {"error": {"code": ..., "message": ...}} on stderr (or per item on stdout for add)
    err = {}
    for stream in (run.stderr, run.stdout):
        try:
            data = json.loads(stream or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            err = data.get("error") or next((r.get("error") for r in data.get("results", []) if isinstance(r, dict) and r.get("error")), None) or err
        if err:
            break
    message = err.get("message") or (run.stderr or run.stdout).strip()[:300]
    if err.get("code") in PERMANENT:
        raise Skip(message)
    raise RuntimeError(f"{err.get('code', 'error')}: {message}")


def transcript(video):
    """Captions as lines that start with their time, e.g. "[12:34] text", so every point can be linked."""
    meta = ytmd("add", video["url"])   # raises Skip when the video has no captions
    lines, cursor = [], None
    while True:
        page = ytmd("read", video["id"], "--cursor", cursor) if cursor else ytmd("read", video["id"], "--max-chars", "100000")
        for p in page.get("passages", []):
            lines.append(f"[{clock(p['start'])}] {p['text']}")
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            break
    text = "\n".join(lines)
    if len(text) < 200:
        raise Skip("captions too short to summarise")
    video["duration"] = meta.get("duration_s") or 0
    video["captions"] = meta.get("captions", "")
    video["truncated"] = len(text) > MAX_TRANSCRIPT_CHARS
    return text[:MAX_TRANSCRIPT_CHARS]


def clock(s):
    s = int(s or 0)
    h, m, x = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


def seconds(t):
    """'12:34' or '1:02:03' to seconds; None when it is not a time."""
    if not isinstance(t, str) or not re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", t.strip()):
        return None
    total = 0
    for part in t.strip().split(":"):
        total = total * 60 + int(part)
    return total


# ---------------------------------------------------------------- 3. ask Gemini

class GeminiError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"Gemini error {code}: {message}" if code else f"Gemini did not answer: {message}")
        self.code = code


REST_SECONDS = 600
_resting = {}   # (model, uses tools) -> when it last failed
_resting_lock = threading.Lock()


def call_gemini(cfg, body, models=None, patient=True):
    """Send one request to the first model in the list that is up.
    A busy, out-of-quota or silent model is skipped for 10 minutes and the next one is tried at once,
    so a bad model costs one failed call per run instead of minutes of retries per video.
    If every model fails and patient is True, wait 20 seconds and try them all once more."""
    models = models or cfg["models"]
    tools = bool(body.get("tools"))
    last = None
    for round_ in (1, 2) if patient else (1,):
        with _resting_lock:
            now = time.time()
            ready = [m for m in models if round_ == 2 or now - _resting.get((m, tools), 0) > REST_SECONDS]
        for model in ready:
            req = urllib.request.Request(API_URL.format(model=model), data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "x-goog-api-key": cfg["gemini_api_key"]})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.load(r)
            except urllib.error.HTTPError as err:
                last = GeminiError(err.code, err.read().decode("utf-8", "replace")[:300])
                if err.code in (400, 401, 403):   # a bad request or a bad key fails the same way on every model
                    raise last
            except (TimeoutError, ConnectionError, urllib.error.URLError, OSError) as err:
                last = GeminiError(None, f"{err.__class__.__name__} {err}")
            log(f"  {model}: {'error ' + str(last.code) if last.code else 'no answer'}, switching to the next model")
            with _resting_lock:
                _resting[(model, tools)] = time.time()
        if round_ == 1 and patient:
            log("  no model answered; waiting 20s and trying them all once more")
            time.sleep(20)
    raise last or GeminiError(None, "no model to try")


def gemini(cfg, system, prompt):
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    data = call_gemini(cfg, body)
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    raw = "".join(p.get("text", "") for p in parts).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("Gemini did not return valid JSON: " + raw[:200])


EXTRACT_SYSTEM = """You turn the transcript of one finance or markets video into a briefing for a busy professional who will not watch it.

Rules:
- Use only what the transcript says. Do not add facts, prices or opinions from your own knowledge.
- Each transcript line starts with its time, like [12:34]. For every item, give "time" as the time of the line where it is said, copied exactly.
- Copy numbers as spoken. Captions are automatic and can mishear names and figures; if a figure is unclear, keep it and set "unclear": true.
- Report the channel's or speaker's view, not yours. Views are one of: bullish, bearish, neutral, mixed.
- Leave a list empty when the video does not cover it. Never invent items to fill a list.

Return one JSON object with exactly these keys:
{
 "summary": "3 to 5 sentences: what the video argues and why it matters",
 "speakers": ["names and roles if stated"],
 "key_points": [{"point": "...", "time": "m:ss"}],
 "market_levels": [{"item": "index, yield, rate, commodity, currency or data release", "value": "as said", "context": "what was said about it", "time": "m:ss", "unclear": false}],
 "stocks": [{"name": "company name", "ticker": "if said, else empty", "view": "bullish|bearish|neutral|mixed", "reason": "the channel's reason, one sentence", "time": "m:ss"}],
 "sectors_and_themes": [{"name": "...", "view": "bullish|bearish|neutral|mixed", "reason": "...", "time": "m:ss"}],
 "predictions": [{"claim": "what they expect", "horizon": "timeframe if said", "time": "m:ss"}],
 "risks": [{"risk": "...", "time": "m:ss"}],
 "upcoming_events": [{"event": "earnings, data release, meeting", "when": "as said", "time": "m:ss"}]
}"""

DAY_SYSTEM = """You write the opening of a daily digest of finance videos for a busy professional.
You receive structured notes from each video, numbered. Use only these notes.
Return one JSON object:
{
 "overview": "4 to 6 sentences: what today's videos say about the markets, naming channels",
 "themes": [{"theme": "short title", "detail": "2 to 3 sentences", "videos": [video numbers]}],
 "disagreements": [{"topic": "...", "detail": "who says what", "videos": [video numbers]}]
}
Give at most 5 themes. Leave "disagreements" empty if the videos do not disagree."""


def extract(cfg, video, text):
    cached = CACHE_DIR / f"{video['id']}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    head = f"Video: {video['title']}\nChannel: {video['channel']}\nPublished: {video['published']}\n\nTranscript:\n"
    notes = gemini(cfg, EXTRACT_SYSTEM, head + text)
    notes = clean_notes(notes, video.get("duration") or 0)
    notes["_video"] = {k: video.get(k) for k in ("id", "title", "channel", "published", "url", "duration")}
    CACHE_DIR.mkdir(exist_ok=True)
    cached.write_text(json.dumps(notes, indent=1, ensure_ascii=False), encoding="utf-8")
    return notes


LISTS = ("key_points", "market_levels", "stocks", "sectors_and_themes", "predictions", "risks", "upcoming_events")
VIEWS = {"bullish", "bearish", "neutral", "mixed"}


def clean_notes(n, duration):
    """Keep only well-formed items, and only times that exist in the video."""
    out = {"summary": str(n.get("summary", "")).strip(), "speakers": [str(s) for s in n.get("speakers", []) if s]}
    for key in LISTS:
        items = []
        for it in n.get(key, []) or []:
            if not isinstance(it, dict):
                continue
            s = seconds(it.get("time"))
            it["seconds"] = s if s is not None and (not duration or s <= duration + 5) else None
            if "view" in it:
                it["view"] = it["view"] if it["view"] in VIEWS else "mixed"
            items.append(it)
        out[key] = items
    return out


def day_summary(cfg, done):
    brief = [{"n": i + 1, "channel": d["video"]["channel"], "title": d["video"]["title"], "summary": d["notes"]["summary"],
              "stocks": [{k: s.get(k) for k in ("name", "view", "reason")} for s in d["notes"]["stocks"]],
              "sectors": [{k: s.get(k) for k in ("name", "view")} for s in d["notes"]["sectors_and_themes"]],
              "predictions": [p.get("claim") for p in d["notes"]["predictions"]]} for i, d in enumerate(done)]
    try:
        s = gemini(cfg, DAY_SYSTEM, json.dumps(brief, ensure_ascii=False))
    except RuntimeError as err:
        log(f"  overview failed: {err}")
        return {"overview": "", "themes": [], "disagreements": []}
    valid = lambda nums: [x for x in nums if isinstance(x, int) and 1 <= x <= len(done)] if isinstance(nums, list) else []
    for key in ("themes", "disagreements"):
        s[key] = [dict(t, videos=valid(t.get("videos"))) for t in s.get(key, []) if isinstance(t, dict)]
    return s


# ---------------------------------------------------------------- 4. build and send the digest

C = {"ink": "#16202E", "muted": "#5C6878", "line": "#DCE2EA", "soft": "#F4F6F9", "blue": "#2447C5",
     "bullish": "#1A7F37", "bearish": "#B42318", "neutral": "#5C6878", "mixed": "#9A6700"}
e = html.escape


def at(video, s):
    return f"{video['url']}&t={s}s" if s is not None else video["url"]


def tlink(video, item):
    s = item.get("seconds")
    if s is None:
        return ""
    return f' <a href="{at(video, s)}" style="color:{C["blue"]};text-decoration:none;white-space:nowrap">[{clock(s)}]</a>'


def view_tag(view):
    return f'<span style="color:{C[view]};font-weight:600">{e(view)}</span>'


def section(title, body):
    return (f'<h2 style="font:600 18px/1.3 Georgia,serif;color:{C["ink"]};margin:28px 0 10px;padding-top:14px;'
            f'border-top:2px solid {C["ink"]}">{e(title)}</h2>{body}')


def table(head, rows):
    th = "".join(f'<th style="text-align:left;padding:6px 8px;border-bottom:1px solid {C["line"]};font-size:12px;color:{C["muted"]}">{h}</th>' for h in head)
    tr = "".join("<tr>" + "".join(f'<td style="padding:6px 8px;border-bottom:1px solid {C["line"]};vertical-align:top">{c}</td>' for c in r) + "</tr>" for r in rows)
    return f'<table style="border-collapse:collapse;width:100%;font-size:14px">{th and "<tr>" + th + "</tr>"}{tr}</table>'


def bullets(items):
    return '<ul style="margin:6px 0 0;padding-left:20px">' + "".join(f'<li style="margin:3px 0">{i}</li>' for i in items) + "</ul>"


def render(day, done, skipped, overview, unchecked=()):
    vref = lambda nums: " ".join(f'<a href="#v{n}" style="color:{C["blue"]}">#{n}</a>' for n in nums)
    parts = [f'<p style="margin:0;color:{C["muted"]};font-size:13px">{day:%A, %d %B %Y}. '
             f'{len(done)} new video{"s" if len(done) != 1 else ""} from {len({d["video"]["channel"] for d in done})} channel(s).</p>',
             f'<h1 style="font:600 26px/1.25 Georgia,serif;color:{C["ink"]};margin:6px 0 14px">Market video digest</h1>']
    if unchecked:
        parts.append(f'<p style="padding:10px 12px;background:#FFF4D6;border-left:4px solid #9A6700">Could not check {len(unchecked)} channel{"s" if len(unchecked) != 1 else ""}, '
                     'so this digest may be missing videos: ' + "; ".join(f"{e(ch)} ({e(why[:120])})" for ch, why in unchecked) + '.</p>')
    if not done and not unchecked:
        parts.append("<p>No new videos with captions since the last digest.</p>")
    if overview.get("overview"):
        parts.append(f'<p style="font-size:16px;line-height:1.6">{e(overview["overview"])}</p>')
    if overview.get("themes"):
        parts.append(section("Themes today", "".join(
            f'<p style="margin:0 0 10px"><b>{e(t.get("theme", ""))}</b>. {e(t.get("detail", ""))} {vref(t["videos"])}</p>' for t in overview["themes"])))
    if overview.get("disagreements"):
        parts.append(section("Where channels disagree", "".join(
            f'<p style="margin:0 0 10px"><b>{e(t.get("topic", ""))}</b>. {e(t.get("detail", ""))} {vref(t["videos"])}</p>' for t in overview["disagreements"])))

    # Stocks across all videos, grouped by name. Built from the notes, not written by the model.
    stocks = {}
    for n, d in enumerate(done, 1):
        for s in d["notes"]["stocks"]:
            key = (s.get("ticker") or s.get("name") or "").strip().upper()
            if key:
                stocks.setdefault(key, []).append((n, d, s))
    if stocks:
        rows = []
        for key, hits in sorted(stocks.items(), key=lambda kv: -len(kv[1])):
            name = hits[0][2].get("name") or key
            tick = hits[0][2].get("ticker")
            rows.append([f'<b>{e(name)}</b>' + (f'<br><span style="color:{C["muted"]};font-size:12px">{e(tick)}</span>' if tick and tick.upper() != name.upper() else ""),
                         "<br>".join(f'{view_tag(s["view"])} <span style="color:{C["muted"]}">{e(d["video"]["channel"])}</span>' for n, d, s in hits),
                         "<br>".join(f'{e(s.get("reason", ""))}{tlink(d["video"], s)}' for n, d, s in hits)])
        parts.append(section("Stocks mentioned", table(["Stock", "View", "Why"], rows)))

    levels = [(d, l) for d in done for l in d["notes"]["market_levels"]]
    if levels:
        parts.append(section("Market levels and data quoted", table(["What", "Level", "Said about it", "Source"], [
            [e(l.get("item", "")), e(str(l.get("value", ""))) + (' <span title="may be misheard" style="color:#9A6700">(check)</span>' if l.get("unclear") else ""),
             e(l.get("context", "")), f'{e(d["video"]["channel"])}{tlink(d["video"], l)}'] for d, l in levels])))

    events = [(d, x) for d in done for x in d["notes"]["upcoming_events"]]
    if events:
        parts.append(section("Coming up", bullets([f'{e(x.get("event", ""))}, {e(x.get("when", ""))} ({e(d["video"]["channel"])}){tlink(d["video"], x)}' for d, x in events])))

    cards = []
    for n, d in enumerate(done, 1):
        v, nt = d["video"], d["notes"]
        meta = [e(v["channel"]), e(v["published"][:10])]
        if v.get("duration"):
            meta.append(clock(v["duration"]))
        if v.get("captions") == "auto":
            meta.append("auto captions")
        body = [f'<p id="v{n}" style="margin:0 0 2px;color:{C["muted"]};font-size:12px">#{n}. {", ".join(meta)}</p>',
                f'<p style="margin:0 0 6px;font-weight:600;font-size:16px"><a href="{v["url"]}" style="color:{C["ink"]}">{e(v["title"])}</a></p>',
                f'<p style="margin:0">{e(nt["summary"])}</p>']
        if nt["speakers"]:
            body.append(f'<p style="margin:6px 0 0;color:{C["muted"]};font-size:13px">Speaking: {e(", ".join(nt["speakers"]))}</p>')
        groups = [("Key points", [f'{e(p.get("point", ""))}{tlink(v, p)}' for p in nt["key_points"]]),
                  ("Sectors and themes", [f'{e(s.get("name", ""))}: {view_tag(s["view"])}. {e(s.get("reason", ""))}{tlink(v, s)}' for s in nt["sectors_and_themes"]]),
                  ("What they expect", [f'{e(p.get("claim", ""))}' + (f' ({e(p["horizon"])})' if p.get("horizon") else "") + tlink(v, p) for p in nt["predictions"]]),
                  ("Risks they flag", [f'{e(r.get("risk", ""))}{tlink(v, r)}' for r in nt["risks"]])]
        for label, items in groups:
            if items:
                body.append(f'<p style="margin:12px 0 0;font-size:13px;font-weight:600;color:{C["muted"]}">{label}</p>' + bullets(items))
        if v.get("truncated"):
            body.append(f'<p style="margin:8px 0 0;font-size:12px;color:{C["muted"]}">Very long video: only the first part was read.</p>')
        body.append(f'<!--ASK:{v["id"]}-->')   # becomes an "Ask about this video" link in the copy saved on this laptop
        cards.append(f'<div style="padding:16px 0;border-bottom:1px solid {C["line"]}">{"".join(body)}</div>')
    if cards:
        parts.append(section("Video by video", "".join(cards)))
    if skipped:
        parts.append(section("Not included", bullets([f'<a href="{v["url"]}" style="color:{C["blue"]}">{e(v["title"])}</a> ({e(v["channel"])}): {e(why)}' for v, why in skipped])))
    parts.append(f'<p style="margin:28px 0 0;font-size:12px;color:{C["muted"]};line-height:1.5">Written automatically by Gemini from the videos\' captions. '
                 'Captions can mishear names and figures, so open the linked moment before relying on a number. '
                 'This reports what each channel said. It is not investment advice.</p>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Market video digest {day:%d %b %Y}</title></head>'
            f'<body style="margin:0;background:{C["soft"]}"><div style="max-width:720px;margin:0 auto;padding:24px 20px;background:#fff;'
            f'font:15px/1.55 -apple-system,\'Segoe UI\',Roboto,Arial,sans-serif;color:{C["ink"]}">{"".join(parts)}</div></body></html>')


def plain_text(done, skipped, overview):
    lines = [overview.get("overview", ""), ""]
    for n, d in enumerate(done, 1):
        lines += [f'#{n} {d["video"]["title"]} ({d["video"]["channel"]})', d["video"]["url"], d["notes"]["summary"], ""]
    lines += [f'Not included: {v["title"]} ({why})' for v, why in skipped]
    return "\n".join(lines)


def send(cfg, subject, html_body, text_body):
    to = cfg.get("email_to") or []
    if isinstance(to, str):
        to = [to]
    if not (to and cfg.get("smtp_user") and cfg.get("smtp_password")):
        log("Email not set up in digest_config.json, so the digest was only saved to a file.")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg["smtp_user"], ", ".join(to)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP_SSL(cfg["smtp_host"], int(cfg["smtp_port"]), context=ssl.create_default_context(), timeout=60) as s:
        s.login(cfg["smtp_user"], cfg["smtp_password"])
        s.send_message(msg)
    return True


def check(cfg, state):
    """Test every channel (link, channel id, uploads feed), the Gemini key and the email login. True if all pass."""
    ok = bool(cfg.get("channels"))
    if not ok:
        print("No channels in digest_config.json.")
    for ch in cfg.get("channels", []):
        print(f"\n{ch}")
        try:
            cid = channel_id(ch, state)
            print(f"  channel id:  {cid}")
        except Exception as err:
            print(f"  FAILED to find the channel id: {err}")
            ok = False
            continue
        try:
            ups = latest_uploads(cid)
        except Exception as err:
            print(f"  FAILED to read the uploads feed: {err}")
            print(f"  Try opening https://www.youtube.com/feeds/videos.xml?channel_id={cid} in your browser.")
            ok = False
            continue
        print(f"  uploads feed: {len(ups)} videos")
        for u in ups[:5]:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(u["published"].replace("Z", "+00:00"))
            print(f"    {age.total_seconds() / 3600:6.1f} hours ago  {'(done) ' if u['id'] in state['done'] else ''}{u['title'][:70]}")
    save_state(state)

    print("\nGemini key: ", end="", flush=True)
    try:
        gemini(cfg, "Return JSON.", 'Return {"ok": true}')
        print("works")
    except RuntimeError as err:
        print(f"FAILED: {err}")
        ok = False

    print("Email: ", end="", flush=True)
    if not (cfg.get("email_to") and cfg.get("smtp_user") and cfg.get("smtp_password")):
        print("not set up, so digests are only saved to the digests folder")
    else:
        try:
            with smtplib.SMTP_SSL(cfg["smtp_host"], int(cfg["smtp_port"]), context=ssl.create_default_context(), timeout=30) as s:
                s.login(cfg["smtp_user"], cfg["smtp_password"])
            print(f"login works ({cfg['smtp_user']})")
        except Exception as err:
            print(f"FAILED to log in as {cfg['smtp_user']}: {err}")
            print("  Gmail needs an app password (Google Account > Security > 2-Step Verification > App passwords), not the normal password.")
            ok = False
    return ok


# ---------------------------------------------------------------- the daily run

def main():
    ap = argparse.ArgumentParser(description="Daily digest of new videos from the channels you follow.")
    ap.add_argument("--hours", type=float, help="look back this many hours (default from the config, 26)")
    ap.add_argument("--dry-run", action="store_true", help="do not email, and do not mark videos as done")
    ap.add_argument("--video", help="make a digest of one video link instead of checking channels")
    ap.add_argument("--check", action="store_true", help="test each channel, the Gemini key and the email login, then stop")
    ap.add_argument("--open", action="store_true", help="open the digest in the browser when done")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg, state = load_config(), load_state()
    if not YTMD.exists():
        sys.exit(f"Put digest.py in the same folder as the ytmd script (looked for {YTMD}).")

    if not wait_for_internet():
        log("No internet for 15 minutes; stopping. Windows will try again in 30 minutes.")
        sys.exit(1)

    # 1. What is new
    unchecked = []   # channels whose uploads could not be read this time
    if args.check:
        sys.exit(0 if check(cfg, state) else 1)
    if args.video:
        vid = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", args.video)
        if not vid:
            sys.exit("That does not look like a YouTube video link.")
        new = [{"id": vid.group(1), "title": "", "channel": "", "published": datetime.now(timezone.utc).isoformat(),
                "url": f"https://www.youtube.com/watch?v={vid.group(1)}", "short": False}]
    else:
        now = datetime.now(timezone.utc)
        # Older state files have no last_sent; the newest "done" time is when that digest went out.
        last = state.get("last_sent") or max((t for t in state["done"].values() if t[:2] == "20"), default=None)
        if args.hours or not last:
            since = now - timedelta(hours=args.hours or cfg["lookback_hours"])
        else:   # everything since the last digest, so days the PC was off are not lost (at most a week back)
            since = max(datetime.fromisoformat(last) - timedelta(hours=1), now - timedelta(days=7))
        new = []
        for ch in cfg.get("channels", []):
            try:
                ups = latest_uploads(channel_id(ch, state))
            except Exception as err:   # one broken channel should not stop the digest
                log(f"Could not check {ch}: {err}")
                unchecked.append((ch, str(err)))
                continue
            fresh = [u for u in ups if u["id"] not in state["done"] and datetime.fromisoformat(u["published"].replace("Z", "+00:00")) >= since]
            log(f"{ch}: {len(ups)} in its feed, {len(fresh)} new since {since.astimezone():%d %b %H:%M}")
            new += fresh
        new.sort(key=lambda u: u["published"], reverse=True)
        if len(new) > cfg["max_videos"]:
            log(f"{len(new)} new videos; keeping the newest {cfg['max_videos']} (max_videos in the config).")
            new = new[:cfg["max_videos"]]
    if not args.dry_run:
        save_state(state)   # keeps the channel ids it just looked up

    # 2 and 3. Read and summarise each one, several at a time
    ytmd_lock = threading.Lock()   # ytmd writes one database file, so captions are fetched one at a time

    def process(v):
        try:
            with ytmd_lock:
                log(f"Reading: {v['title'] or v['url']}")
                text = transcript(v)
                if not v["title"] or not v["channel"]:   # a single --video run: take the details ytmd saved
                    info = ytmd("info", v["id"])
                    v["title"], v["channel"] = v["title"] or info.get("title", v["url"]), v["channel"] or info.get("channel", "")
            notes = extract(cfg, v, text)
            log(f"Summarised: {v['title'][:70]}")
            return notes
        except Exception as err:
            return err

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(process, new))
    done, skipped, sent_ok = [], [], {}
    for v, result in zip(new, results):
        if isinstance(result, Skip):
            skipped.append((v, str(result)))
            if not args.dry_run:
                state["done"][v["id"]] = "skipped: " + str(result)
        elif isinstance(result, Exception):   # temporary trouble: report it, and try again tomorrow
            skipped.append((v, f"failed this time, will retry: {result}"))
        else:
            done.append({"video": v, "notes": result})
            sent_ok[v["id"]] = datetime.now(timezone.utc).isoformat()   # recorded only after the digest goes out
    if not args.dry_run:
        save_state(state)

    # 4. One digest
    overview = day_summary(cfg, done) if len(done) > 1 else {"overview": done[0]["notes"]["summary"] if done else "", "themes": [], "disagreements": []}
    today = datetime.now()
    page = render(today, done, skipped, overview, unchecked)
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"digest-{today:%Y-%m-%d-%H%M}.html"
    local = re.sub(r"<!--ASK:([\w-]{11})-->", lambda m: f'<p style="margin:10px 0 0;font-size:13px"><a href="http://127.0.0.1:8765/?video={m.group(1)}" '
                   f'style="color:{C["blue"]}">Ask a question about this video</a> (opens the chat page; start it with run_chat.bat)</p>', page)
    out.write_text(local, encoding="utf-8")
    log(f"Saved {out}")
    subject = f"Market video digest, {today:%d %b %Y}: {len(done)} new video{'s' if len(done) != 1 else ''}"
    emailed = False
    if not args.dry_run and (done or skipped or unchecked):
        try:
            emailed = send(cfg, subject, page, plain_text(done, skipped, overview))
        except Exception as err:
            emailed = None
            log(f"Email failed: {err}. The digest is saved above; these videos stay queued and Windows will try again in 30 minutes.")
        if emailed:
            log("Emailed to " + ", ".join(cfg["email_to"] if isinstance(cfg["email_to"], list) else [cfg["email_to"]]))
        if emailed is not None:   # sent, or email is not set up and the saved file is the digest
            state["done"].update(sent_ok)
            state["last_sent"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
    elif not args.dry_run:
        log("Nothing new today, so no email was sent.")
    if args.open:
        os.startfile(out) if hasattr(os, "startfile") else print(out)
    if emailed is None:
        sys.exit(1)   # tells Task Scheduler the run failed, so it retries


if __name__ == "__main__":
    main()
