"""From the notes, prices and Wall Street's ratings to what the web app shows: one card a stock, and the market pages.

Nothing here depends on a user. A user's own numbers (shares, value, weight, gain) are worked out in their browser from
the card and what they typed, so their holdings are never needed here."""
import hashlib
import json
from collections import Counter
from datetime import timedelta

from . import ROOT  # noqa: F401
import digest as dg
import insights
import prices

USER_FIELDS = ("owned", "shares", "cost", "value", "weight_pct", "gain_pct", "for", "against", "worth_knowing", "watch", "latest")
ROW_FIELDS = ("ticker", "name", "price", "currency", "change_pct_day", "signal", "confidence_pct", "calls", "spark", "low_52w", "high_52w",
              "verdict_text", "basis", "sector")


def local_day(v):
    return v["when"].astimezone().date()


def stars(record):
    """0.5 to 5 from how often an analyst's calls were right and by how much they beat the S&P 500; None before 3 scored calls."""
    if not record or record.get("scored", 0) < 3 or record.get("hit_pct") is None or record.get("edge") is None:
        return None
    worth = 0.6 * record["hit_pct"] / 100 + 0.4 * max(0.0, min(1.0, (record["edge"] + 10) / 20))
    return max(0.5, round(worth * 10) / 2)


def call_row(c, cache, records):
    s = insights.score(c, cache)
    r = records.get(c["analyst"]) or {}
    return {**{k: c[k] for k in ("day", "view", "analyst", "channel", "reason", "link", "ticker")},
            "outcome": {k: s[k] for k in ("stock_pct", "sp500_pct", "edge", "right")} if s else None,
            "analyst_stars": stars(r), "analyst_hit_pct": r.get("hit_pct") if r.get("scored", 0) >= 3 else None}


def case(calls, view, n=3):
    """The reasons given on one side, newest first, one an analyst: 'Bulls say' / 'Bears say'."""
    out, seen = [], set()
    for c in sorted(calls, key=lambda c: c["day"], reverse=True):
        who = c["analyst"] or c["channel"]
        if c["view"] != view or not c["reason"] or who in seen:
            continue
        seen.add(who)
        out.append({"text": c["reason"][:220], "analyst": c["analyst"], "channel": c["channel"], "link": c["link"], "day": c["day"]})
        if len(out) == n:
            break
    return out


def fingerprint(doc):
    """The same for the same content, whatever the time: a card that did not change is not written again."""
    body = {k: v for k, v in doc.items() if k not in ("updated", "h")}
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


def stock_card(t, calls30, calls90, cache, records, street, events, today, prev):
    c = insights.check_stock(t, calls30, cache, records, street, {}, {}, events, today)
    for k in USER_FIELDS:
        c.pop(k, None)
    st = street.get(t) or {}
    mine90 = [x for x in calls90 if x["ticker"] == t]
    c["name"] = c["name"] or st.get("name") or ""
    c["street"] = {k: v for k, v in st.items() if k not in ("ticker", "name", "price", "days_to_earnings", "raw") and v is not None} or None
    c["sector"] = st.get("sector")
    c["pe"] = c.get("pe") if c.get("pe") is not None else st.get("pe")
    c["calls_list"] = [call_row(x, cache, records) for x in sorted(mine90, key=lambda x: x["day"], reverse=True)[:30]]
    c["bulls"], c["bears"] = case(mine90, insights.BULL), case(mine90, insights.BEAR)
    c["mentions"] = c["calls"][insights.BULL] + c["calls"][insights.BEAR]
    c["unknown"] = c["price"] is None and not mine90 and not st
    # the signal over time: a new line only when it changes
    history = list((prev or {}).get("history") or [])
    if not history or history[-1]["s"] != c["signal"]:
        history.append({"d": today.isoformat(), "s": c["signal"], "c": c["confidence_pct"]})
    c["history"] = history[-20:]
    before = history[-2] if len(history) > 1 else None
    recent = before and (today - _date(history[-1]["d"])).days <= 7
    c["changed"] = {"from": before["s"], "to": history[-1]["s"], "on": history[-1]["d"]} if recent and before["s"] != "none" else None
    c["h"] = fingerprint(c)
    c["updated"] = today.isoformat()
    return c


def _date(text):
    from datetime import date
    return date.fromisoformat(text)


def chart(t, cache):
    rows = prices.series(t, cache)[-260:]
    return {"d": [d for d, _ in rows], "c": [c for _, c in rows]} if rows else None


def row(card):
    out = {k: card.get(k) for k in ROW_FIELDS}
    out["street"] = {k: (card.get("street") or {}).get(k) for k in ("consensus", "upside_pct", "smart_score")} if card.get("street") else None
    return out


def analysts_doc(calls, cache, followed, pairs, today):
    table = insights.analysts_table(calls, cache, followed)
    roles = Counter()
    for _, notes in pairs:
        for s in dg.note_speakers(notes):
            if s.get("role"):
                roles[(s["name"], s["role"])] += 1
    role_of = {}
    for (name, role), _ in roles.most_common():
        role_of.setdefault(name, role)
    by = {}
    for c in sorted(calls, key=lambda c: c["day"], reverse=True):
        if c["analyst"]:
            by.setdefault(c["analyst"], []).append(c)
    records = {a["analyst"]: a for a in table}
    rows = []
    for a in table[:60]:
        rows.append({**a, "role": role_of.get(a["analyst"], ""), "stars": stars(a),
                     "recent": [call_row(c, cache, records) for c in by.get(a["analyst"], [])[:10]]})
    rows.sort(key=lambda a: (a["stars"] is None, -(a["stars"] or 0), -(a["edge"] or -99), -a["calls"]))
    return {"rows": rows, "updated": today.isoformat()}


