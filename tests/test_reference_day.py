"""The user story's acceptance check "Hub matches", on the real stock calls of the Oct 22, 2026 digest.
The hub's scoring rules (from the user story) are applied to the calls as digest_export.py would write them.
Run from the project folder: python -m unittest -v"""
import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from digest_export import load_tickers, resolve_ticker, view

CALLS = json.loads((Path(__file__).parent / "fixtures" / "digest_2026-10-22_calls.json").read_text(encoding="utf-8"))["stocks"]


class Oct22(unittest.TestCase):
    def setUp(self):
        table = load_tickers()
        self.calls = defaultdict(Counter)
        for s in CALLS:
            ticker = resolve_ticker(s["name"], s["ticker"], table)
            for v in s["views"]:   # one row per call, as in mentions[]
                self.calls[ticker or s["name"]][view(v)] += 1

    def test_analyst_mood_is_74_percent(self):
        bull = sum(c["bullish"] for c in self.calls.values())
        bear = sum(c["bearish"] for c in self.calls.values())
        self.assertEqual((bull, bear), (58, 20))
        self.assertEqual(round(100 * bull / (bull + bear)), 74)

    def test_consensus_buys(self):
        buys = sorted((t for t, c in self.calls.items() if c["bullish"] >= 2 and c["bearish"] == 0), key=lambda t: -self.calls[t]["bullish"])
        self.assertEqual(buys[:3], ["GOOGL", "AMZN", "MU"])

    def test_split_and_avoid(self):
        split = {t for t, c in self.calls.items() if c["bullish"] and c["bearish"]}
        self.assertEqual(split, {"NVDA", "AAPL", "META", "CRWV", "NFLX"})
        avoid = sorted((t for t, c in self.calls.items() if not c["bullish"] and c["bearish"] + c["mixed"]),
                       key=lambda t: -(self.calls[t]["bearish"] + self.calls[t]["mixed"]))
        self.assertEqual(avoid[0], "TSLA")
        self.assertEqual((self.calls["TSLA"]["bearish"], self.calls["TSLA"]["mixed"]), (2, 2))

    def test_nvidia_calls_are_seven_rows(self):
        self.assertEqual(sum(self.calls["NVDA"].values()), 7)


if __name__ == "__main__":
    unittest.main()
