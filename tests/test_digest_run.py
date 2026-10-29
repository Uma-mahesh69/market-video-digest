"""Tests for the daily run in digest.py: the JSON file across runs on the same day, --rebuild and --check.
YouTube, ytmd, Gemini and email are replaced by fakes. Run from the project folder: python -m unittest -v"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import digest


def upload(n, hours_ago=1):
    return {"id": f"video{n:06d}", "title": f"Video {n}", "channel": "TheStreet",
            "published": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
            "url": f"https://www.youtube.com/watch?v=video{n:06d}", "short": False}


def fake_notes(view="Bullish"):
    return {"summary": "s", "speakers": [{"name": "Sam Stovall", "role": "CFRA"}], "key_points": [{"point": "p", "time": "2:13"}],
            "market_levels": [{"item": "10-year yield", "value": "5.45%", "number": 5.45, "unit": "%", "context": "c", "time": "19:44"}],
            "stocks": [{"name": "Nvidia", "ticker": "", "view": view, "reason": "r", "analyst": "", "time": "0:53"},
                       {"name": "Weird Co", "ticker": "WRD", "reason": "no view given", "time": "1:00"}],
            "sectors_and_themes": [], "predictions": [], "risks": [],
            "sp500_targets": [{"value": "8,050", "horizon": "year-end", "time": "3:00"}],
            "upcoming_events": [{"event": "Midterms", "when": "November 3rd", "date": "2026-11-03", "time": "1:00"}]}


class DailyRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(digest, k) for k in ("CACHE_DIR", "OUT_DIR", "JSON_DIR", "STATE", "CONFIG", "YTMD", "wait_for_internet",
                                                     "latest_uploads", "transcript", "gemini", "send")}
        digest.CACHE_DIR, digest.OUT_DIR, digest.JSON_DIR = self.tmp / "cache", self.tmp / "digests", self.tmp / "json"
        digest.STATE, digest.CONFIG, digest.YTMD = self.tmp / "state.json", self.tmp / "cfg.json", self.tmp / "ytmd"
        digest.CONFIG.write_text(json.dumps({"channels": ["https://www.youtube.com/channel/UC" + "x" * 22], "gemini_api_key": "k", "email_to": ["anil@example.com"]}))
        digest.YTMD.write_text("")
        digest.wait_for_internet = lambda: True
        self.feed = [upload(1), upload(2)]
        digest.latest_uploads = lambda cid: list(self.feed)
        digest.transcript = self.fake_transcript
        self.calls = {"extract": 0, "day": 0}
        digest.gemini = self.fake_gemini
        digest.send = lambda *a: True

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(digest, k, v)

    def fake_transcript(self, v):
        v.update(duration=1404, captions="auto", truncated=False)
        return "[0:53] text " * 50

    def fake_gemini(self, cfg, system, prompt):
        if system is digest.DAY_SYSTEM:
            self.calls["day"] += 1
            count = prompt.count('"n":')
            return {"overview": f"{count} videos.", "themes": [{"theme": "AI", "detail": "d", "videos": list(range(1, count + 1))}],
                    "disagreements": [{"topic": "Fed", "detail": "d", "videos": [1, 2], "sides": [
                        {"analysts": ["Sam Stovall"], "position": "Hold", "videos": [1]}, {"analysts": ["X"], "position": "Hike", "videos": [2]}]}]}
        self.calls["extract"] += 1
        return fake_notes()

    def run_digest(self, *args):
        sys.argv = ["digest.py", *args]
        out = io.StringIO()
        code = 0
        with redirect_stdout(out):
            try:
                digest.main()
            except SystemExit as stop:
                code = stop.code or 0
        return code, out.getvalue()

    def day_file(self, folder="json"):
        return json.loads((self.tmp / folder / f"video-digest_{datetime.now():%Y-%m-%d}.json").read_text(encoding="utf-8"))

    def test_daily_file(self):
        code, out = self.run_digest()
        self.assertEqual(code, 0, out)
        day = self.day_file()
        self.assertEqual(day["video_count"], 2)
        self.assertEqual([m["view"] for m in day["mentions"]], ["bullish", "mixed"] * 2)   # "Bullish" kept, missing view is mixed
        self.assertEqual(day["mentions"][0]["analyst"], "Sam Stovall")
        self.assertEqual(day["videos"][0]["sp500_targets"], [{"value": 8050, "horizon": "year-end"}])
        self.assertIn("no ticker for 'Weird Co'", out)

    def test_second_run_same_day_adds_to_the_file(self):
        self.run_digest()
        morning = [v["title"] for v in self.day_file()["videos"]]
        self.feed.insert(0, upload(3, hours_ago=0))   # a new upload, picked up by a manual run later that day
        code, out = self.run_digest()
        self.assertEqual(code, 0, out)
        day = self.day_file()
        self.assertEqual(day["video_count"], 3)
        self.assertEqual([v["title"] for v in day["videos"]], morning + ["Video 3"])   # earlier numbers unchanged
        self.assertEqual(day["summary"], "3 videos.")   # the overview covers the whole day
        self.assertEqual(self.calls["extract"], 3)      # earlier videos come from the saved notes, not Gemini

    def test_run_with_nothing_new_keeps_the_file(self):
        self.run_digest()
        code, out = self.run_digest()
        self.assertEqual(self.day_file()["video_count"], 2)
        self.assertIn("today's file is kept", out)

    def test_dry_run_never_touches_the_real_file(self):
        self.run_digest("--dry-run")
        self.assertFalse((self.tmp / "json").exists())
        self.assertEqual(self.day_file("digests")["video_count"], 2)

    def test_rebuild_an_earlier_day(self):
        self.run_digest()
        today = f"{datetime.now():%Y-%m-%d}"
        code, out = self.run_digest("--rebuild", today)   # the real file exists: past files are never changed
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)
        old = json.loads((digest.CACHE_DIR / "video000001.json").read_text(encoding="utf-8"))
        del old["sp500_targets"]                           # notes saved before the JSON fields existed
        (digest.CACHE_DIR / "video000001.json").write_text(json.dumps(old), encoding="utf-8")
        code, out = self.run_digest("--rebuild", today, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("Summarising again", out)
        self.assertEqual(self.day_file("digests")["video_count"], 2)
        self.assertEqual(self.calls["extract"], 3)

    def use_watchlist(self, content):
        sheet = self.tmp / "watchlist.csv"
        sheet.write_text(content, encoding="utf-8")
        cfg = json.loads(digest.CONFIG.read_text())
        digest.CONFIG.write_text(json.dumps(dict(cfg, watchlist_csv=str(sheet))))
        self.sent = []
        digest.send = lambda cfg, subject, page, text: self.sent.append((page, text)) or True

    def test_watchlist_in_email_and_market_file(self):
        self.use_watchlist("Role,Ticker,Name,Price,Currency,Change % (day),Change % (week)\n"
                           "watch,NVDA,NVIDIA Corp,213.25,USD,-0.99,0.49\nwatch,AAPL,Apple Inc,349.32,USD,1.6,0.32\n"
                           "sp500,INDEXSP:.INX,S&P 500,7706.17,,-0.49,0.56\n")
        code, out = self.run_digest()
        self.assertEqual(code, 0, out)
        page, text = self.sent[0]
        self.assertIn("Your watchlist", page)
        self.assertIn("No new expert views today on 1 of your 2 stocks: AAPL.", page)
        self.assertIn("year-end S&amp;P 500 target of 8,050 is +4.5%", page)
        self.assertIn("Look at next:", text)
        market = json.loads((self.tmp / "json" / f"market-data_{datetime.now():%Y-%m-%d}.json").read_text(encoding="utf-8"))
        nvda = market["watchlist"][0]
        self.assertEqual((nvda["ticker"], nvda["price"], nvda["calls_today"]["bullish"]), ("NVDA", 213.25, 2))
        code, out = self.run_digest("--check")
        self.assertIn("Watchlist sheet: 2 stocks, 2 with prices, S&P 500 at 7,706", out)

    def test_broken_sheet_does_not_stop_the_digest(self):
        self.use_watchlist("<html>Sign in</html>")
        code, out = self.run_digest()
        self.assertEqual(code, 0, out)
        self.assertIn("Prices for your watchlist could not be read today", self.sent[0][0])
        self.assertEqual(self.day_file()["video_count"], 2)   # the digest file is saved as usual
        self.assertFalse((self.tmp / "json" / f"market-data_{datetime.now():%Y-%m-%d}.json").exists())

    def test_email_stock_table_merges_names(self):
        notes = digest.clean_notes(fake_notes(), 1404)
        notes["stocks"].append({"name": "NVDA", "ticker": "NVDA", "view": "bearish", "reason": "too far, too fast", "time": "2:00", "seconds": 120})
        page = digest.render(datetime.now(), [{"video": dict(upload(1), duration=1404), "notes": notes}], [],
                             {"overview": "", "themes": [], "disagreements": []})
        table = page[page.index("Stocks mentioned"):page.index("Market levels")]
        self.assertEqual(table.count("<b>Nvidia</b>"), 1)
        self.assertNotIn("<b>NVDA</b>", table)
        self.assertIn("too far, too fast", table)

    def test_check_reports_the_json_folder(self):
        code, out = self.run_digest("--check")   # the /channel/UC... link needs no lookup
        self.assertEqual(code, 0, out)
        self.assertIn(f"JSON folder: {self.tmp / 'json'} (can write)", out)


if __name__ == "__main__":
    unittest.main()
