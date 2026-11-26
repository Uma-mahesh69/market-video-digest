"""Econova's own track record: when the signal said Bullish (or Bearish), did the stock then beat (or trail) the
S&P 500? And which shows' guests are right most often.

Two records, kept apart because they mean different things:

- The replay goes back over the months of videos already read. At a check every week it works out the signal from
  the video calls of the 30 days before (the same rules as the live signal: one vote an analyst, fresh views count
  most), then looks at the month after. Wall Street's rating is left out, because we do not have its history and
  using today's would be cheating; analysts' records are left out for the same reason (they use later prices).
- The live record follows each stock's real signal since the signal's rules last changed (cards.METHOD), from the day
  it was given until it changed, or until today.
"""
from collections import defaultdict
from datetime import date, timedelta

import insights
import prices

HORIZON = 21      # trading days after a check: about a month
STEP = 5          # trading days between checks: about a week
WINDOW = 30       # days of calls behind the signal at a check, as for the live signal
MIN_CALLS = 2     # bullish or bearish calls needed before a stock has a signal at a check
LEAD_DAYS = 14    # the first check comes this long after the first call, so it has calls to go on
BULL, BEAR = insights.BULL, insights.BEAR


def signal_of(calls, day):
    """'yes', 'no' or 'wait' from these calls as at this day, by the video side of the live rules; None with no view."""
    bull, bear, _ = insights.video_votes(calls, {}, day)
    if bull + bear == 0:
        return None
    lean = (bull - bear) / (bull + bear)
    return "yes" if lean >= insights.YES_AT else "no" if lean <= -insights.YES_AT else "wait"


def _move(rows, start, end):
    """(percent, first day, last day) from the close on or after `start` to the close on or after `end`."""
    a = prices.close_on(rows, start)
    b = prices.close_on(rows, end) if end else (rows[-1] if rows else None)
    if not a or not b or b[0] <= a[0]:
        return None
    return (b[1] / a[1] - 1) * 100, a[0], b[0]


def _sessions(rows, a, b):
    return sum(1 for d, _ in rows if a < d <= b)


def summary(picks, signal):
    """How the picks with this signal did: how many, how often right, the average lead over the S&P 500."""
    xs = [p for p in picks if p["s"] == signal]
    if not xs:
        return {"n": 0, "right": 0, "hit_pct": None, "excess": None, "stocks": 0}
    right = sum((p["excess"] > 0) if signal == "yes" else (p["excess"] < 0) for p in xs) if signal in ("yes", "no") else None
    return {"n": len(xs), "right": right, "hit_pct": round(100 * right / len(xs)) if right is not None else None,
            "excess": round(sum(p["excess"] for p in xs) / len(xs), 1), "stocks": len({p["t"] for p in xs})}


def replay(calls, cache):
    """The signal replayed at weekly checks over the videos already read, each judged on the month after."""
    sp = prices.series(prices.SP500, cache)
    empty = {"checks": [], "yes": summary([], "yes"), "no": summary([], "no"), "wait": summary([], "wait"), "all": summary([], "all"),
             "best": [], "worst": [], "from": None, "to": None, "horizon": HORIZON}
    if not calls or len(sp) <= HORIZON:
        return empty
    days = [d for d, _ in sp]
    start = (date.fromisoformat(min(c["day"] for c in calls)) + timedelta(days=LEAD_DAYS)).isoformat()
    usable = [i for i, d in enumerate(days) if d >= start and i + HORIZON < len(days)]
    checks = sorted(usable[::-1][::STEP])   # counted back from the newest, so the latest month is always in
    by = defaultdict(list)
    for c in calls:
        by[c["ticker"]].append(c)
    picks, rows = [], []
    for i in checks:
        d, e = days[i], days[i + HORIZON]
        lo = (date.fromisoformat(d) - timedelta(days=WINDOW)).isoformat()
        market = (sp[i + HORIZON][1] / sp[i][1] - 1) * 100
        here = []
        for t, cs in by.items():
            mine = [c for c in cs if lo < c["day"] <= d]
            if sum(c["view"] in (BULL, BEAR) for c in mine) < MIN_CALLS:
                continue
            s = signal_of(mine, date.fromisoformat(d))
            got = _move(prices.series(t, cache), d, e) if s else None
            if not got:
                continue
            here.append({"t": t, "d": d, "e": e, "s": s, "ret": round(got[0], 1), "excess": round(got[0] - market, 1)})
        picks += here
        avg = lambda s: (lambda xs: round(sum(xs) / len(xs), 1) if xs else None)([p["excess"] for p in here if p["s"] == s])
        rows.append({"d": d, "e": e, "sp500": round(market, 1), "yes": avg("yes"), "no": avg("no"),
                     "n_yes": sum(p["s"] == "yes" for p in here), "n_no": sum(p["s"] == "no" for p in here),
                     "picks": sorted([p["t"] for p in here if p["s"] == "yes"])[:12]})
    yes = sorted((p for p in picks if p["s"] == "yes"), key=lambda p: -p["excess"])
    return {"checks": rows, "yes": summary(picks, "yes"), "no": summary(picks, "no"), "wait": summary(picks, "wait"),
            "all": summary([{**p, "s": "all"} for p in picks], "all"), "best": yes[:5], "worst": [p for p in yes[::-1][:5] if p["excess"] < 0],
            "from": rows[0]["d"] if rows else None, "to": rows[-1]["e"] if rows else None, "horizon": HORIZON}


