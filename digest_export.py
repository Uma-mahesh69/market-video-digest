"""Saves a day's digest as one structured JSON file, for the Econova Dashboard Hub to read.

digest.py calls export_digest() after it has written the email. The file holds the same content as the email in a
fixed shape (digest_schema.json, schema 1.0): one row per stock call, stock names merged into tickers (tickers.json),
and the video number and timestamp kept on every row so each point traces back to its source.
Scoring (mood, consensus buys, upside) is the hub's job, not this file's.
Standard library only.
"""
import json
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_FILE = HERE / "digest_schema.json"
TICKERS_FILE = HERE / "tickers.json"
SCHEMA_VERSION = "1.0"
VIEWS = ("bullish", "bearish", "neutral", "mixed")
UNITS = ("%", "USD", "index pts", "bp")
HORIZONS = ("year-end", "12-month")


# ---------------------------------------------------------------- small helpers

def stamp(seconds):
    """Seconds into the video as '12:34' or '1:02:03'; None when unknown."""
    if seconds is None:
        return None
    s = int(seconds)
    h, m, x = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


def text(value):
    return str(value or "").strip()


def speakers(notes):
    """Speakers as {"name", "role"} dicts. Notes cached by older versions hold plain strings."""
    out = []
    for s in notes.get("speakers") or []:
        if isinstance(s, dict):
            name, role = text(s.get("name")), text(s.get("role"))
        else:
            name, role = text(s), ""
        if name:
            out.append({"name": name, "role": role or None})
    return out


