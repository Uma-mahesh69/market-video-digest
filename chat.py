"""Ask questions about the videos in your digest, plus what the web says now.

Start it with run_chat.bat (or: python chat.py). It opens http://127.0.0.1:8765 in your browser.
It only listens on this computer. It uses the same digest_config.json, Gemini key and saved videos as digest.py.
Standard library only.
"""
import json
import re
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import digest as dg

PORT = 8765
CHATS = dg.HERE / "chats.json"
LOCK = threading.Lock()
MAX_VIDEOS = 25            # newest videos in scope that Gemini sees notes for
MAX_FOCUS_CHARS = 120_000  # transcript sent when you ask about one video
STOPWORDS = set("""a an and are as at be been but by can could did do does for from had has have how i if in into is it its me my
of on or our should so than that the their them then there these they this to was we were what when where which who why will
with would you your about tell explain say said says video videos channel channels think vs versus compare""".split())


# ---------------------------------------------------------------- the videos you have

_meta = {}


def video_meta(vid, notes):
    """Title, channel and date for a saved video: from its notes, or from ytmd for older notes."""
    if vid in _meta:
        return _meta[vid]
    v = dict(notes.get("_video") or {})
    if not v.get("title"):
        try:
            info = dg.ytmd("info", vid)
            v.update(title=info.get("title"), channel=info.get("channel"), published=v.get("published") or info.get("uploaded_at") or info.get("ingested_at"),
                     duration=info.get("duration_s"))
        except Exception:
            v.setdefault("title", vid)
    v["id"], v["url"] = vid, f"https://www.youtube.com/watch?v={vid}"
    v["date"] = to_date(v.get("published"))
    _meta[vid] = v
    return v


def to_date(value):
    s = str(value or "")
    try:
        if re.fullmatch(r"\d{8}", s):
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def library():
    out = []
    for f in dg.CACHE_DIR.glob("*.json") if dg.CACHE_DIR.exists() else []:
        try:
            notes = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append((video_meta(f.stem, notes), notes))
    far = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return sorted(out, key=lambda vn: vn[0]["date"] or far, reverse=True)


def in_scope(days, focus):
    lib = library()
    if focus:
        return [vn for vn in lib if vn[0]["id"] == focus]
    if days:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        lib = [vn for vn in lib if vn[0]["date"] and vn[0]["date"] >= since]
    return lib[:MAX_VIDEOS]


# ---------------------------------------------------------------- what Gemini is shown

def keywords(q):
    words = re.findall(r"[a-z0-9$%.]+", q.lower())
    return list(dict.fromkeys(w.strip(".") for w in words if w.strip(".") not in STOPWORDS and len(w.strip(".")) > 1))[:12]


def full_transcript(vid):
    lines, cursor = [], None
    while True:
        page = dg.ytmd("read", vid, "--cursor", cursor) if cursor else dg.ytmd("read", vid, "--max-chars", "100000")
        lines += [f"[{dg.clock(p['start'])}] {p['text']}" for p in page.get("passages", [])]
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            return "\n".join(lines)[:MAX_FOCUS_CHARS]


def context(question, videos, focus):
    """Numbered videos with their notes, plus caption passages that match the question."""
    number = {v["id"]: n for n, (v, _) in enumerate(videos, 1)}
    blocks = []
    for n, (v, notes) in enumerate(videos, 1):
        keep = {k: notes.get(k) for k in ("summary", "key_points", "market_levels", "stocks", "sectors_and_themes", "predictions", "risks", "upcoming_events") if notes.get(k)}
        for items in keep.values():
            if isinstance(items, list):
                for it in items:
                    it.pop("seconds", None)
        date = v["date"].strftime("%d %b %Y") if v["date"] else "date unknown"
        blocks.append(f"V{n}: \"{v.get('title')}\" by {v.get('channel')}, {date}\nNotes: {json.dumps(keep, ensure_ascii=False)}")
    text = "VIDEOS\n\n" + "\n\n".join(blocks)
    if focus and videos:
        try:
            text += f"\n\nFULL TRANSCRIPT OF V1 (lines start with their time)\n{full_transcript(focus)}"
        except Exception as err:
            text += f"\n\n(The full transcript could not be read: {err})"
    else:
        words = keywords(question)
        if words:
            try:
                hits = dg.ytmd("search", *words, "--match", "any", "-n", "40")
            except Exception:
                hits = []
            hits = [h for h in hits if h.get("video_id") in number][:12]
            if hits:
                text += "\n\nCAPTION PASSAGES THAT MATCH THE QUESTION\n" + "\n".join(
                    f"V{number[h['video_id']]} at [{dg.clock(h['start'])}]: {h['text']}" for h in hits)
    return text


