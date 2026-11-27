"""What the money says: the odds that people betting real money give the big market events, from Kalshi.

Kalshi is a US exchange for event contracts, regulated by the CFTC. Its market data is public (no key, no account):
a contract that pays $1 if something happens and trades at $0.70 means the market gives it about a 70% chance. These
odds sit next to what the experts say on TV: a view backed by money, scored every day by the price.

Read once a day, four small requests. If Kalshi cannot be reached, the last odds stay and say when they were read."""
import json
import urllib.request
from datetime import datetime, timezone

URL = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={}&status=open&limit=200"
SOURCE = "Kalshi"
# (key, series, what it is). Each gives the soonest open event of the series.
SERIES = [
    ("fed", "KXFEDDECISION", "The Fed's next rate decision"),
    ("cpi", "KXCPI", "Inflation (CPI), the next monthly reading"),
    ("jobs", "KXPAYROLLS", "Jobs added, the next monthly report"),
    ("recession", "KXRECSSNBER", "A US recession next year"),
]


def fetch(series, timeout=20):
    req = urllib.request.Request(URL.format(series), headers={"User-Agent": "econova-engine/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")).get("markets") or []


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def chance(m):
    """The market's odds that it happens, 0 to 100: the middle of the best bid and ask when the spread is tight,
    else the last trade. None when there is nothing to go on."""
    bid = _num(m.get("yes_bid_dollars", (m.get("yes_bid") or 0) / 100 if m.get("yes_bid") is not None else None))
    ask = _num(m.get("yes_ask_dollars", (m.get("yes_ask") or 0) / 100 if m.get("yes_ask") is not None else None))
    last = _num(m.get("last_price_dollars", (m.get("last_price") or 0) / 100 if m.get("last_price") is not None else None))
    if bid is not None and ask and ask - bid <= 0.12:
        return round(100 * (bid + ask) / 2)
    if last:
        return round(100 * last)
    return None


def soonest(markets, now, latest=False):
    """The markets of the soonest event that has not closed yet (or, with `latest`, the furthest one: next year's
    recession rather than a year that is nearly over)."""
    by = {}
    for m in markets:
        if str(m.get("close_time") or "") >= now.isoformat()[:19]:
            by.setdefault(m.get("event_ticker"), []).append(m)
    if not by:
        return []
    pick = max if latest else min
    return by[pick(by, key=lambda e: min(str(m.get("close_time")) for m in by[e]))]


def outcomes(markets):
    """[{label, pct}] for an event, most likely first. For "above X" ladders (CPI, jobs) the odds of each step."""
    rows = [{"label": str(m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or "")[:60], "pct": chance(m)} for m in markets]
    rows = [r for r in rows if r["pct"] is not None and r["label"]]
    return sorted(rows, key=lambda r: -r["pct"])


def ladder(rows):
    """From an "above X" ladder, the few steps that tell the story: very likely, a coin toss, unlikely."""
    out = []
    for target in (85, 50, 15):
        best = min(rows, key=lambda r: abs(r["pct"] - target))
        if best not in out and abs(best["pct"] - target) <= 20:
            out.append(best)
    return sorted(out, key=lambda r: -r["pct"])


def event_of(key, series, what, markets, now):
    ms = soonest(markets, now, latest=key == "recession")
    if not ms:
        return None
    rows = outcomes(ms)
    if not rows:
        return None
    close = min(str(m.get("close_time") or "") for m in ms)[:10]
    title = str(ms[0].get("title") or what)
    if key in ("cpi", "jobs"):   # a ladder of "above X": the steps people can read
        rows = ladder(rows)
    else:
        rows = [r for r in rows if r["pct"] >= 1][:4]
    if key == "recession" and len(ms) == 1:
        rows = [{"label": "Yes", "pct": chance(ms[0])}]
    return {"key": key, "what": what, "title": title[:140], "closes": close, "rows": rows, "event": ms[0].get("event_ticker"),
            "link": f"https://kalshi.com/markets/{series.lower()}"}


def read(now=None, fetcher=fetch, log=print):
    """{"events": [...], "at", "source"}; None when nothing could be read."""
    now = now or datetime.now(timezone.utc)
    events = []
    for key, series, what in SERIES:
        try:
            e = event_of(key, series, what, fetcher(series), now)
            if e:
                events.append(e)
        except Exception as err:   # one series failing must not lose the others
            log(f"Odds: {series} not read ({type(err).__name__}: {str(err)[:100]})")
    if not events:
        return None
    return {"events": events, "at": now.isoformat(timespec="minutes"), "source": SOURCE}
