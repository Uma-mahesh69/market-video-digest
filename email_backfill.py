"""Turn a digest that was already sent back into video-digest_YYYY-MM-DD.json, for days before the JSON export existed.

It reads the digest's HTML, either a saved copy (digests/digest-*.html) or the email's HTML, rebuilds each video's notes
from it, and saves the file through digest_export, so the file has the same shape and checks as a daily one.
    python email_backfill.py digests/digest-2026-10-22-0730.html            writes into json_dir (or digest_json/)
    python email_backfill.py digests/*.html --out some/folder
What the email does not hold stays empty: the analyst behind a call (unless the video had one speaker), exact event
dates, and the sides of a debate are worked out from the sentence that describes it. Each file says
"backfilled_from": "digest email". A day that already has a file is left alone, as past days are never changed.
Standard library only.
"""
import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from digest_export import build_payload, file_name, load_tickers, save

HERE = Path(__file__).resolve().parent
VIEWS = ("bullish", "bearish", "neutral", "mixed")


def plain(fragment):
    """The text of an HTML fragment."""
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def section(page, title):
    """The HTML between one <h2> heading and the next."""
    m = re.search(r"<h2[^>]*>" + re.escape(title) + r"</h2>(.*?)(?=<h2|<p style=\"margin:28px 0 0)", page, re.S)
    return m.group(1) if m else ""


def link(fragment):
    """(video id, seconds, time as shown) of the first timestamp link in a fragment, or (None, None, None)."""
    m = re.search(r'watch\?v=([\w-]{11})(?:&amp;|&)t=(\d+)s[^>]*>\[([\d:]+)\]', fragment)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (None, None, None)


def without_link(fragment):
    return plain(re.sub(r"<a [^>]*>\[[\d:]+\]</a>", "", fragment))


def seconds(clock):
    total = 0
    for part in (clock or "").split(":"):
        if part.isdigit():
            total = total * 60 + int(part)
    return total


def split_speakers(line):
    """'Caroline (Host), Sam Stovall (Chief Investment Strategist, CFRA)' -> [{name, role}], commas inside brackets kept."""
    people, depth, cur = [], 0, ""
    for ch in line:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            people.append(cur)
            cur = ""
        else:
            cur += ch
    people.append(cur)
    out = []
    for p in (p.strip() for p in people if p.strip()):
        m = re.fullmatch(r"(.*?)\s*\((.*)\)", p)
        if m:
            out.append({"name": m.group(1), "role": m.group(2)})
        elif out and not out[-1]["role"] and ROLE.search(p):
            out[-1]["role"] = p   # older digests wrote "Name, role" without brackets
        else:
            out.append({"name": p, "role": ""})
    return out


ROLE = re.compile(r"\b(host|interviewer|anchor|moderator|director|manager|founder|chair(man|woman)?|president|officer|ceo|cio|cfo|"
                  r"strategist|analyst|economist|partner|head|editor|reporter|portfolio|advisor|adviser|trader|investor)\b|\b(at|of)\s+[A-Z]", re.I)


def items(block):
    return re.findall(r"<li[^>]*>(.*?)</li>", block, re.S)