def market_docs(cards, pairs, calls30, cache, sources, today, themes=None):
    """The pages that are the same for everyone: overview and ideas, analysts, calendar, videos, meta."""
    start = today - timedelta(days=30)
    videos30 = [(v, n) for v, n in pairs if local_day(v) >= start]
    views = Counter(c["view"] for c in calls30)
    covered = [c for c in cards.values() if c["signal"] != "none" and c["price"] is not None]
    by_conf = lambda c: (-(c["confidence_pct"] or 0), -c["mentions"], c["ticker"])
    lists = {
        "yes": [c["ticker"] for c in sorted((c for c in covered if c["signal"] == "yes" and c["mentions"] >= 2 and (c["confidence_pct"] or 0) >= 50), key=by_conf)[:15]],
        "no": [c["ticker"] for c in sorted((c for c in covered if c["signal"] == "no" and (c["confidence_pct"] or 0) >= 50), key=by_conf)[:15]],
        "discussed": [c["ticker"] for c in sorted(covered, key=lambda c: (-c["mentions"], c["ticker"]))[:15]],
        "split": [c["ticker"] for c in sorted((c for c in covered if c["signal"] == "wait" and c["mentions"] >= 3), key=lambda c: (-c["mentions"], c["ticker"]))[:15]],
        "changed": [c["ticker"] for c in sorted((c for c in covered if c.get("changed")), key=lambda c: c["changed"]["on"], reverse=True)[:15]],
    }
    listed = {t for ts in lists.values() for t in ts}
    sp = prices.quote(prices.SP500, cache)
    sp_rows = prices.series(prices.SP500, cache)[-66:]
    overview = {
        "date": today.isoformat(), "videos": len(videos30), "calls": len(calls30), "channels": len({v.get("channel") for v, _ in videos30}),
        "mood_pct": round(100 * views[insights.BULL] / (views[insights.BULL] + views[insights.BEAR])) if views[insights.BULL] + views[insights.BEAR] else None,
        "views": {v: views.get(v, 0) for v in insights.VIEWS}, "scorecard": insights.scorecard(calls30, cache),
        "mood_by_day": insights.mood_by_day(calls30, today - timedelta(days=29), today + timedelta(days=1)),
        "sp500": {"price": sp["price"], "change_pct_day": sp["change_pct_day"], "change_pct_month": sp["change_pct_month"],
                  "spark": [c for _, c in sp_rows]} if sp else None,
        "themes": themes or [], "extremes": insights.best_and_worst(calls30, cache, n=4),
        "lists": lists, "rows": {t: row(cards[t]) for t in sorted(listed)},
        "counts": {s: sum(c["signal"] == s for c in covered) for s in ("yes", "wait", "no")},
    }
    earnings = sorted(({"ticker": c["ticker"], "name": c["name"], "date": (c.get("street") or {}).get("next_earnings"), "days": c["days_to_earnings"],
                        "signal": c["signal"]} for c in cards.values() if c.get("days_to_earnings") is not None and c["days_to_earnings"] <= 45),
                      key=lambda e: (e["days"], e["ticker"]))
    calendar = {"earnings": earnings[:200], "events": insights.upcoming(videos30, today), "updated": today.isoformat()}
    table = insights.load_tickers()
    vids = []
    for v, n in pairs[:40]:
        stocks, seen = [], set()
        for s in n.get("stocks") or []:
            said, name = str(s.get("ticker") or "").strip(), str(s.get("name") or "").strip()
            t = prices.clean(insights.resolve_ticker(name or said, said, table) or (said or name).upper())
            if t and t not in seen:
                seen.add(t)
                stocks.append({"ticker": t, "view": s.get("view") if s.get("view") in insights.VIEWS else "mixed"})
        vids.append({"id": v["id"], "title": v.get("title"), "channel": v.get("channel"), "day": local_day(v).isoformat(), "link": v["url"],
                     "summary": (n.get("summary") or "")[:400], "speakers": insights.speakers(n)[:4], "stocks": stocks[:8]})
    meta = {"packs": sources.get("packs") or [], "channels": [c["name"] for c in sources["channels"]], "analysts": sources["analysts"],
            "updated": today.isoformat()}
    return {"overview": overview, "calendar": calendar, "videos": {"rows": vids, "updated": today.isoformat()}, "meta": meta}


def build(pairs, cache, street, prev, universe, today, sources, themes=None):
    """Everything to write: ({ticker: card}, {ticker: chart}, {name: market doc})."""
    since = lambda days: [(v, n) for v, n in pairs if local_day(v) >= today - timedelta(days=days)]
    calls30, calls90, calls120 = insights.calls_in(since(30)), insights.calls_in(since(90)), insights.calls_in(since(120))
    records = {a["analyst"]: a for a in insights.analysts_table(calls120, cache, sources["analysts"])}
    events = insights.upcoming(since(30), today)
    cards, charts = {}, {}
    for t in universe:
        cards[t] = stock_card(t, calls30, calls90, cache, records, street, events, today, prev.get(t))
        ch = chart(t, cache)
        if ch:
            charts[t] = ch
    docs = market_docs(cards, pairs, calls30, cache, sources, today, themes)
    docs["analysts"] = analysts_doc(calls120, cache, sources["analysts"], pairs, today)
    return cards, charts, docs
