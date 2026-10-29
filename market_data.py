"""Your watchlist and its prices, from a Google Sheet that uses GOOGLEFINANCE(), set against what the analysts said.

digest.py calls this each run when watchlist_csv is set in digest_config.json:
  read_watchlist()  reads the sheet (published as CSV) or a CSV file on this computer
  market_brief()    joins it with the stock calls in the videos and finds what is worth saying (the insight cards)
  save_market()     writes market-data_YYYY-MM-DD.json next to the digest's JSON file, for the Econova hub

Prices are kept out of video-digest_*.json on purpose: that file holds only what analysts said.
The cards report what analysts said and what prices did. They end with something to look at, never "buy" or "sell".

Coverage check (the first step in the E2E plan): how often were your stocks mentioned lately, and with what view?
    python market_data.py --coverage              the last 14 days, for the stocks in your watchlist sheet
    python market_data.py --coverage --days 28 --tickers NVDA,AAPL
Standard library only.
"""
import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from digest_export import build_payload, load_tickers, norm, number, resolve_ticker, stamp, text, validate, view

HERE = Path(__file__).resolve().parent
SCHEMA_FILE = HERE / "market_schema.json"
SCHEMA_VERSION = "1.0"
SOURCE = ("Google Finance, through GOOGLEFINANCE() in a Google Sheet. Prices can be delayed by up to 20 minutes "
          "and are for information only, not for trading.")
BIG_MOVE = 5.0    # a week's price change, in %, that counts as a big move
MAX_CARDS = 5     # cards in the email; the "no new views" line comes on top
COLUMNS = {"role": "role", "ticker": "ticker", "name": "name", "price": "price", "currency": "currency",
           "change % (day)": "change_pct_day", "close a week ago": "close_week_ago", "change % (week)": "change_pct_week",
           "52-week high": "high_52w", "52-week low": "low_52w", "p/e": "pe", "market cap": "market_cap"}
NUMBERS = ("price", "change_pct_day", "close_week_ago", "change_pct_week", "high_52w", "low_52w", "pe", "market_cap")


class MarketDataError(RuntimeError):
    """The watchlist could not be read, or it has no prices."""


# ---------------------------------------------------------------- 1. read the sheet

def fetch_csv(source):
    """The sheet as CSV text, from its published link or from a file on this computer."""
    if not re.match(r"https?://", source):
        try:
            return Path(source).expanduser().read_text(encoding="utf-8-sig")
        except OSError as err:
            raise MarketDataError(f"could not read {source}: {err}")
    req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8-sig", "replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
            if attempt == 2:
                raise MarketDataError(f"could not download the watchlist sheet: {err}")
            time.sleep(2 * (attempt + 1))


def cell_number(value):
    """A number from a sheet cell as shown, such as "1,234.5", "-0.99", "12%" or "$61.82"; None for "#N/A" or empty."""
    return number(re.sub(r"[%$\s]", "", text(value)))


def read_watchlist(source):
    """{"watchlist": [rows], "benchmarks": {"sp500": ..., "us10y": ...}} from the sheet. Raises MarketDataError."""
    raw = fetch_csv(source)
    if raw.lstrip().startswith("<"):
        raise MarketDataError("the link gave a web page, not CSV. In the sheet use File > Share > Publish to web, "
                              "choose Comma-separated values (.csv), and use that link")
    watchlist, benchmarks = [], {}
    for row in csv.DictReader(io.StringIO(raw)):
        r = {COLUMNS[k.strip().lower()]: v for k, v in row.items() if k and k.strip().lower() in COLUMNS}
        symbol = text(r.get("ticker")).upper()
        if not symbol:
            continue
        values = {k: cell_number(r.get(k)) for k in NUMBERS}
        role = text(r.get("role")).lower() or "watch"
        if role == "sp500" and values["price"] is not None:
            benchmarks["sp500"] = {"value": values["price"], "change_pct_day": values["change_pct_day"],
                                   "change_pct_week": values["change_pct_week"]}
        elif role == "us10y" and values["price"] is not None:
            # Google Finance quotes the CBOE 10-year index (TNX) as the yield times 10: 49.72 means 4.972%.
            y = values["price"] / 10 if values["price"] > 20 else values["price"]
            benchmarks["us10y"] = {"value": round(y, 3), "unit": "%", "change_pct_day": values["change_pct_day"]}
        elif role == "watch":
            watchlist.append({"ticker": symbol.split(":")[-1], "name": text(r.get("name")) or symbol.split(":")[-1],
                              "currency": text(r.get("currency")) or None, **{k: values[k] for k in NUMBERS if k != "close_week_ago"}})
    if not watchlist:
        raise MarketDataError("the sheet has no rows with Role 'watch'")
    if all(w["price"] is None for w in watchlist):
        raise MarketDataError("the sheet has no prices yet. Open it once in the browser so GOOGLEFINANCE() loads")
    return {"watchlist": watchlist, "benchmarks": benchmarks}


