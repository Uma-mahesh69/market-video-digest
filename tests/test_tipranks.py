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

    def tools(self):
        return [TOOL]

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": json.dumps(self.answer)}]}


class Reading(unittest.TestCase):
    def test_event_stream_and_json_answers(self):
        sse = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
        self.assertEqual(tr.Client._answer(sse, "text/event-stream"), {"tools": []})
        self.assertEqual(tr.Client._answer('{"jsonrpc":"2.0","id":2,"result":{"ok":1}}', "application/json"), {"ok": 1})
        with self.assertRaises(tr.TipRanksError):
            tr.Client._answer('{"jsonrpc":"2.0","id":3,"error":{"message":"bad key"}}')

    def test_fields_found_in_different_shapes(self):
        nested = {"data": [{"ticker": "NVDA", "analystConsensus": {"consensus": "Strong Buy", "buy": 30, "hold": 2, "sell": 0},
                            "priceTarget": {"average": "$260.50", "upside": "21.3%"}, "smartScore": 8, "numberOfAnalysts": 32}]}
        by_ticker = {"AAPL": {"consensusRating": "Moderate Buy", "averagePriceTarget": 300, "upsidePercent": -4.1, "smart_score": 6}}
        n, a = tr.rows(nested)[0], tr.rows(by_ticker)[0]
        self.assertEqual((n["ticker"], n["consensus"], n["buy"], n["hold"], n["sell"], n["analysts"], n["smart_score"]), ("NVDA", "Strong Buy", 30, 2, 0, 32, 8))
        self.assertEqual((n["price_target"], n["upside_pct"]), (260.5, 21.3))
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

    def test_monthly_budget_and_no_key(self):
        self.state["tipranks"] = {"month": "2026-11", "calls": 40}
        fake = Fake({})
        self.assertIsNone(tr.snapshot(self.cfg, self.state, DAY, ["NVDA"], self.folder, self.logs.append, fake))
        self.assertEqual(fake.calls, [])
        self.assertIn("40 TipRanks calls are used", self.logs[-1])
        self.state["tipranks"]["month"] = "2026-10"   # a new month starts again
        self.assertIsNotNone(tr.snapshot(self.cfg, self.state, DAY, ["NVDA"], self.folder, self.logs.append, fake))
        self.assertIsNone(tr.snapshot({}, {}, DAY, ["NVDA"], self.folder, self.logs.append, fake))

    def test_a_failure_is_logged_not_raised(self):
        class Broken(Fake):
            def call(self, name, arguments):
                raise tr.TipRanksError("TipRanks rate limit reached (HTTP 429)")
        self.assertIsNone(tr.snapshot(self.cfg, self.state, DAY, ["NVDA"], self.folder, self.logs.append, Broken({})))
        self.assertIn("429", self.logs[-1])
        self.assertEqual(self.state["tipranks"]["calls"], 1)   # the attempt still counts against the month


if __name__ == "__main__":
    unittest.main()