WEB_RULES = {
    "on": "Use Google Search for current facts, prices, news and definitions. Give the date of any price or figure you state.",
    "off": "Web search is turned off. Under this heading write only: Web search is off for this question.",
    "unavailable": "Web search could not be used. Under this heading write only: Web search was not available for this question "
                   "(the Gemini key has no search quota left), so this answer uses only your videos.",
}


def system_prompt(web):
    today = datetime.now().strftime("%A %d %B %Y")
    web_rule = WEB_RULES[web]
    return f"""You answer questions from a finance professional about the YouTube videos in his daily digest, and about the wider market. Today is {today}.

Write your answer in exactly two sections with these headings:

## From your channels
What the videos say that bears on the question. Cite every claim as [V2 12:34], using the video number and a time from its notes or passages. Report each channel's view as that channel's view, not as fact. Where channels differ, say who says what. If the videos do not cover the question, say so in one sentence.

## From the web
{web_rule} Point out where the web contradicts or updates what a channel said.

Rules:
- Be concise and specific. Prefer numbers, names and dates over general statements.
- Use "- " for bullet points and **bold** sparingly. No tables.
- Do not tell him what to buy or sell. You may lay out the arguments on each side.
- Captions can mishear names and figures. If a figure from a video looks wrong, say so."""


# ---------------------------------------------------------------- Gemini, with Google Search

def ask_gemini(cfg, history, question, ctx, web):
    """Returns (text, sources, search suggestions, whether web search was used)."""
    contents = [{"role": "user" if m["role"] == "you" else "model", "parts": [{"text": m["text"]}]} for m in history[-6:]]
    contents.append({"role": "user", "parts": [{"text": f"{ctx}\n\nQUESTION\n{question}"}]})

    def body(mode):
        b = {"system_instruction": {"parts": [{"text": system_prompt(mode)}]}, "contents": contents, "generationConfig": {"temperature": 0.3}}
        if mode == "on":
            b["tools"] = [{"google_search": {}}]
        return b

    if web:
        try:   # search quota is separate and often zero on the free tier, so try two models once, without waiting
            data = dg.call_gemini(cfg, body("on"), models=cfg["models"][:2], patient=False)
        except dg.GeminiError as err:
            if err.code in (401, 403):
                raise
            dg.log(f"Web search not available ({err.code or 'no answer'}); answering from the videos only.")
            web = False
            data = dg.call_gemini(cfg, body("unavailable"))
    else:
        data = dg.call_gemini(cfg, body("off"))
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", [])).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty answer (finish reason: " + str(cand.get("finishReason")) + ")")
    meta = cand.get("groundingMetadata") or {}
    sources, seen = [], set()
    for ch in meta.get("groundingChunks", []):
        w = ch.get("web") or {}
        if w.get("uri") and w["uri"] not in seen:
            seen.add(w["uri"])
            sources.append({"title": w.get("title") or w["uri"], "url": w["uri"]})
    return text, sources, (meta.get("searchEntryPoint") or {}).get("renderedContent", ""), web


# ---------------------------------------------------------------- saved chats