def video_cards(page):
    """Each video's details and notes from 'Video by video', keyed by video id, in digest order."""
    part = section(page, "Video by video")
    cards = {}
    for m in re.finditer(r'<p id="v(\d+)"[^>]*>(.*?)</p>(.*?)(?=<p id="v\d+"|$)', part, re.S):
        number, meta, rest = int(m.group(1)), plain(m.group(2)), m.group(3)
        url = re.search(r'href="(https://www\.youtube\.com/watch\?v=([\w-]{11}))"', rest)
        title = re.search(r'<a href="https://www\.youtube\.com/watch\?v=[\w-]{11}"[^>]*>(.*?)</a>', rest, re.S)
        bits = [b.strip() for b in re.sub(r"^#\d+\.\s*", "", meta).split(",")]
        duration = next((b for b in bits[2:] if re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", b)), None)
        paras = re.findall(r'<p style="margin:0">(.*?)</p>', rest, re.S)
        speaking = re.search(r"Speaking: (.*?)</p>", rest, re.S)
        groups = dict(re.findall(r'font-weight:600;color:#5C6878">([^<]+)</p><ul[^>]*>(.*?)</ul>', rest, re.S))
        vid = url.group(2) if url else f"video{number}"
        notes = {"summary": plain(paras[0]) if paras else "", "speakers": split_speakers(plain(speaking.group(1))) if speaking else [],
                 "key_points": [], "market_levels": [], "stocks": [], "sectors_and_themes": [], "predictions": [], "risks": [],
                 "upcoming_events": [], "sp500_targets": []}
        for li in items(groups.get("Key points", "")):
            notes["key_points"].append(dict(point=without_link(li), **at(li)))
        for li in items(groups.get("Sectors and themes", "")):
            view = re.search(r">(bullish|bearish|neutral|mixed)</span>", li)
            text = without_link(li)
            name, _, reason = text.partition(":")
            reason = re.sub(r"^\s*(bullish|bearish|neutral|mixed)\s*\.\s*", "", reason.strip())
            notes["sectors_and_themes"].append(dict(name=name.strip(), view=view.group(1) if view else "mixed", reason=reason, **at(li)))
        for li in items(groups.get("What they expect", "")):
            text = without_link(li)
            m2 = re.fullmatch(r"(.*?)\s*\(([^()]*)\)", text)
            notes["predictions"].append(dict(claim=m2.group(1) if m2 else text, horizon=m2.group(2) if m2 else "", **at(li)))
        for li in items(groups.get("Risks they flag", "")):
            notes["risks"].append(dict(risk=without_link(li), **at(li)))
        cards[vid] = {"number": number, "video": {"id": vid, "title": plain(title.group(1)) if title else "",
                                                  "channel": bits[0] if bits else "", "published": bits[1] if len(bits) > 1 else "",
                                                  "url": url.group(1) if url else "", "duration": seconds(duration) if duration else 0},
                      "notes": notes}
    return cards


def at(fragment):
    vid, secs, clock = link(fragment)
    return {"time": clock or "", "seconds": secs}


def targets(notes):
    """S&P 500 targets stated as such in the video's summary or expectations: year-end and 12-month."""
    text = " ".join([notes["summary"]] + [p["claim"] for p in notes["predictions"]])
    found = []
    for horizon, pattern in (("year-end", r"year[- ]end (?:S&P 500 )?(?:price )?target of ([\d,]{4,6})"),
                             ("12-month", r"12[- ]month (?:S&P 500 )?(?:price )?target of ([\d,]{4,6})")):
        for m in re.finditer(pattern, text, re.I):
            value = int(m.group(1).replace(",", ""))
            if {"value": value, "horizon": horizon} not in found:
                found.append({"value": value, "horizon": horizon})
    return found


def sides(detail, videos, cards_by_number):
    """The two sides of a disagreement, from its sentence: split at 'while', 'whereas' or 'but', and give each side the
    speakers it names and the videos those speakers appear in."""
    parts = [p.strip(" ,.;") for p in re.split(r",?\s+(?:while|whereas|but)\s+|;\s+", detail) if p.strip(" ,.;")]
    if len(parts) < 2:
        return []
    out = []
    for part in parts:
        names = []
        # "Videos 1, 4, and 5 call it a trap": the side names its videos
        said = re.search(r"\b[Vv]ideos?\s+((?:#?\d+(?:\s*,\s*(?:and\s+)?|\s+and\s+)?)+)", part)
        vids = [n for n in (int(x) for x in re.findall(r"\d+", said.group(1))) if n in videos] if said else []
        for n in videos:
            for s in cards_by_number.get(n, {}).get("notes", {}).get("speakers", []):
                last = s["name"].split()[-1] if s["name"] else ""
                if last and re.search(rf"\b{re.escape(last)}\b", part) and s["name"] not in names:
                    names.append(s["name"])
                if last and re.search(rf"\b{re.escape(last)}\b", part) and n not in vids:
                    vids.append(n)
        out.append({"analysts": names, "position": part[0].upper() + part[1:], "videos": vids or list(videos)})
    return out


def parse(page):
    """(day, done, overview) from a digest's HTML, as digest.py would hand them to the export."""
    dated = re.search(r"\w+day, (\d{1,2} \w+ \d{4})\.", page)
    if not dated:
        raise ValueError("this does not look like a market video digest (no date line)")
    day = datetime.strptime(dated.group(1), "%d %B %Y")
    cards = video_cards(page)
    by_number = {c["number"]: c for c in cards.values()}

    # Stocks: each line of the View and Why columns is one call, linked to its video and moment
    for row in re.findall(r"<tr>(.*?)</tr>", section(page, "Stocks mentioned"), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 3 or "<b>" not in cells[0]:
            continue
        name = plain(re.search(r"<b>(.*?)</b>", cells[0], re.S).group(1))
        tick = re.search(r"<span[^>]*>([^<]+)</span>", cells[0])
        views = re.findall(r">(bullish|bearish|neutral|mixed)</span>", cells[1])
        for view, why in zip(views, cells[2].split("<br>")):
            vid, secs, clock = link(why)
            card = cards.get(vid) or (next(iter(cards.values())) if len(cards) == 1 else None)
            if card:
                card["notes"]["stocks"].append({"name": name, "ticker": plain(tick.group(1)) if tick else "", "view": view,
                                                "reason": without_link(why), "analyst": "", "time": clock or "", "seconds": secs})

    for row in re.findall(r"<tr>(.*?)</tr>", section(page, "Market levels and data quoted"), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 4:
            continue
        vid, secs, clock = link(cells[3])
        if vid in cards:
            value = plain(re.sub(r"<span[^>]*>\(check\)</span>", "", cells[1]))
            cards[vid]["notes"]["market_levels"].append({"item": plain(cells[0]), "value": value, "context": plain(cells[2]),
                                                         "time": clock or "", "seconds": secs, "unclear": "(check)" in cells[1]})

    for li in items(section(page, "Coming up")):
        vid, secs, clock = link(li)
        text = re.sub(r"\s*\([^()]*\)\s*$", "", without_link(li))   # drop the "(TheStreet)" channel name
        event, _, when = text.rpartition(", ")
        if vid in cards:
            cards[vid]["notes"]["upcoming_events"].append({"event": event or text, "when": when if event else "", "date": "",
                                                           "time": clock or "", "seconds": secs})

    for c in cards.values():
        c["notes"]["sp500_targets"] = targets(c["notes"])

    refs = lambda p: [int(n) for n in re.findall(r'href="#v(\d+)"', p)]
    themes = [{"theme": plain(t), "detail": without_refs(d), "videos": refs(d)}
              for t, d in re.findall(r"<p[^>]*><b>(.*?)</b>\.(.*?)</p>", section(page, "Themes today"), re.S)]
    disagreements = []
    for t, d in re.findall(r"<p[^>]*><b>(.*?)</b>\.(.*?)</p>", section(page, "Where channels disagree"), re.S):
        detail = without_refs(d)
        disagreements.append({"topic": plain(t), "detail": detail, "videos": refs(d), "sides": sides(detail, refs(d), by_number)})
    lead = re.search(r'<p style="font-size:16px;line-height:1.6">(.*?)</p>', page, re.S)
    done = [{"video": c["video"], "notes": c["notes"]} for c in sorted(cards.values(), key=lambda c: c["number"])]
    return day, done, {"overview": plain(lead.group(1)) if lead else "", "themes": themes, "disagreements": disagreements}


def without_refs(fragment):
    return plain(re.sub(r'<a href="#v\d+"[^>]*>#\d+</a>', "", fragment))


def combine(digests):
    """One day from that day's digests, as the daily run makes one file per day. The digest with the most videos is the
    base (often a later run that covers the earlier ones); videos only in another digest are added after its own."""
    digests = sorted(digests, key=lambda d: -len(d[1]))
    day, done, overview = digests[0]
    seen = {d["video"]["id"] for d in done}
    for _, more, _ in digests[1:]:
        for d in more:
            if d["video"]["id"] not in seen:
                done.append(d)
                seen.add(d["video"]["id"])
    return day, done, overview


def backfill(pages, folder, log=print):
    """Write one day's JSON file into folder from that day's digest pages. Returns the path, or None (nothing written)."""
    day, done, overview = combine([parse(p) for p in pages])
    if (Path(folder) / file_name(f"{day:%Y-%m-%d}")).exists():
        log(f"{folder}/{file_name(f'{day:%Y-%m-%d}')} already exists; past days are never changed, so it is left as it is.")
        return None
    payload, unmatched = build_payload(day, done, overview, load_tickers())
    payload["backfilled_from"] = "digest email"
    for name, said in unmatched:
        log(f"no ticker for {name!r}; add it to tickers.json")
    return save(payload, folder, log)


def main():
    ap = argparse.ArgumentParser(description="Write video-digest_YYYY-MM-DD.json files from digests already sent.")
    ap.add_argument("pages", nargs="+", help="saved digests (digests/digest-*.html) or saved email HTML")
    ap.add_argument("--out", help="folder to write into (default: json_dir from digest_config.json, else digest_json/)")
    args = ap.parse_args()
    folder = args.out
    if not folder:
        cfg = HERE / "digest_config.json"
        folder = (json.loads(cfg.read_text(encoding="utf-8")).get("json_dir") if cfg.exists() else None) or HERE / "digest_json"
    by_day, ok = {}, True
    for p in args.pages:   # several digests on one day become one file, as the daily run does
        try:
            page = Path(p).read_text(encoding="utf-8")
            by_day.setdefault(f"{parse(page)[0]:%Y-%m-%d}", []).append(page)
        except (OSError, ValueError) as err:
            print(f"{p}: {err}")
            ok = False
    for day in sorted(by_day):
        ok = backfill(by_day[day], folder) is not None and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
