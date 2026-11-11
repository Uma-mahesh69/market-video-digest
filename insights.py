"""What the saved videos add up to over a period: the numbers behind the dashboard and the weekly and monthly digests.

Everything here is computed by code from the notes saved for each video (digest_cache) and the prices this computer
fetched (prices.json). Nothing is asked of Gemini. A call is "right" when the stock then did better than the S&P 500
(for a bullish call) or worse (for a bearish one), measured from the first close after the video to the latest close.
Standard library only.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import digest as dg
import prices
from digest_export import load_tickers, resolve_ticker

MIN_SESSIONS = 3      # a call is scored once this many trading days have passed
BULL, BEAR = "bullish", "bearish"
VIEWS = ("bullish", "bearish", "neutral", "mixed")


def to_date(value):
    s = str(value or "")
    try:
        if re.fullmatch(r"\d{8}", s):
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def saved_notes():
    """(video, notes) for every saved video that went into a digest, newest first."""
    out = []
    for f in dg.CACHE_DIR.glob("*.json") if dg.CACHE_DIR.exists() else []:
        try:
            notes = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if notes.get("_left_out"):
            continue
        v = dict(notes.get("_video") or {})
        v.setdefault("id", f.stem)
        v.setdefault("url", f"https://www.youtube.com/watch?v={f.stem}")
        v["when"] = to_date(v.get("published"))
        if v["when"]:
            out.append((v, notes))
    return sorted(out, key=lambda vn: vn[0]["when"], reverse=True)


def window(start, end):
    """The saved videos published from start (inclusive) to end (exclusive), both dates."""
    return [(v, n) for v, n in saved_notes() if start <= v["when"].astimezone().date() < end]


def moment(video, item):
    s = item.get("seconds")
    return f"{video['url']}&t={int(s)}s" if isinstance(s, (int, float)) else video["url"]


def speakers(notes):
    return [s["name"] for s in dg.note_speakers(notes)]


def calls_in(videos):
    """Every stock call in these videos, as flat rows."""
    table = load_tickers()
    rows = []
    for v, notes in videos:
        who_spoke = speakers(notes)
        for s in notes.get("stocks") or []:
            said = str(s.get("ticker") or "").strip()
            name = str(s.get("name") or "").strip()
            symbol = resolve_ticker(name or said, said, table) or (said or name).upper()
            if not symbol:
                continue
            rows.append({"ticker": prices.clean(symbol) or symbol, "name": name, "view": s.get("view") if s.get("view") in VIEWS else "mixed",
                         "reason": str(s.get("reason") or "").strip(),
                         "analyst": str(s.get("analyst") or "").strip() or (who_spoke[0] if len(who_spoke) == 1 else ""),
                         "channel": v.get("channel") or "", "video": v.get("title") or "", "video_id": v["id"],
                         "day": v["when"].astimezone().date().isoformat(), "link": moment(v, s)})
    return rows


# ---------------------------------------------------------------- scoring calls against the S&P 500

def score(call, cache):
    """{"edge", "right", "stock_pct", "sp500_pct", "since"} for a bullish or bearish call, or None when it cannot
    be scored yet (no prices, or fewer than MIN_SESSIONS trading days since)."""
    if call["view"] not in (BULL, BEAR):
        return None
    stock, sp = prices.series(call["ticker"], cache), prices.series(prices.SP500, cache)
    a, b = prices.close_on(stock, call["day"]), prices.close_on(sp, call["day"])
    if not a or not b or not stock or not sp:
        return None
    if sum(1 for d, _ in stock if d > a[0]) < MIN_SESSIONS:
        return None
    s_pct = (stock[-1][1] / a[1] - 1) * 100
    m_pct = (sp[-1][1] / b[1] - 1) * 100
    edge = s_pct - m_pct if call["view"] == BULL else m_pct - s_pct   # positive = the call was right
    return {"edge": round(edge, 1), "right": edge > 0, "stock_pct": round(s_pct, 1), "sp500_pct": round(m_pct, 1), "since": a[0]}


# ---------------------------------------------------------------- the tables

def stocks_table(calls, cache, cfg):
    watch = {prices.clean(t) for t in cfg.get("watchlist") or []}
    held = holdings_weights(cfg, cache)
    by = defaultdict(list)
    for c in calls:
        by[c["ticker"]].append(c)
    rows = []
    for t, cs in by.items():
        counts = Counter(c["view"] for c in cs)
        latest = max(cs, key=lambda c: c["day"])
        q = prices.quote(t, cache)
        first = min(c["day"] for c in cs)
        start = prices.close_on(prices.series(t, cache), first)
        rows.append({"ticker": t, "name": next((c["name"] for c in cs if c["name"]), (q or {}).get("name", "")),
                     "calls": len(cs), **{v: counts.get(v, 0) for v in VIEWS},
                     "lean": lean(counts), "analysts": sorted({c["analyst"] for c in cs if c["analyst"]}),
                     "latest": {k: latest[k] for k in ("day", "view", "analyst", "channel", "reason", "link")},
                     "price": (q or {}).get("price"), "change_pct_day": (q or {}).get("change_pct_day"),
                     "move_since_pct": round((q["price"] / start[1] - 1) * 100, 1) if q and start else None,
                     "from_high_pct": (q or {}).get("from_high_pct"),
                     "watchlist": t in watch, "weight_pct": held.get(t)})
    return sorted(rows, key=lambda r: (-r["calls"], r["ticker"]))


def lean(counts):
    b, s = counts.get(BULL, 0), counts.get(BEAR, 0)
    if b + s == 0:
        return "no clear view"
    if b >= 2 * s and b > s:
        return "bullish"
    if s >= 2 * b and s > b:
        return "bearish"
    return "split"


def analysts_table(calls, cache, followed=()):
    followed_names = {n.strip().lower() for f in followed for n in str(f).split("/")}
    by = defaultdict(list)
    for c in calls:
        if c["analyst"]:
            by[c["analyst"]].append(c)
    rows = []
    for name, cs in by.items():
        scored = [s for s in (score(c, cache) for c in cs) if s]
        counts = Counter(c["view"] for c in cs)
        rows.append({"analyst": name, "calls": len(cs), "bullish": counts.get(BULL, 0), "bearish": counts.get(BEAR, 0),
                     "scored": len(scored), "right": sum(s["right"] for s in scored),
                     "hit_pct": round(100 * sum(s["right"] for s in scored) / len(scored)) if scored else None,
                     "edge": round(sum(s["edge"] for s in scored) / len(scored), 1) if scored else None,
                     "followed": name.lower() in followed_names,
                     "stocks": [t for t, _ in Counter(c["ticker"] for c in cs).most_common(4)]})
    return sorted(rows, key=lambda r: (-r["calls"], r["analyst"]))


def scorecard(calls, cache):
    out = {}
    for view in (BULL, BEAR):
        scored = [s for s in (score(c, cache) for c in calls if c["view"] == view) if s]
        out[view] = {"calls": sum(1 for c in calls if c["view"] == view), "scored": len(scored), "right": sum(s["right"] for s in scored),
                     "hit_pct": round(100 * sum(s["right"] for s in scored) / len(scored)) if scored else None,
                     "edge": round(sum(s["edge"] for s in scored) / len(scored), 1) if scored else None}
    return out


def best_and_worst(calls, cache, n=3):
    scored = [(c, s) for c in calls for s in [score(c, cache)] if s]
    scored.sort(key=lambda cs: cs[1]["edge"], reverse=True)
    pick = lambda cs: {**{k: cs[0][k] for k in ("ticker", "view", "analyst", "channel", "day", "link", "reason")}, **cs[1]}
    return {"best": [pick(x) for x in scored[:n]], "worst": [pick(x) for x in scored[::-1][:n] if x[1]["edge"] < 0]}


def mood_by_day(calls, start, end):
    days = []
    d = start
    while d < end:
        cs = [c for c in calls if c["day"] == d.isoformat()]
        b, s = sum(c["view"] == BULL for c in cs), sum(c["view"] == BEAR for c in cs)
        days.append({"day": d.isoformat(), "bullish": b, "bearish": s, "calls": len(cs)})
        d += timedelta(days=1)
    return days


def holdings_weights(cfg, cache):
    """{ticker: % of the value of your holdings}. Share counts never leave this computer."""
    values = {}
    for t, shares in (cfg.get("holdings") or {}).items():
        q = prices.quote(t, cache)
        try:
            if q and float(shares) > 0:
                values[prices.clean(t)] = q["price"] * float(shares)
        except (TypeError, ValueError):
            continue
    total = sum(values.values())
    return {t: round(100 * v / total, 1) for t, v in values.items()} if total else {}


def upcoming(videos, today):
    seen, out = set(), []
    for v, notes in videos:
        for e in notes.get("upcoming_events") or []:
            when = str(e.get("date") or "")
            key = (str(e.get("event") or "").lower()[:60], when)
            if not e.get("event") or key in seen or (when and when < today.isoformat()):
                continue
            seen.add(key)
            out.append({"event": e.get("event"), "date": when or None, "when": e.get("when") or "", "channel": v.get("channel"), "link": moment(v, e)})
    return sorted(out, key=lambda e: e["date"] or "9999")[:12]


def tipranks_latest(cfg):
    folder = dg.Path(cfg.get("json_dir") or dg.JSON_DIR)
    try:
        f = max(folder.glob("tipranks_*.json"))
        return {r["ticker"]: r for r in json.loads(f.read_text(encoding="utf-8")).get("rows") or [] if r.get("ticker")}
    except (ValueError, OSError, KeyError):
        return {}


# ---------------------------------------------------------------- what matters

def signals(stocks, analysts, card, street, cfg):
    """Up to 8 plain sentences worth reading first, most important first."""
    out = []
    held = {r["ticker"]: r for r in stocks if r["weight_pct"]}
    for r in stocks:
        if r["weight_pct"] and r["bearish"] > r["bullish"]:
            out.append(("bad", f"You hold {r['ticker']} ({r['weight_pct']}% of your holdings) and the analysts lean bearish: "
                               f"{r['bearish']} bearish to {r['bullish']} bullish calls.", r["latest"]["link"]))
    for r in stocks[:15]:
        st = street.get(r["ticker"]) or {}
        cons = str(st.get("consensus") or "").lower()
        if cons and r["lean"] in ("bullish", "bearish") and (("sell" in cons and r["lean"] == "bullish") or ("buy" in cons and r["lean"] == "bearish")):
            out.append(("warn", f"{r['ticker']}: the videos lean {r['lean']}, but Wall Street's consensus is {st.get('consensus')}.", r["latest"]["link"]))
    for r in stocks[:10]:
        if r["move_since_pct"] is not None and abs(r["move_since_pct"]) >= 8 and r["lean"] in ("bullish", "bearish"):
            went = "up" if r["move_since_pct"] > 0 else "down"
            agree = (went == "up") == (r["lean"] == "bullish")
            out.append(("good" if agree else "warn", f"{r['ticker']} is {went} {abs(r['move_since_pct'])}% since it was first called this period, "
                                                      f"and the calls lean {r['lean']}: so far they are {'right' if agree else 'wrong'}.", r["latest"]["link"]))
    top = [r for r in stocks if r["calls"] >= 3][:3]
    for r in top:
        if r["ticker"] not in held:
            out.append(("info", f"Most discussed: {r['ticker']} with {r['calls']} calls ({r['bullish']} bullish, {r['bearish']} bearish).", r["latest"]["link"]))
    good = [a for a in analysts if a["scored"] >= 3 and a["edge"] is not None and a["edge"] > 0]   # only a record that beat the market
    if good:
        best = max(good, key=lambda a: (a["edge"], a["scored"]))
        out.append(("good", f"Best record this period: {best['analyst']}, right on {best['right']} of {best['scored']} scored calls "
                            f"(average {best['edge']:+} points against the S&P 500).", None))
    b = card[BULL]
    if b["scored"] >= 5:
        out.append(("info", f"Bullish calls beat the S&P 500 {b['right']} times out of {b['scored']} ({b['hit_pct']}%).", None))
    return [{"tone": t, "text": x, "link": link} for t, x, link in out[:8]]


def overview(days=30, cfg=None, end=None, start=None):
    """Everything the dashboard shows, for the last N days (or start to end, both dates; end exclusive)."""
    cfg = cfg if cfg is not None else {}
    end = end or (date.today() + timedelta(days=1))
    start = start or (end - timedelta(days=days))
    videos = window(start, end)
    calls = calls_in(videos)
    cache = prices.load()
    stocks = stocks_table(calls, cache, cfg)
    analysts = analysts_table(calls, cache, cfg.get("analysts") or [])
    card = scorecard(calls, cache)
    street = tipranks_latest(cfg)
    sp = prices.quote(prices.SP500, cache)
    for r in stocks:
        st = street.get(r["ticker"]) or {}
        r["street"] = {k: st.get(k) for k in ("consensus", "price_target", "upside_pct", "next_earnings") if st.get(k) is not None} or None
    held = [{"ticker": t, "weight_pct": w, **{k: (prices.quote(t, cache) or {}).get(k) for k in ("price", "change_pct_day", "change_pct_month", "from_high_pct")},
             "bullish": next((r["bullish"] for r in stocks if r["ticker"] == t), 0), "bearish": next((r["bearish"] for r in stocks if r["ticker"] == t), 0)}
            for t, w in sorted(holdings_weights(cfg, cache).items(), key=lambda tw: -tw[1])]
    views = Counter(c["view"] for c in calls)
    return {
        "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(), "days": (end - start).days,
        "videos": len(videos), "channels": len({v.get("channel") for v, _ in videos}), "calls": len(calls),
        "mood_pct": round(100 * views[BULL] / (views[BULL] + views[BEAR])) if views[BULL] + views[BEAR] else None,
        "views": {v: views.get(v, 0) for v in VIEWS},
        "scorecard": card, "stocks": stocks, "analysts": analysts, "extremes": best_and_worst(calls, cache),
        "mood_by_day": mood_by_day(calls, start, end), "upcoming": upcoming(videos, date.today()),
        "holdings": held, "signals": signals(stocks, analysts, card, street, cfg),
        "sp500": {"price": sp["price"], "change_pct_day": sp["change_pct_day"], "as_of": sp["as_of"],
                  "change_pct_period": None} if sp else None,
        "prices_as_of": max((e.get("day") for e in cache.values() if isinstance(e, dict) and e.get("day")), default=None),
        "price_source": prices.SOURCE,
        "recent_videos": [{"title": v.get("title"), "channel": v.get("channel"), "day": v["when"].astimezone().date().isoformat(),
                           "link": v["url"], "speakers": speakers(n)[:3], "summary": n.get("summary", "")} for v, n in videos[:12]],
    }


def tickers_to_price(cfg, days=90):
    """The symbols worth keeping prices for: the watchlist, holdings, and the stocks called recently (most called first)."""
    calls = calls_in(window(date.today() - timedelta(days=days), date.today() + timedelta(days=1)))
    called = [t for t, _ in Counter(c["ticker"] for c in calls).most_common(60)]
    return list(dict.fromkeys([*(cfg.get("watchlist") or []), *(cfg.get("holdings") or {}).keys(), *called]))