# ---------------------------------------------------------------- 2. what the analysts said

def aliases(ticker, name, table):
    """Lower-case names that mean this stock in a sentence: its entries in tickers.json and the sheet's name."""
    # The ticker itself is matched separately, in capitals, so "mu" in a sentence is not taken for Micron.
    names = {k for k, v in table.items() if v == ticker and k != ticker.lower() and len(k) >= 4}
    first = norm(name).split(" ")[0] if name else ""
    if len(first) > 3:
        names.add(first)   # "nvidia corp" -> "nvidia"
    return names


def history(cache_dir, table, day, days=14):
    """Stock calls in the videos published in the `days` days up to `day`, from the saved notes:
    {ticker: [(date, view)]}. Each saved notes file is one video."""
    since = (day - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    until = day.strftime("%Y-%m-%d")
    calls = {}
    for path in Path(cache_dir).glob("*.json"):
        try:
            notes = json.loads(path.read_text(encoding="utf-8"))
            date = text(notes["_video"].get("published"))[:10]
        except (OSError, ValueError, KeyError, AttributeError):
            continue
        if not since <= date <= until:
            continue
        for s in notes.get("stocks", []):
            ticker = resolve_ticker(text(s.get("name")) or text(s.get("ticker")), s.get("ticker"), table)
            if ticker:
                calls.setdefault(ticker, []).append((date, view(s.get("view"))))
    return calls


def tally(views):
    out = {"bullish": 0, "bearish": 0, "neutral": 0, "mixed": 0}
    for v in views:
        out[v] += 1
    return out


def mood(counts):
    """Bullish share of bullish + bearish calls, as in the hub's analyst mood; None with no such calls."""
    n = counts["bullish"] + counts["bearish"]
    return round(counts["bullish"] / n, 2) if n else None


# ---------------------------------------------------------------- 3. what is worth saying

def market_brief(day, prices, done, cache_dir, table=None, now=None):
    """The market-data file's content: the watchlist with prices and analyst calls, and the insight cards.
    done is the digest's videos ({"video", "notes"}), numbered #1, #2... as in the email."""
    table = table if table is not None else load_tickers()
    digest, _ = build_payload(day, done, {}, table)
    videos = {v["number"]: v for v in digest["videos"]}
    link = lambda n, ts: (f"{videos[n]['url']}&t={secs(ts)}s" if ts else videos[n]["url"]) if n in videos else None
    past = history(cache_dir, table, day, 14)
    week_start = (day - timedelta(days=6)).strftime("%Y-%m-%d")
    bench = prices["benchmarks"]
    cards, quiet, rows = [], [], []

    for w in prices["watchlist"]:
        t = w["ticker"]
        today = [m for m in digest["mentions"] if m["ticker"] == t]
        this_week = tally(v for d, v in past.get(t, []) if d >= week_start)
        last_week = tally(v for d, v in past.get(t, []) if d < week_start)
        rows.append(dict(w, calls_today=tally(m["view"] for m in today), calls_7d=this_week, mood_7d=mood(this_week)))
        if not today:
            quiet.append(t)

        # Experts vs price: the week's calls lean one way, and the price went the other way by 5% or more
        m7, move = mood(this_week), w.get("change_pct_week")
        calls7 = this_week["bullish"] + this_week["bearish"]
        if m7 is not None and calls7 >= 2 and move is not None:
            if m7 >= 2 / 3 and move <= -BIG_MOVE:
                cards.append(card("experts_vs_price", [t], f"Experts stayed bullish on {t} ({this_week['bullish']} of {calls7} calls this week), "
                                  f"but the stock fell {abs(move):.1f}% this week.", "Check what changed since last week: news, guidance, earnings."))
            elif m7 <= 1 / 3 and move >= BIG_MOVE:
                cards.append(card("experts_vs_price", [t], f"Experts leaned bearish on {t} ({this_week['bearish']} of {calls7} calls this week), "
                                  f"but the stock rose {move:.1f}% this week.", "Read the bear case against the move."))

        # Sentiment shift: this week's mood is a third or more away from last week's
        m_prev, calls_prev = mood(last_week), last_week["bullish"] + last_week["bearish"]
        if m7 is not None and m_prev is not None and calls7 >= 2 and calls_prev >= 2 and abs(m7 - m_prev) >= 0.34:
            word = "cautious" if m7 < m_prev else "more positive"
            cards.append(card("sentiment_shift", [t], f"Experts turned {word} on {t}: {this_week['bullish']} of {calls7} calls bullish this week, "
                              f"against {last_week['bullish']} of {calls_prev} the week before.", "Watch this week's clips to see what changed their minds."))

        # Split today: at least one bullish and one bearish call in today's videos
        bull = next((m for m in today if m["view"] == "bullish"), None)
        bear = next((m for m in today if m["view"] == "bearish"), None)
        if bull and bear:
            counts = tally(m["view"] for m in today)
            cards.append(card("split", [t], f"Experts split on {t} today: {counts['bullish']} bullish, {counts['bearish']} bearish.",
                              f"Hear both sides: video #{bull['video']} [{bull['timestamp'] or 'start'}] and video #{bear['video']} [{bear['timestamp'] or 'start'}].",
                              bull["video"], bull["timestamp"], link(bull["video"], bull["timestamp"])))
        elif today:
            first = today[0]
            counts = tally(m["view"] for m in today)
            said = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
            cards.append(card("new_views", [t], f"{t}: {len(today)} new call{'s' if len(today) != 1 else ''} today ({said}). "
                              f"First: {first['reason'] or first['view']}" + (f" ({first['analyst']})." if first["analyst"] else "."),
                              f"Watch the clip: video #{first['video']} [{first['timestamp'] or 'start'}].",
                              first["video"], first["timestamp"], link(first["video"], first["timestamp"])))

        # A catalyst for this stock among today's "Coming up"
        names = aliases(t, w.get("name"), table)
        for ev in digest["upcoming"]:
            said = ev["event"].lower()
            if re.search(rf"\b{re.escape(t)}\b", ev["event"]) or any(re.search(rf"\b{re.escape(a)}\b", said) for a in names):
                when = ev["date"] or ev["date_text"] or "date not given"
                cards.append(card("catalyst", [t], f"{t}: '{ev['event']}' ({when}) was flagged in video #{ev['videos'][0]}.",
                                  "Note the date and look at the position before it.", ev["videos"][0], None, link(ev["videos"][0], None)))

    # Market-wide: S&P 500 targets against today's level, and 10-year concern levels against today's yield
    sp = bench.get("sp500")
    if sp:
        for v in digest["videos"]:
            who = v["speakers"][0]["name"] if v["speakers"] else f"Video #{v['number']}"
            for target in v["sp500_targets"]:
                up = (target["value"] / sp["value"] - 1) * 100
                cards.append(card("target_upside", [], f"{who}'s {target['horizon']} S&P 500 target of {target['value']:,.0f} is "
                                  f"{up:+.1f}% from today's level ({sp['value']:,.0f}).", "Compare it with the other targets in today's videos.",
                                  v["number"], None, link(v["number"], None)))
    tenyr = bench.get("us10y")
    if tenyr:
        for l in digest["levels"]:
            about = f"{l['metric']} {l['note']}".lower()
            if l["value"] is not None and l["unit"] == "%" and re.search(r"10[- ]?y(ea)?r|ten[- ]year", about) \
                    and re.search(r"concern|threshold|worr|danger|trouble|pain|break", about):
                gap = round((l["value"] - tenyr["value"]) * 100)
                cards.append(card("rate_headroom", [], f"The 10-year level flagged in video #{l['video']} ({l['display']}) is {gap:+d} bp "
                                  f"from today's yield ({tenyr['value']:.2f}%).", "Keep an eye on the yield as it nears that level.",
                                  l["video"], l["timestamp"], link(l["video"], l["timestamp"])))

    order = ["experts_vs_price", "sentiment_shift", "split", "catalyst", "target_upside", "rate_headroom", "new_views"]
    cards.sort(key=lambda c: order.index(c["type"]))
    cards = cards[:MAX_CARDS]
    if quiet:
        cards.insert(0, card("no_new_views", quiet, f"No new expert views today on {len(quiet)} of your {len(rows)} stocks: {', '.join(quiet)}.",
                             "Nothing to look at for these today."))
    return {
        "schema_version": SCHEMA_VERSION,
        "date": day.strftime("%Y-%m-%d"),
        "generated_at": (now or datetime.now().astimezone()).isoformat(timespec="seconds"),
        "source": SOURCE,
        "benchmarks": {"sp500": bench.get("sp500"), "us10y": bench.get("us10y")},
        "watchlist": rows,
        "insights": cards,
    }


def card(kind, tickers, says, look, video=None, timestamp=None, url=None):
    return {"type": kind, "tickers": tickers, "text": says, "look_at_next": look, "video": video, "timestamp": timestamp, "url": url}


def secs(ts):
    total = 0
    for part in ts.split(":"):
        total = total * 60 + int(part)
    return total


# ---------------------------------------------------------------- 4. save it

def file_name(date):
    return f"market-data_{date}.json"


def save_market(payload, directory, log):
    """Validate, then write market-data_YYYY-MM-DD.json into directory. On any problem nothing is written and the
    reason is logged. Returns the path, or None."""
    date = payload["date"]
    errors = validate(payload, json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))
    if errors:
        log(f"Market data for {date} NOT saved: {len(errors)} schema problem(s): " + "; ".join(errors[:5]))
        return None
    path = Path(directory) / file_name(date)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as err:
        log(f"Market data for {date} NOT saved: could not write {path}: {err}")
        return None
    log(f"Saved {path} ({len(payload['watchlist'])} stocks, {len(payload['insights'])} insights)")
    return path


