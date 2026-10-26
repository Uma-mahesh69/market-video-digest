"""Tests for the JSON export (digest_export.py). Run: python -m unittest test_digest_export -v
Uses made-up notes shaped like the Oct 22 digest; no network, Gemini or YouTube needed."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import digest_export as dx

DAY = datetime(2026, 10, 22, 7, 5)
NOW = datetime(2026, 10, 22, 7, 5, tzinfo=timezone.utc)


def video(n, channel="TheStreet"):
    return {"id": f"vid{n:08d}", "title": f"Video {n}", "channel": channel, "published": "2026-10-21T14:00:00+00:00",
            "url": f"https://www.youtube.com/watch?v=vid{n:08d}", "duration": 1404}


def notes(**extra):
    base = {"summary": "A summary.", "speakers": [{"name": "Sam Stovall", "role": "Chief Investment Strategist, CFRA Research"}],
            "key_points": [{"point": "Bull market isn't over", "time": "2:13", "seconds": 133}],
            "market_levels": [], "stocks": [], "sectors_and_themes": [], "predictions": [], "risks": [], "upcoming_events": [],
            "sp500_targets": []}
    base.update(extra)
    return base


def stock(name, view, ticker="", analyst="", seconds=53):
    return {"name": name, "ticker": ticker, "view": view, "reason": "because", "analyst": analyst, "time": dx.stamp(seconds), "seconds": seconds}


def fixture():
    """Two videos and a day overview, as digest.py hands them to the export."""
    done = [
        {"video": video(1), "notes": notes(
            sp500_targets=[{"value": 8050, "horizon": "year-end"}, {"value": 8650, "horizon": "12-month"}],
            sectors_and_themes=[{"name": "Healthcare", "view": "bullish", "reason": "Top pick", "time": "17:13", "seconds": 1033}],
            market_levels=[{"item": "10-year yield concern threshold", "value": "5.45%", "number": 5.45, "unit": "%",
                            "context": "Stovall: level where stocks get seriously concerned", "time": "19:44", "seconds": 1184},
                           {"item": "Dollar index", "value": "near 100", "number": 100, "unit": "pts?", "context": "", "time": "3:00", "seconds": 180}],
            upcoming_events=[{"event": "US midterm elections", "when": "November 3rd", "date": "2026-11-03", "time": "1:00", "seconds": 60}],
            stocks=[stock("Nvidia", "bullish"), stock("NVDA", "bullish"), stock("Tesla", "bearish", "TSLA")])},
        {"video": video(2), "notes": notes(
            speakers=["James Demmert"],   # the older cached format: plain strings
            upcoming_events=[{"event": "US Midterm Elections", "when": "next month", "date": "", "time": "2:00", "seconds": 120}],
            stocks=[stock("Micron", "bullish", analyst="James Demmert"), stock("Nvidia", "neutral"),
                    stock("Acme Robotics", "loves it", "ACME"), stock("SK Hynix", "bullish")])},
    ]
    overview = {"overview": "A bifurcated market.",
                "themes": [{"theme": "AI Infrastructure and Bottlenecks", "detail": "...", "videos": [1, 2, 9]}],
                "disagreements": [{"topic": "Federal Reserve's next move", "detail": "...", "videos": [1, 2], "sides": [
                    {"analysts": ["Sam Stovall"], "position": "Hold in October", "videos": [1]},
                    {"analysts": ["Julian Koski"], "position": "Next move is a hike", "videos": [2]}]},
                       {"topic": "No sides given", "detail": "...", "videos": [1]}]}
    return done, overview


class Export(unittest.TestCase):
    def setUp(self):
        self.table = dx.load_tickers()
        self.schema = json.loads(dx.SCHEMA_FILE.read_text(encoding="utf-8"))
        self.done, self.overview = fixture()

    def build(self, done=None, overview=None):
        return dx.build_payload(DAY, self.done if done is None else done, self.overview if overview is None else overview, self.table, now=NOW)

    def test_schema_passes(self):
        payload, _ = self.build()
        self.assertEqual(dx.validate(payload, self.schema), [])
        self.assertEqual(payload["digest_date"], "2026-10-22")
        self.assertEqual(payload["video_count"], 2)
        self.assertEqual(payload["channels"], ["TheStreet"])

    def test_one_row_per_call_and_names_merged(self):
        payload, unmatched = self.build()
        tickers = [m["ticker"] for m in payload["mentions"]]
        self.assertEqual(len(payload["mentions"]), 7)   # never collapsed
        self.assertEqual(tickers.count("NVDA"), 3)       # "Nvidia" and "NVDA" in two videos
        self.assertIn("000660.KS", tickers)
        acme = next(m for m in payload["mentions"] if m["name"] == "Acme Robotics")
        self.assertIsNone(acme["ticker"])                # unknown name: null, and reported
        self.assertEqual(acme["view"], "mixed")          # unknown view word becomes mixed
        self.assertEqual(unmatched, [("Acme Robotics", "ACME")])

    def test_traceable(self):
        payload, _ = self.build()
        micron = next(m for m in payload["mentions"] if m["ticker"] == "MU")
        self.assertEqual((micron["video"], micron["timestamp"], micron["analyst"]), (2, "0:53", "James Demmert"))
        level = payload["levels"][0]
        self.assertEqual((level["value"], level["unit"], level["display"], level["video"], level["timestamp"]), (5.45, "%", "5.45%", 1, "19:44"))
        self.assertIsNone(payload["levels"][1]["unit"])   # a unit outside the four allowed is dropped, the value kept
        self.assertEqual(payload["levels"][1]["value"], 100)

    def test_video_fields(self):
        payload, _ = self.build()
        v1, v2 = payload["videos"]
        self.assertEqual(v1["duration"], "23:24")
        self.assertEqual(v1["sp500_targets"], [{"value": 8050, "horizon": "year-end"}, {"value": 8650, "horizon": "12-month"}])
        self.assertEqual(v1["sectors"][0]["timestamp"], "17:13")
        self.assertEqual(v2["speakers"], [{"name": "James Demmert", "role": None}])

    def test_events_merged_and_debates(self):
        payload, _ = self.build()
        self.assertEqual(payload["upcoming"], [{"event": "US midterm elections", "date": "2026-11-03", "date_text": "November 3rd", "videos": [1, 2]}])
        self.assertEqual(len(payload["debates"]), 1)     # a disagreement without sides is left out
        self.assertEqual(payload["themes"][0]["videos"], [1, 2])   # video 9 does not exist in this digest

    def test_no_video_day(self):
        payload, _ = self.build(done=[], overview={"overview": "", "themes": [], "disagreements": []})
        self.assertEqual(dx.validate(payload, self.schema), [])
        self.assertEqual(payload["video_count"], 0)
        for key in ("videos", "mentions", "themes", "debates", "levels", "upcoming"):
            self.assertEqual(payload[key], [])

    def test_validator_catches_problems(self):
        payload, _ = self.build()
        del payload["summary"]
        payload["mentions"][0]["view"] = "great"
        payload["videos"][0]["number"] = True
        errors = dx.validate(payload, self.schema)
        self.assertTrue(any("missing summary" in x for x in errors))
        self.assertTrue(any("mentions[0].view" in x for x in errors))
        self.assertTrue(any("videos[0].number" in x for x in errors))

    def test_view_words(self):
        self.assertEqual([dx.view(w) for w in ("Bullish", " bearish ", "NEUTRAL", "cautious", None)],
                         ["bullish", "bearish", "neutral", "mixed", "mixed"])

    def test_company_name_forms(self):
        for name in ("Apple Inc.", "NVIDIA Corporation", "Nvidia's", "Nvidia\u2019s", "Nvidia (NVDA)", "The Walt Disney Company"):
            with self.subTest(name=name):
                expected = None if "Disney" in name else ("AAPL" if "Apple" in name else "NVDA")
                self.assertEqual(dx.resolve_ticker(name, "", self.table), expected)
        self.assertEqual(dx.resolve_ticker("Some Bank", "JPM", self.table), "JPM")   # falls back to the ticker said

    def test_numbers_and_levels(self):
        self.assertEqual(dx.number("8,050"), 8050)
        self.assertEqual(dx.number("5.45"), 5.45)
        self.assertIsNone(dx.number("lots"))
        self.assertIsNone(dx.number(True))
        self.assertEqual(dx.parse_level("5.45%"), (5.45, "%"))
        self.assertEqual(dx.parse_level("near 100"), (100, None))
        self.assertEqual(dx.parse_level("$4,000"), (4000, "USD"))
        self.assertEqual(dx.parse_level("50 bps"), (50, "bp"))
        self.assertEqual(dx.parse_level("between 4 and 5%"), (None, None))

    def test_older_notes_still_fill_fields(self):
        """Notes saved before this change have no "number" on levels and no analyst on stocks."""
        old = notes(speakers=["Sam Stovall"], market_levels=[{"item": "10-year yield", "value": "4.95%", "context": "", "time": "1:00", "seconds": 60}],
                    stocks=[{"name": "Tesla", "ticker": "", "view": "bearish", "reason": "r", "time": "0:00", "seconds": 0}])
        del old["sp500_targets"]
        payload, _ = self.build(done=[{"video": video(1), "notes": old}], overview={"overview": "", "themes": [], "disagreements": []})
        self.assertEqual(dx.validate(payload, self.schema), [])
        self.assertEqual((payload["levels"][0]["value"], payload["levels"][0]["unit"]), (4.95, "%"))
        self.assertEqual(payload["mentions"][0]["analyst"], "Sam Stovall")   # the video's only speaker

    def test_analyst_not_guessed_with_several_speakers(self):
        two = notes(speakers=[{"name": "A", "role": ""}, {"name": "B", "role": ""}], stocks=[stock("Tesla", "bearish")])
        payload, _ = self.build(done=[{"video": video(1), "notes": two}], overview={"overview": "", "themes": [], "disagreements": []})
        self.assertIsNone(payload["mentions"][0]["analyst"])

    def test_later_1x_versions_pass(self):
        payload, _ = self.build()
        newer = dict(payload, schema_version="1.1", new_optional_field=[1])
        self.assertEqual(dx.validate(newer, self.schema), [])
        self.assertTrue(dx.validate(dict(payload, schema_version="2.0"), self.schema))


class Save(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.logs = []
        self.done, self.overview = fixture()
        self.full, _ = dx.build_payload(DAY, self.done, self.overview, dx.load_tickers(), now=NOW)

    def test_writes_named_file(self):
        path = dx.save(self.full, self.dir, self.logs.append)
        self.assertEqual(path.name, "video-digest_2026-10-22.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["video_count"], 2)

    def test_failed_validation_saves_nothing(self):
        yesterday = self.dir / "video-digest_2026-10-21.json"
        yesterday.write_text("{}", encoding="utf-8")
        bad = dict(self.full, video_count=-1)
        self.assertIsNone(dx.save(bad, self.dir, self.logs.append))
        self.assertFalse((self.dir / "video-digest_2026-10-22.json").exists())
        self.assertEqual(yesterday.read_text(encoding="utf-8"), "{}")
        self.assertIn("2026-10-22 NOT saved", self.logs[-1])

    def test_empty_rerun_keeps_days_file(self):
        dx.save(self.full, self.dir, self.logs.append)
        empty, _ = dx.build_payload(DAY, [], {"overview": "", "themes": [], "disagreements": []}, {}, now=NOW)
        dx.save(empty, self.dir, self.logs.append)
        self.assertEqual(json.loads((self.dir / "video-digest_2026-10-22.json").read_text(encoding="utf-8"))["video_count"], 2)

    def test_rerun_with_videos_overwrites(self):
        dx.save(self.full, self.dir, self.logs.append)
        one, _ = dx.build_payload(DAY, self.done[:1], self.overview, dx.load_tickers(), now=NOW)
        dx.save(one, self.dir, self.logs.append)
        self.assertEqual(json.loads((self.dir / "video-digest_2026-10-22.json").read_text(encoding="utf-8"))["video_count"], 1)


if __name__ == "__main__":
    unittest.main()
