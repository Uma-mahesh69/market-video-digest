"""Example data for trying the product without any keys: invented analysts, invented calls and invented prices for
well-known tickers. It fills the local Firebase emulator (and the tests) through the real engine, so every page shows
what real data would. Nothing here is real, and the pages that show it say so.

    FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=demo-md python cloud/tools/demo_data.py
"""
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from cloud.engine import run as engine  # noqa: E402

STOCKS = [  # ticker, name, sector, start price, drift a day (%), swing a day (%), market cap ($bn), P/E, dividend %
    ("NVDA", "Nvidia", "Technology", 172, 0.28, 2.2, 4400, 48, 0.02), ("AAPL", "Apple", "Technology", 265, 0.10, 1.2, 4100, 33, 0.4),
    ("MSFT", "Microsoft", "Technology", 540, 0.07, 1.1, 4000, 35, 0.7), ("GOOGL", "Alphabet", "Communication", 250, 0.12, 1.5, 3100, 27, 0.3),
    ("AMZN", "Amazon", "Consumer", 280, 0.11, 1.6, 3000, 38, 0), ("META", "Meta Platforms", "Communication", 760, 0.09, 1.8, 1900, 28, 0.3),
    ("TSLA", "Tesla", "Consumer", 250, -0.30, 3.0, 610, 95, 0), ("AVGO", "Broadcom", "Technology", 440, 0.15, 2.0, 2100, 41, 0.6),
    ("AMD", "AMD", "Technology", 210, 0.05, 2.6, 340, 44, 0), ("ORCL", "Oracle", "Technology", 250, -0.35, 2.1, 400, 30, 0.9),
    ("JPM", "JPMorgan Chase", "Financials", 250, 0.08, 1.1, 720, 14, 2.0), ("BAC", "Bank of America", "Financials", 48, 0.05, 1.3, 370, 13, 2.2),
    ("GS", "Goldman Sachs", "Financials", 690, 0.10, 1.4, 215, 15, 1.8), ("LLY", "Eli Lilly", "Health", 890, 0.02, 1.7, 840, 42, 0.7),
    ("UNH", "UnitedHealth", "Health", 360, -0.12, 1.9, 330, 17, 2.4), ("PFE", "Pfizer", "Health", 27, -0.06, 1.3, 150, 12, 6.3),
    ("COST", "Costco", "Consumer", 960, 0.03, 1.0, 430, 50, 0.5), ("WMT", "Walmart", "Consumer", 104, 0.06, 0.9, 830, 37, 0.9),
    ("KO", "Coca-Cola", "Consumer", 70, 0.01, 0.8, 300, 25, 2.9), ("DIS", "Disney", "Communication", 112, -0.04, 1.5, 200, 20, 0.9),
    ("PLTR", "Palantir", "Technology", 150, 0.25, 3.4, 420, 210, 0), ("INTC", "Intel", "Technology", 36, -0.10, 2.8, 160, None, 0),
    ("XOM", "Exxon Mobil", "Energy", 116, 0.02, 1.2, 500, 15, 3.4), ("NFLX", "Netflix", "Communication", 1150, 0.06, 1.9, 490, 45, 0),
]
ANALYSTS = [  # name, firm, how often their call matches what the price then does
    ("Maya Chen", "Northgate Capital", 0.82), ("Daniel Ortiz", "Halden Research", 0.70), ("Priya Raman", "Blue Harbor Partners", 0.64),
    ("Tom Becker", "Kestrel Advisors", 0.55), ("Sara Lindqvist", "Alder & Co", 0.50), ("James Okafor", "Meridian Street", 0.42),
    ("Elena Rossi", "Tessera Partners", 0.60), ("Ken Watanabe", "Sumida Securities", 0.33),
]
CHANNELS = ["Example Markets TV", "Example Business Daily", "Example Finance Live"]
BULL = ["Demand is running ahead of supply and margins are widening", "Earnings estimates keep moving up and the valuation has not caught up",
        "The new product cycle is stronger than the market expects", "Cash flow is growing and buybacks are accelerating",
        "It is taking share from rivals in its biggest market", "Pricing power is holding even as costs fall"]