# ---------------------------------------------------------------- coverage check

def coverage(tickers, cache_dir, day, days=14):
    """Rows of (ticker, calls by view, weeks mentioned) and how many of the stocks came up in every week."""
    table = load_tickers()
    past = history(cache_dir, table, day, days)
    weeks = max(1, days // 7)
    starts = [(day - timedelta(days=7 * (i + 1) - 1)).strftime("%Y-%m-%d") for i in range(weeks)]
    ends = [(day - timedelta(days=7 * i)).strftime("%Y-%m-%d") for i in range(weeks)]
    rows, every_week = [], 0
    for t in tickers:
        calls = past.get(t, [])
        seen = sum(1 for s, e in zip(starts, ends) if any(s <= d <= e for d, _ in calls))
        every_week += seen == weeks
        rows.append((t, tally(v for _, v in calls), seen))
    return rows, every_week, weeks


def main():
    ap = argparse.ArgumentParser(description="Watchlist coverage: how often were your stocks mentioned in the videos lately?")
    ap.add_argument("--coverage", action="store_true", help="count recent mentions of each watchlist stock")
    ap.add_argument("--days", type=int, default=14, help="how many days back (default 14)")
    ap.add_argument("--tickers", help="comma-separated tickers, instead of the watchlist sheet")
    args = ap.parse_args()
    if not args.coverage:
        ap.print_help()
        return
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        cfg = json.loads((HERE / "digest_config.json").read_text(encoding="utf-8"))
        if not cfg.get("watchlist_csv"):
            sys.exit("Set watchlist_csv in digest_config.json, or pass --tickers NVDA,AAPL,...")
        tickers = [w["ticker"] for w in read_watchlist(cfg["watchlist_csv"])["watchlist"]]
    rows, every_week, weeks = coverage(tickers, HERE / "digest_cache", datetime.now(), args.days)
    print(f"Mentions in the videos of the last {args.days} days (from digest_cache)\n")
    print(f"{'Stock':<8}{'Calls':>6}{'Bullish':>9}{'Bearish':>9}{'Neutral':>9}{'Mixed':>7}   Weeks mentioned")
    for t, c, seen in sorted(rows, key=lambda r: -sum(r[1].values())):
        print(f"{t:<8}{sum(c.values()):>6}{c['bullish']:>9}{c['bearish']:>9}{c['neutral']:>9}{c['mixed']:>7}   {seen} of {weeks}")
    print(f"\n{every_week} of {len(tickers)} stocks came up in every week.")
    if every_week * 2 > len(tickers):
        print("Most of your stocks are mentioned every week: the videos are enough to build the insight cards on.")
    else:
        print("Few of your stocks are mentioned every week: add stock-specific sources (analyst interviews, earnings coverage) "
              "first, and use the market summaries for big-picture themes.")


if __name__ == "__main__":
    main()