def load_chats():
    try:
        return json.loads(CHATS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_chats(chats):
    tmp = CHATS.with_suffix(".tmp")
    tmp.write_text(json.dumps(chats, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CHATS)


def answer(cfg, req):
    question = (req.get("question") or "").strip()
    if not question:
        raise ValueError("Type a question first.")
    days, focus, web = int(req.get("days") or 0), req.get("video") or "", bool(req.get("web"))
    with LOCK:
        chats = load_chats()
    chat = next((c for c in chats if c["id"] == req.get("chat")), None)
    videos = in_scope(days, focus)
    text, sources, suggestions, web_used = ask_gemini(cfg, chat["messages"] if chat else [], question, context(question, videos, focus), web)
    numbered = {str(n): {"title": v.get("title"), "channel": v.get("channel"), "url": v["url"]} for n, (v, _) in enumerate(videos, 1)}
    now = datetime.now().isoformat(timespec="seconds")
    with LOCK:
        chats = load_chats()
        chat = next((c for c in chats if c["id"] == req.get("chat")), None)
        if not chat:
            chat = {"id": uuid.uuid4().hex[:12], "title": question[:80], "created": now, "messages": []}
            chats.insert(0, chat)
        chat["messages"] += [{"role": "you", "text": question, "at": now,
                              "scope": "one video" if focus else (f"last {days} days" if days else "all saved videos"), "web": web_used},
                             {"role": "answer", "text": text, "at": now, "videos": numbered, "sources": sources, "suggestions": suggestions}]
        chat["updated"] = now
        chats.sort(key=lambda c: c.get("updated", c["created"]), reverse=True)
        save_chats(chats)
    return chat


# ---------------------------------------------------------------- the web server (this computer only)

class Handler(BaseHTTPRequestHandler):
    cfg = None

    def log_message(self, *a):
        pass

    def allowed(self):
        # Only pages opened from this computer's own address may use it.
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        if u.path == "/":
            return self.send(200, (dg.HERE / "chat.html").read_text(encoding="utf-8"), "text/html")
        if u.path == "/api/state":
            vids = [{"id": v["id"], "title": v.get("title"), "channel": v.get("channel"), "date": v["date"].strftime("%d %b") if v["date"] else ""} for v, _ in library()]
            with LOCK:
                chats = [{"id": c["id"], "title": c["title"], "updated": c.get("updated", c["created"])} for c in load_chats()]
            return self.send(200, {"videos": vids, "chats": chats})
        if u.path == "/api/chat":
            cid = parse_qs(u.query).get("id", [""])[0]
            with LOCK:
                chat = next((c for c in load_chats() if c["id"] == cid), None)
            return self.send(200, chat) if chat else self.send(404, {"error": "That chat no longer exists."})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.allowed() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send(403, {"error": "forbidden"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self.send(400, {"error": "bad request"})
        try:
            if self.path == "/api/ask":
                return self.send(200, answer(self.cfg, req))
            if self.path == "/api/delete":
                with LOCK:
                    save_chats([c for c in load_chats() if c["id"] != req.get("id")])
                return self.send(200, {"ok": True})
            if self.path == "/api/rename":
                with LOCK:
                    chats = load_chats()
                    for c in chats:
                        if c["id"] == req.get("id") and (req.get("title") or "").strip():
                            c["title"] = req["title"].strip()[:80]
                    save_chats(chats)
                return self.send(200, {"ok": True})
        except ValueError as err:
            return self.send(400, {"error": str(err)})
        except Exception as err:
            return self.send(502, {"error": str(err)})
        self.send(404, {"error": "not found"})


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    Handler.cfg = dg.load_config()
    if not dg.YTMD.exists():
        sys.exit(f"Put chat.py in the same folder as the ytmd script (looked for {dg.YTMD}).")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"The chat page is already running. Opening http://127.0.0.1:{PORT}")
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        return
    print(f"Chat page: http://127.0.0.1:{PORT}  (only this computer can open it). Close this window to stop it.")
    if "--no-browser" not in sys.argv:
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
