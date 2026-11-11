"""Stock prices for your watchlist, your holdings and the stocks the analysts called, fetched by this computer.

No key and no Google Sheet: daily closing prices come from Yahoo Finance's public chart data, or from Stooq when
Yahoo does not answer. They are kept in prices.json in the program folder and refreshed once a day, so the dashboard
and the digests read them without waiting for the internet. Prices can be delayed and are for information only.

    python prices.py NVDA AAPL      fetch these now and print the latest close
Standard library only.
"""
import csv
import io
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "prices.json"
SP500 = "^GSPC"
US10Y = "^TNX"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
MAX_SYMBOLS = 80          # a day's refresh never asks for more than this many
SOURCE = "Yahoo Finance (or Stooq), daily closes. Prices can be delayed and are for information only, not for trading."
SYMBOL = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-]{0,14}$")
_lock = threading.Lock()


class PriceError(RuntimeError):
    pass


def clean(symbol):
    s = str(symbol or "").strip().upper().replace(" ", "")
    return s if SYMBOL.match(s) else ""


# ---------------------------------------------------------------- fetching

def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def from_yahoo(symbol, text=None):
    """{"name", "currency", "closes": [[YYYY-MM-DD, close], ...]} from Yahoo's chart data (a year of daily closes)."""
    if text is None:
        text = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1y&interval=1d")
    data = json.loads(text)
    chart = data.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise PriceError(f"Yahoo has no prices for {symbol}")
    res = chart["result"][0]
    meta = res.get("meta") or {}
    offset = int(meta.get("gmtoffset") or 0)
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    rows = []
    for ts, c in zip(res.get("timestamp") or [], closes):
        if c is None:
            continue
        day = datetime.fromtimestamp(int(ts) + offset, timezone.utc).date().isoformat()
        if rows and rows[-1][0] == day:
            rows[-1][1] = round(float(c), 4)
        else:
            rows.append([day, round(float(c), 4)])
    if not rows:
        raise PriceError(f"Yahoo sent no closing prices for {symbol}")
    return {"name": meta.get("longName") or meta.get("shortName") or "", "currency": meta.get("currency") or "", "closes": rows}


def stooq_symbol(symbol):
    if symbol == SP500:
        return "^spx"
    if symbol.startswith("^"):
        return symbol.lower()
    return symbol.lower() + ("" if "." in symbol else ".us")


def from_stooq(symbol, text=None):
    if text is None:
        text = get(f"https://stooq.com/q/d/l/?s={urllib.parse.quote(stooq_symbol(symbol))}&i=d")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            rows.append([r["Date"], round(float(r["Close"]), 4)])
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        raise PriceError(f"Stooq has no prices for {symbol}")
    cutoff = (date.today() - timedelta(days=370)).isoformat()
    return {"name": "", "currency": "", "closes": [r for r in rows if r[0] >= cutoff]}


def fetch(symbol):
    errors = []
    for source in (from_yahoo, from_stooq):
        try:
            return source(symbol)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, PriceError) as err:
            errors.append(f"{source.__name__[5:]}: {err}")
    raise PriceError(f"no prices for {symbol} ({'; '.join(errors)})")


# ---------------------------------------------------------------- the cache

def load():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(cache):
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    tmp.replace(CACHE)


def refresh(symbols, log=print, fetcher=None, pause=0.3):
    """Fetch what is not already fetched today. Returns (fetched, failed). Never raises: prices are extra."""
    fetcher = fetcher or fetch
    today = date.today().isoformat()
    wanted = list(dict.fromkeys(s for s in (clean(x) for x in [SP500, *symbols]) if s))[:MAX_SYMBOLS]
    with _lock:
        cache = load()
        todo = [s for s in wanted if (cache.get(s) or {}).get("day") != today]
        fetched, failed = [], []
        for s in todo:
            try:
                got = fetcher(s)
                cache[s] = {**got, "day": today}
                fetched.append(s)
            except Exception as err:
                failed.append(s)
                if s == SP500 or len(failed) <= 3:
                    log(f"Prices: {err}")
            if pause:
                time.sleep(pause)
        if fetched:
            save(cache)
    if todo:
        log(f"Prices: {len(fetched)} of {len(todo)} updated" + (f"; not found: {', '.join(failed[:8])}" if failed else ""))
    return fetched, failed


# ---------------------------------------------------------------- reading

def series(symbol, cache=None):
    return ((cache if cache is not None else load()).get(clean(symbol)) or {}).get("closes") or []


def close_on(rows, day):
    """The first close on or after a day (YYYY-MM-DD): the price right after something was said. None if none yet."""
    for d, c in rows:
        if d >= day:
            return d, c
    return None


def latest(rows):
    return rows[-1] if rows else None


def change(rows, sessions):
    """% change over the last N trading sessions, or None."""
    if len(rows) <= sessions:
        return None
    return round((rows[-1][1] / rows[-1 - sessions][1] - 1) * 100, 2)


def quote(symbol, cache=None):
    """The latest price and its changes, or None when this symbol has no prices yet."""
    cache = cache if cache is not None else load()
    entry = cache.get(clean(symbol)) or {}
    rows = entry.get("closes") or []
    if not rows:
        return None
    year = [c for _, c in rows[-252:]]
    return {"ticker": clean(symbol), "name": entry.get("name") or "", "currency": entry.get("currency") or "", "price": rows[-1][1],
            "as_of": rows[-1][0], "change_pct_day": change(rows, 1), "change_pct_week": change(rows, 5),
            "change_pct_month": change(rows, 21), "close_week_ago": rows[-6][1] if len(rows) > 5 else None,
            "high_52w": max(year), "low_52w": min(year),
            "from_high_pct": round((rows[-1][1] / max(year) - 1) * 100, 2)}


def as_watchlist(tickers, cache=None):
    """The same shape market_data.read_watchlist() returns from a sheet, so the digest's watchlist section works the
    same either way: {"watchlist": [rows], "benchmarks": {"sp500": ...}}."""
    cache = cache if cache is not None else load()
    rows = []
    for t in tickers:
        q = quote(t, cache)
        rows.append({"ticker": clean(t), "name": (q or {}).get("name", ""), "currency": (q or {}).get("currency", ""), "role": "watch",
                     **{k: (q or {}).get(k) for k in ("price", "change_pct_day", "close_week_ago", "change_pct_week", "high_52w", "low_52w")},
                     "pe": None, "market_cap": None})
    out = {"watchlist": rows, "benchmarks": {}}
    sp = quote(SP500, cache)
    if sp:
        out["benchmarks"]["sp500"] = {"value": sp["price"], "change_pct_day": sp["change_pct_day"], "change_pct_week": sp["change_pct_week"]}
    return out


def main():
    syms = [clean(s) for s in sys.argv[1:]] or ["NVDA"]
    refresh(syms, pause=0)
    for s in [SP500, *syms]:
        q = quote(s)
        print(f"{s}: " + (f"{q['price']} on {q['as_of']} ({q['change_pct_day']}% on the day)" if q else "no prices"))


if __name__ == "__main__":
    main()
