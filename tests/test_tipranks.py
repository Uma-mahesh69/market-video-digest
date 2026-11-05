"""Tests for tipranks.py: the daily TipRanks call stays inside the free tier and is saved for the dashboard.
No network: a fake client stands in for TipRanks. Run from the project folder: python -m unittest -v"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import tipranks as tr

DAY = datetime(2026, 11, 5, 7, 30)
TOOL = {"name": "get_assets_data", "inputSchema": {"properties": {"tickers": {"type": "string", "description": "comma separated"}}}}


class Fake:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def start(self):
        pass

    usage = {"tier": "free", "limit": 50, "remaining": 50}

    def tools(self):
        return [TOOL, {"name": "get_my_usage"}]

    def call(self, name, arguments):
        if name == "get_my_usage":
            return {"content": [{"type": "text", "text": json.dumps(self.usage)}]}
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": json.dumps(self.answer)}]}


class Reading(unittest.TestCase):
    def test_event_stream_and_json_answers(self):
        sse = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
        self.assertEqual(tr.Client._answer(sse, "text/event-stream"), {"tools": []})
        self.assertEqual(tr.Client._answer('{"jsonrpc":"2.0","id":2,"result":{"ok":1}}', "application/json"), {"ok": 1})
        with self.assertRaises(tr.TipRanksError):
            tr.Client._answer('{"jsonrpc":"2.0","id":3,"error":{"message":"bad key"}}')

    def test_fields_found_in_another_shape(self):
        by_ticker = {"AAPL": {"consensusRating": "ModerateBuy", "averagePriceTarget": 300, "upsidePercent": -4.1, "smart_score": 6}}
        a = tr.rows(by_ticker)[0]
        self.assertEqual((a["ticker"], a["consensus"], a["price_target"], a["upside_pct"], a["smart_score"]), ("AAPL", "Moderate Buy", 300, -4.1, 6))

    def test_ticker_argument_from_the_schema(self):
        self.assertEqual(tr.ticker_argument(TOOL), ("tickers", False))
        self.assertEqual(tr.ticker_argument({"inputSchema": {"properties": {"symbols": {"type": "array"}}}}), ("symbols", True))


class Daily(unittest.TestCase):
    def setUp(self):
        self.folder, self.logs = Path(tempfile.mkdtemp()), []
        self.cfg, self.state = {"tipranks_api_key": "k"}, {}

    def test_one_call_a_day_for_every_stock(self):
        fake = Fake({"data": [{"ticker": "NVDA", "consensus": "Strong Buy"}]})
        path = tr.snapshot(self.cfg, self.state, DAY, ["NVDA", "GOOG", "000660.KS", "NVDA"], self.folder, self.logs.append, fake)
        self.assertEqual(fake.calls, [("get_assets_data", {"tickers": "NVDA,GOOG"})])   # one call; Korean listing left out
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((path.name, doc["rows"][0]["consensus"]), ("tipranks_2026-11-05.json", "Strong Buy"))
        self.assertIsNone(tr.snapshot(self.cfg, self.state, DAY, ["NVDA"], self.folder, self.logs.append, fake))   # same day again
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("already fetched today", self.logs[-1])

    def test_the_quota_sets_the_pace(self):
        fake = Fake({})
        fake.usage = {"tier": "basic", "limit": 10, "remaining": 9}   # the basic tier: weekly
        self.assertIsNotNone(tr.snapshot(self.cfg, self.state, DAY, ["NVDA"], self.folder, self.logs.append, fake))
        later = DAY.replace(day=9)
        self.assertIsNone(tr.snapshot(self.cfg, self.state, later, ["NVDA"], self.folder, self.logs.append, fake))
        self.assertIn("due 7 days after 2026-11-05", self.logs[-1])
        self.assertIsNotNone(tr.snapshot(self.cfg, self.state, DAY.replace(day=12), ["NVDA"], self.folder, self.logs.append, fake))
        fake.usage = {"limit": 10, "remaining": 3}                     # the last 3 stay for questions in Claude
        self.assertIsNone(tr.snapshot(self.cfg, self.state, DAY.replace(day=20), ["NVDA"], self.folder, self.logs.append, fake))
        self.assertIn("3 are kept", self.logs[-1])
        self.assertEqual(len(fake.calls), 2)
        self.assertIsNone(tr.snapshot({}, {}, DAY, ["NVDA"], self.folder, self.logs.append, fake))   # no key, no call

    def test_a_50_call_key_looks_up_on_weekdays(self):
        fake = Fake({})   # its get_my_usage says 50 a month
        self.assertIsNotNone(tr.snapshot(self.cfg, self.state, DAY, ["NVDA"], self.folder, self.logs.append, fake))           # Thursday
        self.assertIsNone(tr.snapshot(self.cfg, self.state, DAY.replace(day=7), ["NVDA"], self.folder, self.logs.append, fake))  # Saturday
        self.assertIn("weekend", self.logs[-1])
        self.assertIsNotNone(tr.snapshot(self.cfg, self.state, DAY.replace(day=9), ["NVDA"], self.folder, self.logs.append, fake))  # Monday
        self.assertEqual(len(fake.calls), 2)

    def test_the_real_answer(self):
        """get_assets_data's answer for four stocks on 5 Nov 2026."""
        data = json.loads((Path(__file__).parent / "fixtures" / "tipranks_assets_2026-11-05.json").read_text(encoding="utf-8"))
        r = {x["ticker"]: x for x in tr.rows(data)}
        self.assertEqual((r["GOOG"]["consensus"], r["GOOG"]["upside_pct"], r["GOOG"]["smart_score"]), ("Strong Buy", 48.4, 8))
        self.assertEqual((r["CRWV"]["consensus"], r["CRWV"]["best_consensus"], r["CRWV"]["days_to_earnings"]), ("Buy", "Strong Buy", 5))
        self.assertEqual((r["AAPL"]["upside_pct"], r["QCOM"]["consensus"]), (-2.3, "Neutral"))

    def test_a_failure_is_logged_not_raised(self):
        class Broken(Fake):
            def call(self, name, arguments):
                raise tr.TipRanksError("TipRanks rate limit reached (HTTP 429)")
        self.assertIsNone(tr.snapshot(self.cfg, self.state, DAY, ["NVDA"], self.folder, self.logs.append, Broken({})))
        self.assertIn("429", self.logs[-1])
        self.assertEqual(self.state["tipranks"]["calls"], 1)   # the attempt still counts against the month


if __name__ == "__main__":
    unittest.main()