BEAR = ["Growth is slowing while the valuation still assumes it will not", "Margins are under pressure from rising costs",
        "Competition is cutting prices and it is losing share", "Guidance was cut and estimates still look too high",
        "Capital spending is climbing faster than revenue", "Regulatory risk is growing and is not in the price"]


def trading_days(end, n):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def make(today=None, seed=7):
    """({video id: notes}, {symbol: {"name", "currency", "closes"}}, {ticker: TipRanks-style record})"""
    today = today or date.today()
    rng = random.Random(seed)
    days = trading_days(today - timedelta(days=1 if today.weekday() != 0 else 3), 250)
    closes = {}
    for t, name, _, start, drift, swing, *_ in STOCKS:
        price, rows = start * (1 - drift * 2.2), []
        for d in days:
            price *= 1 + (drift + rng.gauss(0, swing)) / 100
            rows.append([d.isoformat(), round(price, 2)])
        closes[t] = {"name": name, "currency": "USD", "closes": rows}
    level, rows = 6100.0, []
    for d in days:
        level *= 1 + (0.05 + rng.gauss(0, 0.7)) / 100
        rows.append([d.isoformat(), round(level, 2)])
    closes["^GSPC"] = {"name": "S&P 500", "currency": "USD", "closes": rows}

    def ahead(t, i, span=15):   # the stock against the S&P 500 over the next span days: what a good analyst "sees"
        r, m = closes[t]["closes"], closes["^GSPC"]["closes"]
        j = min(len(r) - 1, i + span)
        return (r[j][1] / r[i][1]) - (m[j][1] / m[i][1])

    notes, n = {}, 0
    for i in range(len(days) - 85, len(days)):
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            n += 1
            who, firm, skill = rng.choice(ANALYSTS)
            picks = rng.sample(STOCKS, rng.choice([2, 3, 3, 4]))
            stocks = []
            for s in picks:
                up = ahead(s[0], i) > 0
                right = rng.random() < skill
                view = ("bullish" if up == right else "bearish") if rng.random() > 0.12 else rng.choice(["neutral", "mixed"])
                reason = rng.choice(BULL if view == "bullish" else BEAR) if view in ("bullish", "bearish") else "Good and bad points roughly cancel out for now"
                stocks.append({"name": s[1], "ticker": s[0], "view": view, "reason": reason + ".", "analyst": who, "seconds": rng.randint(30, 700)})
            when = datetime(days[i].year, days[i].month, days[i].day, rng.randint(12, 21), rng.randint(0, 59), tzinfo=timezone.utc)
            vid = f"demo{n:07d}"
            events = []
            if rng.random() < 0.15:
                e = rng.choice(["Fed rate decision", "CPI inflation report", "Jobs report", "Retail sales data"])
                events.append({"event": e, "when": "next week", "date": (days[i] + timedelta(days=rng.randint(6, 16))).isoformat(), "seconds": 60})
            notes[vid] = {"summary": f"{who} of {firm} on {', '.join(s[1] for s in picks[:3])} and where the market goes next.",
                          "speakers": [{"name": who, "role": firm}], "key_points": [], "market_levels": [], "stocks": stocks,
                          "sectors_and_themes": [], "predictions": [], "risks": [], "sp500_targets": [], "upcoming_events": events,
                          "_video": {"id": vid, "title": f"{who}: {rng.choice(['Where I would put money now', 'What the market is missing', 'My top calls this week', 'Reading the latest earnings'])}",
                                     "channel": rng.choice(CHANNELS), "published": when.isoformat(), "url": f"https://www.youtube.com/watch?v={vid}"}}

    street = {}
    for k, (t, name, sector, _, drift, _, cap, pe, div) in enumerate(STOCKS):
        price = closes[t]["closes"][-1][1]
        lean = drift * 3 + rng.gauss(0, 0.25)
        consensus = "StrongBuy" if lean > 0.5 else "ModerateBuy" if lean > 0.1 else "Hold" if lean > -0.4 else "ModerateSell"
        upside = round(max(-0.2, min(0.45, lean * 0.3 + rng.gauss(0.06, 0.05))), 3)
        street[t] = {"ticker": t, "companyName": name, "sector": sector, "marketCap": cap * 1e9, "price": price,
                     "smartScore": max(1, min(10, round(6 + lean * 5))), "analystConsensus": consensus,
                     "bestAnalystConsensus": consensus if rng.random() < 0.7 else "ModerateBuy",
                     "priceTarget": round(price * (1 + upside), 2), "priceTargetUpside": upside, "peRatio": pe, "dividendYield": div,
                     "newsSentiment": round(max(0.05, min(0.95, 0.5 + lean * 0.4)), 2), "hedgeFundsScore": round(max(0.05, min(0.95, 0.5 + lean * 0.3 + rng.gauss(0, 0.1))), 2),
                     "insiderScore": round(max(0.05, min(0.95, 0.5 + rng.gauss(0, 0.2))), 2), "ytdGainPct": round(drift * 220 + rng.gauss(0, 6), 1),
                     "yearlyGainPct": round(drift * 250 + rng.gauss(0, 8), 1),
                     "nextEarningsDate": (today + timedelta(days=3 + k * 2 % 40)).isoformat(), "daysUntilEarnings": 3 + k * 2 % 40,
                     "url": f"https://www.tipranks.com/stocks/{t.lower()}"}
    return notes, closes, street


