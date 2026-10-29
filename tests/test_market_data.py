"""Tests for the watchlist and its insight cards (market_data.py). Run from the project folder: python -m unittest -v
The sheet rows are the values Google Finance gave on 29 Oct 2026; no network is used."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import market_data as md
from digest_export import load_tickers

SHEET = """Role,Ticker,Name,Price,Currency,Change % (day),Close a week ago,Change % (week),52-week high,52-week low,P/E,Market cap
watch,NVDA,NVIDIA Corp,213.25,USD,-0.99,212.21,0.49,243.37,164.27,26.99,5137394749450
watch,GOOGL,Alphabet Inc Class A,283.18,USD,-12.84,324.22,-12.66,408.61,270.7,14.77,3448837803598
watch,NASDAQ:MU,Micron Technology Inc,"1,947.63",USD,-3.62,856.49,10.64,1255,192.59,12.79,1072169435384
watch,AAPL,Apple Inc,349.32,USD,1.6%,348.22,0.32,351.73,243.42,40.02,5098039064490
watch,NFLX,Netflix Inc,61.82,USD,-0.27,67.05,-7.8,116.73,61.4,17.87,253976194984
watch,CRWV,CoreWeave Inc,#N/A,USD,,,,,,,
sp500,INDEXSP:.INX,S&P 500,7706.17,,-0.49,7663.43,0.56,,,,
us10y,INDEXCBOE:TNX,US 10-year Treasury yield,49.72,,-1.45,,,,,,
"""
DAY = datetime(2026, 10, 29, 7, 30)
NOW = datetime(2026, 10, 29, 7, 30, tzinfo=timezone.utc)


def write(folder, name, content):
    path = Path(folder) / name
    path.write_text(content, encoding="utf-8")
    return path


def stock(name, view, seconds=53, analyst=""):
    return {"name": name, "ticker": "", "view": view, "reason": "because", "analyst": analyst, "time": md.stamp(seconds), "seconds": seconds}


def notes(**extra):
    base = {"summary": "s", "speakers": [], "key_points": [], "market_levels": [], "stocks": [], "sectors_and_themes": [],
            "predictions": [], "risks": [], "upcoming_events": [], "sp500_targets": []}
    base.update(extra)
    return base


def video(n, days_ago=0):
    published = (DAY - timedelta(days=days_ago)).strftime("%Y-%m-%dT10:00:00+00:00")
    return {"id": f"vid{n:08d}", "title": f"Video {n}", "channel": "TheStreet", "published": published,
            "url": f"https://www.youtube.com/watch?v=vid{n:08d}", "duration": 1404}


class ReadSheet(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_rows_and_benchmarks(self):
        data = md.read_watchlist(str(write(self.dir, "sheet.csv", SHEET)))
        tickers = [w["ticker"] for w in data["watchlist"]]
        self.assertEqual(tickers, ["NVDA", "GOOGL", "MU", "AAPL", "NFLX", "CRWV"])   # "NASDAQ:MU" becomes MU
        mu = data["watchlist"][2]
        self.assertEqual(mu["price"], 1947.63)                      # "1,947.63"
        self.assertEqual(data["watchlist"][3]["change_pct_day"], 1.6)   # "1.6%"
        self.assertIsNone(data["watchlist"][5]["price"])              # "#N/A"
        self.assertEqual(data["benchmarks"]["sp500"]["value"], 7706.17)
        self.assertEqual(data["benchmarks"]["us10y"]["value"], 4.972)   # TNX is quoted as the yield times 10

    def test_problems_are_explained(self):
        page = write(self.dir, "page.csv", "<!DOCTYPE html><html>Sign in</html>")
        with self.assertRaisesRegex(md.MarketDataError, "Publish to web"):
            md.read_watchlist(str(page))
        empty = write(self.dir, "empty.csv", "Role,Ticker,Price\nwatch,NVDA,\nwatch,AAPL,#N/A\n")
        with self.assertRaisesRegex(md.MarketDataError, "no prices yet"):
            md.read_watchlist(str(empty))
        with self.assertRaisesRegex(md.MarketDataError, "could not read"):
            md.read_watchlist(str(Path(self.dir) / "missing.csv"))


class Brief(unittest.TestCase):
    def setUp(self):
        self.cache = Path(tempfile.mkdtemp())
        self.prices = md.read_watchlist(str(write(self.cache.parent, f"sheet-{id(self)}.csv", SHEET)))
        self.done = [
            {"video": video(1), "notes": notes(
                speakers=[{"name": "Sam Stovall", "role": "CFRA"}],
                sp500_targets=[{"value": 8050, "horizon": "year-end"}],
                market_levels=[{"item": "10-year yield concern threshold", "value": "5.45%", "number": 5.45, "unit": "%",
                                "context": "where stocks get seriously concerned", "time": "19:44", "seconds": 1184}],
                upcoming_events=[{"event": "Nvidia earnings", "when": "November 19", "date": "2026-11-19", "time": "1:00", "seconds": 60}],
                stocks=[stock("Apple", "bullish")])},
            {"video": video(2), "notes": notes(stocks=[stock("Nvidia", "bullish", 120, "James Demmert"), stock("NVDA", "bearish", 300)])},
        ]
        # The week before: Netflix and Alphabet were liked; this week Netflix turned, Alphabet stayed liked
        self.save(10, 9, [stock("Netflix", "bullish"), stock("Netflix", "bullish"), stock("Netflix", "bullish")])
        self.save(11, 3, [stock("Netflix", "bearish"), stock("Netflix", "bearish"), stock("Alphabet", "bullish"), stock("Google", "bullish")])
        for n, d in enumerate(self.done, 1):   # today's videos are in the saved notes too, as after extract()
            self.save(n, 0, d["notes"]["stocks"])

    def save(self, n, days_ago, stocks):
        v = video(n, days_ago)
        (self.cache / f"{v['id']}.json").write_text(json.dumps(dict(notes(stocks=stocks), _video=v)), encoding="utf-8")

    def brief(self):
        return md.market_brief(DAY, self.prices, self.done, self.cache, load_tickers(), now=NOW)

    def test_cards(self):
        b = self.brief()
        kinds = [c["type"] for c in b["insights"]]
        self.assertEqual(kinds[0], "no_new_views")
        self.assertEqual(b["insights"][0]["tickers"], ["GOOGL", "MU", "NFLX", "CRWV"])
        texts = " | ".join(c["text"] for c in b["insights"])
        self.assertIn("Experts stayed bullish on GOOGL (2 of 2 calls this week), but the stock fell 12.7% this week.", texts)
        self.assertIn("Experts turned cautious on NFLX: 0 of 2 calls bullish this week, against 3 of 3 the week before.", texts)
        self.assertIn("Experts split on NVDA today: 1 bullish, 1 bearish.", texts)
        self.assertIn("NVDA: 'Nvidia earnings' (2026-11-19) was flagged in video #1.", texts)
        self.assertLessEqual(len(b["insights"]), md.MAX_CARDS + 1)
        for c in b["insights"]:
            self.assertNotRegex(c["look_at_next"].lower(), r"\b(buy|sell)\b")

    def test_market_wide_cards_and_links(self):
        md.MAX_CARDS, saved = 20, md.MAX_CARDS
        try:
            b = self.brief()
        finally:
            md.MAX_CARDS = saved
        texts = {c["type"]: c for c in b["insights"]}
        self.assertEqual(texts["target_upside"]["text"], "Sam Stovall's year-end S&P 500 target of 8,050 is +4.5% from today's level (7,706).")
        self.assertEqual(texts["rate_headroom"]["text"], "The 10-year level flagged in video #1 (5.45%) is +48 bp from today's yield (4.97%).")
        self.assertEqual(texts["rate_headroom"]["url"], "https://www.youtube.com/watch?v=vid00000001&t=1184s")
        self.assertEqual(texts["split"]["url"], "https://www.youtube.com/watch?v=vid00000002&t=120s")

    def test_watchlist_rows_and_schema(self):
        b = self.brief()
        schema = json.loads(md.SCHEMA_FILE.read_text(encoding="utf-8"))
        self.assertEqual(md.validate(b, schema), [])
        nvda = next(w for w in b["watchlist"] if w["ticker"] == "NVDA")
        self.assertEqual(nvda["calls_today"], {"bullish": 1, "bearish": 1, "neutral": 0, "mixed": 0})
        self.assertEqual(next(w for w in b["watchlist"] if w["ticker"] == "NFLX")["mood_7d"], 0.0)
        self.assertEqual(b["benchmarks"]["us10y"], {"value": 4.972, "unit": "%", "change_pct_day": -1.45})

    def test_no_videos_today(self):
        b = md.market_brief(DAY, self.prices, [], self.cache, load_tickers(), now=NOW)
        self.assertEqual(b["insights"][0]["tickers"], ["NVDA", "GOOGL", "MU", "AAPL", "NFLX", "CRWV"])
        self.assertEqual(md.validate(b, json.loads(md.SCHEMA_FILE.read_text(encoding="utf-8"))), [])

    def test_save(self):
        logs = []
        path = md.save_market(self.brief(), self.cache / "out", logs.append)
        self.assertEqual(path.name, "market-data_2026-10-29.json")
        bad = dict(self.brief(), watchlist="oops")
        self.assertIsNone(md.save_market(bad, self.cache / "out2", logs.append))
        self.assertFalse((self.cache / "out2").exists())
        self.assertIn("NOT saved", logs[-1])

    def test_coverage(self):
        rows, every_week, weeks = md.coverage(["NFLX", "GOOGL", "AAPL", "TSLA"], self.cache, DAY, 14)
        counts = {t: (sum(c.values()), seen) for t, c, seen in rows}
        self.assertEqual(weeks, 2)
        self.assertEqual(counts, {"NFLX": (5, 2), "GOOGL": (2, 1), "AAPL": (1, 1), "TSLA": (0, 0)})
        self.assertEqual(every_week, 1)


if __name__ == "__main__":
    unittest.main()