def number(value):
    """A plain number, or None. Booleans and text are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def iso_date(value):
    try:
        return datetime.strptime(text(value), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def video_numbers(nums, count):
    """Keep only video numbers that exist in this digest."""
    return [n for n in nums if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= count] if isinstance(nums, list) else []


# ---------------------------------------------------------------- stock names to tickers

def load_tickers():
    table = json.loads(TICKERS_FILE.read_text(encoding="utf-8"))
    return {norm(k): v for k, v in table.items() if not k.startswith("_")}


def norm(name):
    return re.sub(r"\s+", " ", text(name).lower()).strip(" .,")


def resolve_ticker(name, said, table):
    """The ticker for a company as written in the digest, or None. Tries the name, the name without any
    bracketed part, then the ticker the video said."""
    for candidate in (name, re.sub(r"\(.*?\)", "", text(name)), said):
        hit = table.get(norm(candidate))
        if hit:
            return hit
    return None


# ---------------------------------------------------------------- build the file

def build_payload(day, done, overview, table, now=None):
    """The JSON content for one digest. done is a list of {"video", "notes"}; overview is day_summary()'s result.
    Returns (payload, unmatched) where unmatched lists (name, ticker said) with no entry in tickers.json."""
    count = len(done)
    videos, mentions, levels, events = [], [], [], {}
    unmatched = []
    for n, d in enumerate(done, 1):
        v, nt = d["video"], d["notes"]
        at = lambda item: stamp(item.get("seconds"))
        videos.append({
            "number": n,
            "channel": text(v.get("channel")),
            "published_date": text(v.get("published"))[:10],
            "duration": stamp(v.get("duration")) if v.get("duration") else None,
            "title": text(v.get("title")),
            "url": text(v.get("url")),
            "speakers": speakers(nt),
            "summary": text(nt.get("summary")),
            "key_points": [{"text": text(p.get("point")), "timestamp": at(p)} for p in nt.get("key_points", []) if text(p.get("point"))],
            "sectors": [{"name": text(s.get("name")), "view": s.get("view", "mixed"), "reason": text(s.get("reason")), "timestamp": at(s)}
                        for s in nt.get("sectors_and_themes", []) if text(s.get("name"))],
            "expectations": [{"text": text(p.get("claim")), "horizon": text(p.get("horizon")) or None, "timestamp": at(p)}
                             for p in nt.get("predictions", []) if text(p.get("claim"))],
            "risks": [{"text": text(r.get("risk")), "timestamp": at(r)} for r in nt.get("risks", []) if text(r.get("risk"))],
            "sp500_targets": [{"value": t["value"], "horizon": t["horizon"]} for t in nt.get("sp500_targets", [])
                              if number(t.get("value")) is not None and t.get("horizon") in HORIZONS],
        })
        for s in nt.get("stocks", []):   # one row per call; the same company in two videos is two rows
            name = text(s.get("name")) or text(s.get("ticker"))
            if not name:
                continue
            ticker = resolve_ticker(name, s.get("ticker"), table)
            if ticker is None and (name, text(s.get("ticker"))) not in unmatched:
                unmatched.append((name, text(s.get("ticker"))))
            mentions.append({"ticker": ticker, "name": name, "view": s.get("view") if s.get("view") in VIEWS else "mixed",
                             "reason": text(s.get("reason")), "video": n, "analyst": text(s.get("analyst")) or None, "timestamp": at(s)})
        for l in nt.get("market_levels", []):
            if not text(l.get("item")):
                continue
            value = number(l.get("number"))
            levels.append({"metric": text(l.get("item")), "value": value, "unit": l.get("unit") if value is not None and l.get("unit") in UNITS else None,
                           "display": text(l.get("value")), "note": text(l.get("context")), "video": n, "timestamp": at(l)})
        for x in nt.get("upcoming_events", []):   # one row per distinct event, with every video that mentions it
            if not text(x.get("event")):
                continue
            row = events.setdefault(norm(x["event"]), {"event": text(x["event"]), "date": None, "date_text": "", "videos": []})
            row["date"] = row["date"] or iso_date(x.get("date"))
            row["date_text"] = row["date_text"] or text(x.get("when"))
            if n not in row["videos"]:
                row["videos"].append(n)

    themes = [{"name": text(t.get("theme")), "summary": text(t.get("detail")), "videos": video_numbers(t.get("videos"), count)}
              for t in overview.get("themes", []) if text(t.get("theme"))]
    debates = []
    for t in overview.get("disagreements", []):
        sides = [{"analysts": [text(a) for a in side.get("analysts", []) if text(a)] if isinstance(side.get("analysts"), list) else [],
                  "position": text(side.get("position")), "videos": video_numbers(side.get("videos"), count)}
                 for side in t.get("sides", []) if isinstance(side, dict) and text(side.get("position"))]
        if text(t.get("topic")) and sides:
            debates.append({"topic": text(t["topic"]), "sides": sides})

    channels = list(dict.fromkeys(v["channel"] for v in videos if v["channel"]))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "digest_date": day.strftime("%Y-%m-%d"),
        "generated_at": (now or datetime.now().astimezone()).isoformat(timespec="seconds"),
        "channels": channels,
        "video_count": count,
        "summary": text(overview.get("overview")),
        "videos": videos,
        "mentions": mentions,
        "themes": themes,
        "debates": debates,
        "levels": levels,
        "upcoming": list(events.values()),
    }
    return payload, unmatched


# ---------------------------------------------------------------- check against the schema

def _type_ok(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, {"string": str, "array": list, "object": dict}[name])


def validate(value, schema, root=None, path="$"):
    """Check value against the part of JSON Schema that digest_schema.json uses (type, const, enum, pattern, minimum,
    required, properties, additionalProperties, items, $ref). Returns a list of problems; empty means it passes."""
    root = root or schema
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return validate(value, node, root, path)
    errors = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            return [f"{path}: expected {' or '.join(types)}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: {value} is below {schema['minimum']}")
    if isinstance(value, dict):
        errors += [f"{path}: missing {k}" for k in schema.get("required", []) if k not in value]
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors += [f"{path}: unexpected field {k}" for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                errors += validate(value[k], sub, root, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += validate(item, schema["items"], root, f"{path}[{i}]")
    return errors


# ---------------------------------------------------------------- save it

def file_name(digest_date):
    return f"video-digest_{digest_date}.json"


def save(payload, directory, log):
    """Validate, then write video-digest_YYYY-MM-DD.json into directory. On any problem nothing is written and the
    reason is logged with the digest date; earlier days' files are never touched. Returns the path, or None."""
    date = payload["digest_date"]
    errors = validate(payload, json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))
    if errors:
        log(f"JSON digest for {date} NOT saved: {len(errors)} schema problem(s): " + "; ".join(errors[:5]))
        return None
    path = Path(directory) / file_name(date)
    try:
        if payload["video_count"] == 0 and path.exists():
            # A second run later the same day finds nothing new; it must not wipe out the day's earlier file.
            try:
                earlier = json.loads(path.read_text(encoding="utf-8")).get("video_count", 0)
            except (OSError, ValueError):
                earlier = 0
            if earlier:
                log(f"JSON digest for {date}: no new videos on this run, kept the earlier file ({earlier} videos).")
                return path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as err:
        log(f"JSON digest for {date} NOT saved: could not write {path}: {err}")
        return None
    log(f"Saved {path} ({payload['video_count']} videos, {len(payload['mentions'])} stock calls)")
    return path


def export_digest(day, done, overview, directory, log):
    """Build, check and save the JSON file for this digest. Returns the path, or None if nothing was saved."""
    payload, unmatched = build_payload(day, done, overview, load_tickers())
    for name, said in unmatched:
        log(f"JSON digest: no ticker for {name!r}" + (f" (video said {said!r})" if said else "") + "; add it to tickers.json")
    return save(payload, directory, log)