def live(cards, cache, today):
    """Each real Bullish or Bearish signal since the rules last changed, from the day it was given to when it changed
    (or to today), against the S&P 500 over the same days. Too new to judge: fewer than 3 market days."""
    sp = prices.series(prices.SP500, cache)
    out, since = [], None
    for t, c in cards.items():
        h = c.get("history") or []
        rows = prices.series(t, cache)
        for k, entry in enumerate(h):
            since = min(since or entry["d"], entry["d"])
            if entry["s"] not in ("yes", "no"):
                continue
            end = h[k + 1]["d"] if k + 1 < len(h) else None
            got, market = _move(rows, entry["d"], end), _move(sp, entry["d"], end)
            row = {"t": t, "s": entry["s"], "from": entry["d"], "to": end, "open": end is None, "conf": entry.get("c")}
            if got and market and _sessions(rows, got[1], got[2]) >= insights.MIN_SESSIONS:
                excess = got[0] - market[0]
                row.update(ret=round(got[0], 1), sp500=round(market[0], 1), excess=round(excess, 1), right=(excess > 0) == (entry["s"] == "yes"))
            out.append(row)
    judged = [r for r in out if "excess" in r]
    out.sort(key=lambda r: (r["from"], r["t"]), reverse=True)
    return {"since": since, "yes": summary([r for r in judged], "yes"), "no": summary([r for r in judged], "no"),
            "waiting": len(out) - len(judged), "rows": out[:40], "judged": len(judged), "updated": today.isoformat()}


def shows(calls, cache, n=20):
    """Each channel's calls and how they turned out: which shows' guests are right most often."""
    by = defaultdict(list)
    for c in calls:
        if c.get("channel"):
            by[c["channel"]].append(c)
    out = []
    for name, cs in by.items():
        scored = [s for s in (insights.score(c, cache) for c in cs) if s]
        out.append({"channel": name, "calls": len(cs), "bullish": sum(c["view"] == BULL for c in cs), "bearish": sum(c["view"] == BEAR for c in cs),
                    "scored": len(scored), "right": sum(s["right"] for s in scored),
                    "hit_pct": round(100 * sum(s["right"] for s in scored) / len(scored)) if scored else None,
                    "edge": round(sum(s["edge"] for s in scored) / len(scored), 1) if scored else None,
                    "analysts": len({c["analyst"] for c in cs if c["analyst"]})})
    out.sort(key=lambda r: (r["scored"] < 5, -(r["hit_pct"] or 0), -r["calls"]))
    return out[:n]


def build(calls, cards, cache, today):
    """The track record page: the replay, the live record, every call by view, and the shows."""
    return {"replay": replay(calls, cache), "live": live(cards, cache, today), "calls": insights.scorecard(calls, cache),
            "shows": shows(calls, cache), "window": WINDOW, "updated": today.isoformat()}


def headline(doc):
    """The one line the front page and Home can show: how Bullish signals did against Bearish ones, or None."""
    r = (doc or {}).get("replay") or {}
    y, n = r.get("yes") or {}, r.get("no") or {}
    if (y.get("n") or 0) < 10 or y.get("excess") is None:
        return None
    return {"yes_hit_pct": y.get("hit_pct"), "yes_excess": y.get("excess"), "no_excess": n.get("excess"), "n": y["n"] + (n.get("n") or 0),
            "from": r.get("from"), "to": r.get("to")}