class FakeTipRanks:
    """Answers like TipRanks' MCP server, from the invented records."""

    def __init__(self, street, remaining=48):
        self.street, self.remaining, self.calls = street, remaining, 0

    def start(self):
        pass

    def tools(self):
        return [{"name": "get_assets_data", "inputSchema": {"properties": {"tickers": {"type": "string"}}}}, {"name": "get_my_usage"}]

    def call(self, name, args):
        if name == "get_my_usage":
            return {"structuredContent": {"limit": 50, "remaining": self.remaining, "used": 50 - self.remaining}}
        self.calls += 1
        self.remaining -= 1
        return {"structuredContent": {"assetsData": [self.street[t] for t in args["tickers"].split(",") if t in self.street]}}


DEMO_USER = {"email": "you@example.com", "name": "Sample Investor", "onboarded": True, "prefs": {"daily": "every", "weekly": True},
             "stocks": [{"t": "NVDA", "shares": 20, "cost": 150}, {"t": "AAPL", "shares": 15, "cost": 210}, {"t": "TSLA", "shares": 8, "cost": 310},
                        {"t": "JPM", "shares": 10, "cost": 230}, {"t": "ORCL"}, {"t": "MSFT"}, {"t": "PLTR"}, {"t": "LLY"}]}


def fill(store, today=None, work=None, log=print):
    """Put the invented notes in the store and run the real engine over them."""
    today = today or date.today()
    notes, closes, street = make(today)
    for vid, n in notes.items():
        store.set("videos", vid, {"published": n["_video"]["published"], "channel": n["_video"]["channel"], "title": n["_video"]["title"],
                                  "notes": json.dumps(n, separators=(",", ":"))})
    store.set("users", "demo-user", DEMO_USER)
    store.set("members", DEMO_USER["email"], {"email": DEMO_USER["email"], "added": today.isoformat()})   # the private beta
    sources = engine.load_sources()
    sources["base_tickers"] = [s[0] for s in STOCKS]
    sources["analysts"] = [a[0] for a in ANALYSTS[:3]]
    sources["channels"] = [{"name": c, "url": ""} for c in CHANNELS]
    sources["limits"]["tipranks_calls_per_day"] = 5
    now = datetime(today.year, today.month, today.day, 12, tzinfo=timezone.utc)
    if today.weekday() >= 5:   # ratings are not fetched at weekends: pretend it is Friday for them
        now -= timedelta(days=today.weekday() - 4)

    def fetch(symbol):
        if symbol not in closes:
            raise engine.prices.PriceError(f"no example prices for {symbol}")
        return closes[symbol]
    return engine.run(store, {"site": "http://localhost:5000/"}, sources=sources, now=now, log=log, work=work, read_videos=False,
                      price_fetcher=fetch, tipranks_client=FakeTipRanks(street))


if __name__ == "__main__":
    import tempfile
    from cloud.engine.store import FirestoreStore
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(fill(FirestoreStore(), work=tmp), indent=1))
