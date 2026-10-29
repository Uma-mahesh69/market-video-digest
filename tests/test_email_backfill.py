"""Tests for email_backfill.py: a digest rendered by digest.py, read back into the JSON file. No network.
Run from the project folder: python -m unittest -v"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import digest
import digest_export as dx
import email_backfill as eb

DAY = datetime(2026, 10, 22, 7, 30)


def video(vid, title, published="2026-10-21T14:00:00+00:00"):
    return {"id": vid, "title": title, "channel": "TheStreet", "published": published,
            "url": f"https://www.youtube.com/watch?v={vid}", "duration": 1404, "captions": "manual"}


def notes(**extra):
    raw = {"summary": "Stovall sets a year-end S&P 500 price target of 8,050 and a 12-month target of 8,650.",
           "speakers": [{"name": "Caroline", "role": "Host"}, {"name": "Sam Stovall", "role": "Chief Investment Strategist, CFRA Research"}],
           "key_points": [{"point": "Bull market isn't over", "time": "2:13"}],
           "market_levels": [{"item": "10-year yield threshold for market concern", "value": "5.45%", "context": "Where stocks worry", "time": "19:44"}],
           "stocks": [{"name": "Nvidia", "ticker": "", "view": "bullish", "reason": "Still the AI leader", "time": "0:53"},
                      {"name": "Tesla", "ticker": "TSLA", "view": "bearish", "reason": "Ran too far ahead of earnings", "time": "1:10"}],
           "sectors_and_themes": [{"name": "Healthcare", "view": "bullish", "reason": "Top pick: defensive", "time": "17:13"}],
           "predictions": [{"claim": "Stocks end the year higher", "horizon": "year-end", "time": "3:00"}],
           "risks": [{"risk": "Rates back above 5%", "time": "4:00"}],
           "upcoming_events": [{"event": "US midterm elections", "when": "November 3rd", "time": "1:00"}],
           "sp500_targets": []}
    raw.update(extra)
    return digest.clean_notes(raw, 1404)


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.done = [
            {"video": video("aaaaaaaaaa1", "Bull market isn't over"), "notes": notes()},
            {"video": video("bbbbbbbbbb2", "Is Nvidia a buy?"), "notes": notes(
                speakers=[{"name": "Julian Koski", "role": "CIO"}], summary="Koski on rates.",
                stocks=[{"name": "NVDA", "ticker": "NVDA", "view": "bearish", "reason": "Too far, too fast", "time": "5:00"}],
                upcoming_events=[{"event": "US Midterm Elections", "when": "next month", "time": "2:00"}])},
        ]
        self.overview = {"overview": "A bifurcated market.",
                         "themes": [{"theme": "AI Infrastructure", "detail": "Memory and power.", "videos": [1, 2]}],
                         "disagreements": [{"topic": "Federal Reserve's next move",
                                            "detail": "Sam Stovall expects the Fed to hold, while Julian Koski predicts the next move is a hike.",
                                            "videos": [1, 2]}]}
        self.page = digest.render(DAY, self.done, [], self.overview)

    def test_everything_comes_back(self):
        day, done, overview = eb.parse(self.page)
        self.assertEqual(day.date(), DAY.date())
        self.assertEqual([d["video"]["id"] for d in done], ["aaaaaaaaaa1", "bbbbbbbbbb2"])
        v1 = done[0]
        self.assertEqual(v1["video"]["duration"], 1404)
        self.assertEqual(v1["notes"]["speakers"][1], {"name": "Sam Stovall", "role": "Chief Investment Strategist, CFRA Research"})
        self.assertEqual([(s["name"], s["view"], s["seconds"]) for s in v1["notes"]["stocks"]], [("Nvidia", "bullish", 53), ("Tesla", "bearish", 70)])
        self.assertEqual(v1["notes"]["sp500_targets"], [{"value": 8050, "horizon": "year-end"}, {"value": 8650, "horizon": "12-month"}])
        self.assertEqual(v1["notes"]["sectors_and_themes"][0]["reason"], "Top pick: defensive")
        self.assertEqual(v1["notes"]["predictions"][0]["horizon"], "year-end")
        self.assertEqual(v1["notes"]["upcoming_events"][0]["event"], "US midterm elections")
        self.assertEqual(overview["themes"][0]["videos"], [1, 2])

    def test_file_matches_a_daily_one(self):
        folder = Path(tempfile.mkdtemp())
        path = eb.backfill([self.page], folder, log=lambda m: None)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(dx.validate(data, json.loads(dx.SCHEMA_FILE.read_text(encoding="utf-8"))), [])
        self.assertEqual(data["backfilled_from"], "digest email")
        self.assertEqual([m["ticker"] for m in data["mentions"]], ["NVDA", "TSLA", "NVDA"])   # every call, names merged
        self.assertEqual(data["mentions"][2]["analyst"], "Julian Koski")                     # the video's one speaker
        self.assertEqual(data["levels"][0]["value"], 5.45)
        self.assertEqual(data["upcoming"][0]["videos"], [1, 2])                               # one row per event
        sides = data["debates"][0]["sides"]
        self.assertEqual([(s["analysts"], s["videos"]) for s in sides], [(["Sam Stovall"], [1]), (["Julian Koski"], [2])])

    def test_same_day_digests_become_one_file(self):
        earlier = digest.render(DAY, self.done[:1], [], {"overview": "", "themes": [], "disagreements": []})
        day, done, _ = eb.combine([eb.parse(earlier), eb.parse(self.page)])
        self.assertEqual([d["video"]["id"] for d in done], ["aaaaaaaaaa1", "bbbbbbbbbb2"])
        folder = Path(tempfile.mkdtemp())
        eb.backfill([self.page], folder, log=lambda m: None)
        logs = []
        self.assertIsNone(eb.backfill([earlier], folder, log=logs.append))   # a day that has a file is left alone
        self.assertIn("left as it is", logs[0])

    def test_older_speaker_lines_and_video_sides(self):
        self.assertEqual(eb.split_speakers("Ashim Mehra, Managing Director and Portfolio Manager at Baron Capital, Caroline, Host"),
                         [{"name": "Ashim Mehra", "role": "Managing Director and Portfolio Manager at Baron Capital"},
                          {"name": "Caroline", "role": "Host"}])
        sides = eb.sides("Video 6 explicitly rates Apple a buy, while Videos 1, 4, and 5 label it a trap", [1, 4, 5, 6], {})
        self.assertEqual([s["videos"] for s in sides], [[6], [1, 4, 5]])

    def test_saved_copy_and_patterns(self):
        """The saved copy in digests/ has an "Ask a question" link under each video; a pattern is expanded by the script."""
        import re, subprocess, sys
        folder, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        local = re.sub(r"<!--ASK:([\w-]{11})-->", lambda m: f'<p style="margin:10px 0 0;font-size:13px"><a href="http://127.0.0.1:8765/?video={m.group(1)}">Ask a question about this video</a></p>', self.page)
        (folder / "digest-2026-10-22-0730.html").write_text(local, encoding="utf-8")
        run = subprocess.run([sys.executable, "email_backfill.py", str(folder / "digest-*.html"), "--out", str(out)], capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads((out / "video-digest_2026-10-22.json").read_text(encoding="utf-8"))["video_count"], 2)

    def test_not_a_digest(self):
        with self.assertRaises(ValueError):
            eb.parse("<html>hello</html>")


if __name__ == "__main__":
    unittest.main()
