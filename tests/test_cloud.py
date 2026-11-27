"""Tests for the cloud version: the shared engine (cloud/engine) and its tools. No network, no Firebase: the engine
runs against an in-memory store with invented data. Run from the project folder: python -m unittest -v"""
import json
import re
import tempfile
import unittest
from unittest import mock
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import digest
import prices
import tipranks

from cloud.engine import cards, mail, odds, record, run as engine, street, videos
from cloud.engine.store import MemoryStore, check, doc_id
from cloud.tools import demo_data, make_symbols

FEED = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/">
{}</feed>"""
ENTRY = """<entry><yt:videoId>{id}</yt:videoId><title>{title}</title><link rel="alternate" href="https://www.youtube.com/{path}{id}"/>
<author><name>Example TV</name></author><published>{when}</published><media:group><media:description>{desc}</media:description></media:group></entry>"""


def entry(vid, title, when, desc="", short=False):
    return ENTRY.format(id=vid, title=title, when=when.isoformat(), desc=desc, path="shorts/" if short else "watch?v=")


class Globals(unittest.TestCase):
    """The engine points the shared price and digest modules at its own folder; put them back after each test."""

    def setUp(self):
        self.keep = (prices.CACHE, prices.MAX_SYMBOLS, digest.log)
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)

    def tearDown(self):
        prices.CACHE, prices.MAX_SYMBOLS, digest.log = self.keep
        self.tmp.cleanup()


class Storing(unittest.TestCase):
    def test_a_list_inside_a_list_is_refused_before_firestore_refuses_it(self):
        check({"a": [1, {"b": [2, 3]}]})
        with self.assertRaises(ValueError):
            check({"closes": [["2026-11-13", 100.0]]})

    def test_tickers_become_safe_document_names(self):
        self.assertEqual([doc_id("^GSPC"), doc_id("BRK-B"), doc_id("A/B")], ["_GSPC", "BRK-B", "A-B"])

    def test_merge_keeps_what_was_there(self):
        s = MemoryStore()
        s.set("mail", "u1", {"daily": "2026-11-13"})
        s.set("mail", "u1", {"weekly": "2026-11-14"}, merge=True)
        self.assertEqual(s.get("mail", "u1"), {"daily": "2026-11-13", "weekly": "2026-11-14"})


class Videos(unittest.TestCase):
    NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    SOURCES = {"channels": [{"name": "Example TV", "url": "https://www.youtube.com/channel/UC" + "a" * 22}], "analysts": ["Dan Ives", "Tom Lee"],
               "limits": {"lookback_hours": 36, "videos_per_day": 3, "videos_per_run": 2, "max_video_minutes": 20, "video_fps": 0.2}}

    def feed(self):
        t = self.NOW
        return FEED.format("".join([
            entry("aaaaaaaaaa1", "Cooking pasta at home", t - timedelta(hours=1)),
            entry("aaaaaaaaaa2", "Dan Ives: why Nvidia stock rallies after earnings", t - timedelta(hours=5), "price target raised"),
            entry("aaaaaaaaaa3", "Stocks slide as the Fed holds rates", t - timedelta(hours=3)),
            entry("aaaaaaaaaa4", "Nvidia stock in 30 seconds", t - timedelta(hours=2), short=True),
            entry("aaaaaaaaaa5", "Tom Lee on the market outlook", t - timedelta(hours=50)),
            entry("aaaaaaaaaa6", "Tesla earnings: what analysts expect", t - timedelta(hours=4))]))

    def test_the_feed_gives_ids_times_and_descriptions(self):
        rows = videos.feed("UCx", self.feed())
        self.assertEqual(len(rows), 6)
        self.assertEqual((rows[1]["id"], rows[1]["description"], rows[1]["short"], rows[3]["short"]), ("aaaaaaaaaa2", "price target raised", False, True))

    def test_new_videos_are_ranked_named_analysts_first_and_old_seen_and_short_ones_left_out(self):
        state = {"seen": ["aaaaaaaaaa6"]}
        found = videos.discover(self.SOURCES, state, self.NOW, log=lambda m: None, fetch_feed=lambda cid: videos.feed(cid, self.feed()))
        self.assertEqual([v["id"] for v in found], ["aaaaaaaaaa2", "aaaaaaaaaa3"])   # the cooking video is not about markets

    def test_gemini_is_given_the_link_and_asked_for_few_small_frames(self):
        v = {"id": "x", "title": "T", "channel": "C", "published": "2026-11-16T10:00:00+00:00", "url": "https://www.youtube.com/watch?v=x"}
        body = videos.body_for(v, self.SOURCES["limits"])
        part = body["contents"][0]["parts"][0]
        self.assertEqual(part["fileData"]["fileUri"], v["url"])
        self.assertEqual(part["videoMetadata"], {"endOffset": "1200s", "fps": 0.2})
        self.assertEqual(body["generationConfig"]["mediaResolution"], "MEDIA_RESOLUTION_LOW")
        plain = videos.body_for(v, self.SOURCES["limits"], plain=True)
        self.assertNotIn("videoMetadata", plain["contents"][0]["parts"][0])
        self.assertIn("watch one finance", body["system_instruction"]["parts"][0]["text"])

    def answer(self, notes):
        return {"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps(notes) + "\n```"}]}}]}

    def test_notes_come_back_in_the_usual_shape_and_a_refused_setting_is_retried_plainly(self):
        v = {"id": "abcdefghijk", "title": "T", "channel": "C", "published": "2026-11-16T10:00:00+00:00", "url": "u"}
        calls = []

        def call(cfg, body, timeout=0):
            calls.append(body)
            if len(calls) == 1:
                raise digest.GeminiError(400, "unknown field fps")
            return self.answer({"summary": "s", "stocks": [{"name": "Nvidia", "ticker": "NVDA", "view": "BULLISH", "time": "1:05"}, "junk"]})
        notes = videos.read({}, v, self.SOURCES["limits"], call=call)
        self.assertEqual(len(calls), 2)
        self.assertEqual(notes["stocks"], [{"name": "Nvidia", "ticker": "NVDA", "view": "bullish", "time": "1:05", "seconds": 65}])
        self.assertEqual(notes["_video"]["id"], "abcdefghijk")

        def never(cfg, body, timeout=0):
            raise digest.GeminiError(400, "video is private")
        with self.assertRaises(digest.Skip):
            videos.read({}, v, self.SOURCES["limits"], call=never)

    def test_reading_stops_at_the_days_allowance_and_remembers_what_it_read(self):
        store, state = MemoryStore(), {"channel_ids": {}}
        real = videos.discover
        videos.discover = lambda sources, st, now, log=print: real(sources, st, now, log, fetch_feed=lambda cid: videos.feed(cid, self.feed()))
        try:
            reader = lambda cfg, v, limits: {"stocks": [], "_video": {"id": v["id"], "published": v["published"]}}
            first = videos.read_new({}, self.SOURCES, state, store, self.NOW, log=lambda m: None, reader=reader, pause=0)
            second = videos.read_new({}, self.SOURCES, state, store, self.NOW, log=lambda m: None, reader=reader, pause=0)
            third = videos.read_new({}, self.SOURCES, state, store, self.NOW, log=lambda m: None, reader=reader, pause=0)
        finally:
            videos.discover = real
        self.assertEqual([len(first), len(second), len(third)], [2, 1, 0])   # 2 a run, 3 a day
        self.assertEqual(sorted(store.all("videos")), ["aaaaaaaaaa2", "aaaaaaaaaa3", "aaaaaaaaaa6"])
        self.assertEqual(state["videos_read"]["count"], 3)

    def test_out_of_quota_stops_the_run_and_the_video_is_tried_again_later(self):
        store, state = MemoryStore(), {"channel_ids": {}}
        real = videos.discover
        videos.discover = lambda sources, st, now, log=print: real(sources, st, now, log, fetch_feed=lambda cid: videos.feed(cid, self.feed()))
        tried = []

        def reader(cfg, v, limits):
            tried.append(v["id"])
            raise digest.GeminiError(429, "quota")
        try:
            made = videos.read_new({}, self.SOURCES, state, store, self.NOW, log=lambda m: None, reader=reader, pause=0)
        finally:
            videos.discover = real
        self.assertEqual((made, len(tried), state["seen"]), ([], 1, []))


class Street(unittest.TestCase):
    LIMITS = {"tipranks_batch": 2, "tipranks_calls_per_day": 3, "tipranks_reserve": 2}

    def test_the_months_calls_are_spread_over_its_weekdays(self):
        monday, saturday = date(2026, 11, 2), date(2026, 11, 7)
        self.assertEqual(street.weekdays_left(monday), 21)
        self.assertEqual(street.allowance({"remaining": 48}, {}, monday, self.LIMITS), 2)      # 46 over 21 days
        self.assertEqual(street.allowance({"remaining": 48}, {}, saturday, self.LIMITS), 0)    # ratings barely move at weekends
        self.assertEqual(street.allowance({"remaining": 2}, {}, monday, self.LIMITS), 0)       # the reserve is kept
        self.assertEqual(street.allowance(None, {}, monday, self.LIMITS), 0)                   # no count from TipRanks: do not guess
        self.assertEqual(street.allowance({"remaining": 48}, {"tipranks": {"day": "2026-11-02", "today": 2}}, monday, self.LIMITS), 0)

    def test_users_stocks_first_then_the_stalest(self):
        have = {"AAA": {"at": "2026-11-10"}, "BBB": {"at": "2026-11-01"}, "MINE": {"at": "2026-11-12"}}
        self.assertEqual(street.order(["AAA", "BBB", "CCC", "MINE", "005930.KS"], ["MINE"], have), ["MINE", "CCC", "BBB", "AAA"])

    def test_every_stock_gets_its_turn_however_many_there_are(self):
        names = [a + b for a in "ABCDEFGHIJ" for b in "ABCDEFGHIJ"]   # 100 tickers
        self.assertEqual(len(street.order(names + ["^GSPC", "RELIANCE.NS", "BRK-B"], [], {})), 101)   # the index and the Indian listing are not asked for
        records = {t: {"ticker": t, "analystConsensus": "Hold", "priceTargetUpside": 0.1} for t in names}
        have, day = {}, date(2026, 11, 2)
        for _ in range(30):   # a month of weekdays, a few batches a day
            client = demo_data.FakeTipRanks(records, remaining=48)
            have = street.refresh("", {}, have, names, [], day, {**self.LIMITS, "tipranks_batch": 30}, log=lambda m: None, client=client)
            day += timedelta(days=1)
        self.assertEqual(len(have), 100)

    def test_a_refresh_asks_in_batches_and_stamps_what_it_read(self):
        _, _, records = demo_data.make(date(2026, 11, 16))
        client, state = demo_data.FakeTipRanks(records, remaining=48), {}
        got = street.refresh("", state, {}, ["NVDA", "AAPL", "TSLA", "JPM", "ORCL"], ["ORCL"], date(2026, 11, 2), self.LIMITS, log=lambda m: None, client=client)
        self.assertEqual(client.calls, 2)   # two calls allowed that day, two stocks a call
        self.assertEqual(sorted(got), ["AAPL", "JPM", "NVDA", "ORCL"])
        self.assertEqual(got["ORCL"]["at"], "2026-11-02")
        self.assertIn(got["NVDA"]["consensus"], ("Strong Buy", "Moderate Buy", "Hold", "Moderate Sell"))
        self.assertEqual(got["NVDA"]["sector"], "Technology")
        self.assertIsNotNone(got["NVDA"]["market_cap"])

    def test_a_failing_tipranks_never_stops_the_run(self):
        class Broken:
            def start(self):
                raise tipranks.TipRanksError("down")
        self.assertEqual(street.refresh("k", {}, {"A": {"at": "x"}}, ["A"], [], date(2026, 11, 16), self.LIMITS, log=lambda m: None, client=Broken()), {"A": {"at": "x"}})


class Engine(Globals):
    """The whole run, on invented data, in memory."""

    def fill(self, store=None, **kw):
        store = store or MemoryStore()
        status = demo_data.fill(store, today=date(2026, 11, 16), work=self.work, log=lambda m: None, **kw)
        return store, status

    def test_a_run_writes_cards_charts_and_the_market_pages(self):
        store, status = self.fill()
        self.assertTrue(status["ok"], status["errors"])
        self.assertEqual(sorted(store.all("market")), ["analysts", "calendar", "meta", "odds", "overview", "record", "status", "videos"])
        card = store.get("stocks", "NVDA")
        for key in ("ticker", "name", "price", "signal", "confidence_pct", "factors", "calls", "calls_list", "bulls", "bears", "spark", "street",
                    "history", "low_52w", "high_52w", "days_to_earnings", "sector", "h", "updated"):
            self.assertIn(key, card, key)
        self.assertIn(card["signal"], ("yes", "no", "wait"))
        for private in ("shares", "cost", "value", "weight_pct", "gain_pct", "owned"):
            self.assertNotIn(private, card)   # a card is the same for everyone
        chart = store.get("charts", "NVDA")
        self.assertEqual(len(chart["d"]), len(chart["c"]))
        self.assertEqual(chart["c"][-1], card["price"])
        o = store.get("market", "overview")
        self.assertTrue(set(o["lists"]) >= {"yes", "no", "discussed", "split", "changed"})
        self.assertTrue(all(t in o["rows"] for ts in o["lists"].values() for t in ts))
        self.assertTrue(all((o["rows"][t]["confidence_pct"] or 0) >= 50 for t in o["lists"]["yes"]))
        leaders = store.get("market", "analysts")["rows"]
        self.assertEqual(len(leaders), 8)
        self.assertEqual([a["stars"] for a in leaders], sorted([a["stars"] for a in leaders], reverse=True))
        self.assertTrue(all(a["role"] for a in leaders))
        demo = store.get("public", "demo")
        self.assertEqual([c["ticker"] for c in demo["cards"]], ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"])
        self.assertIn("NVDA", demo["charts"])
        # the front page's proof numbers and the example's market card, without the signed-in pages' full lists
        self.assertEqual(demo["overview"]["analysts"], 8)
        self.assertGreater(demo["overview"]["calls"], 0)
        self.assertEqual((demo["overview"]["lists"], demo["overview"]["rows"]), ({}, {}))
        self.assertIn("price", demo["overview"]["sp500"])

    def test_a_ticker_nobody_knows_is_marked_so_the_page_can_say_so(self):
        store = MemoryStore()
        store.set("requests", "ZZZZ", {"by": "u", "at": "x"})
        self.fill(store)
        self.assertTrue(store.get("stocks", "ZZZZ")["unknown"])
        self.assertEqual(store.all("requests"), {})   # handled, so removed

    def test_a_second_run_with_nothing_new_writes_only_its_own_state(self):
        store, _ = self.fill()
        before = store.writes
        self.fill(store)
        videos_and_user = len(store.all("videos")) + 2   # the example data (videos, its user, its member) is put in again by fill()
        self.assertEqual(store.writes - before - videos_and_user, 2)   # engine/state and market/status

    def test_without_the_scratch_folder_everything_is_rebuilt_from_the_store(self):
        store, _ = self.fill()
        first = store.get("stocks", "AMZN")
        with tempfile.TemporaryDirectory() as fresh:
            self.work = Path(fresh)
            self.fill(store)
        self.assertEqual(store.get("stocks", "AMZN")["h"], first["h"])

    def test_a_signal_that_changes_is_recorded_once_with_its_date(self):
        today = date(2026, 11, 16)
        notes, closes, records = demo_data.make(today)
        pairs = videos.as_pairs(list(notes.values()))
        cache = {t: {**v, "day": today.isoformat()} for t, v in closes.items()}
        sources = {"analysts": [], "channels": [], "packs": []}
        tr = {r["ticker"]: {**r, "at": today.isoformat()} for r in tipranks.rows({"assetsData": list(records.values())})}
        first, _, _ = cards.build(pairs, cache, tr, {}, ["NVDA"], today, sources)
        self.assertIsNone(first["NVDA"]["changed"])
        self.assertEqual(len(first["NVDA"]["history"]), 1)
        flipped = {"NVDA": {**first["NVDA"], "history": [{"d": "2026-11-12", "s": "no" if first["NVDA"]["signal"] != "no" else "yes", "c": 60}]}}
        second, _, _ = cards.build(pairs, cache, tr, flipped, ["NVDA"], today, sources)
        self.assertEqual(second["NVDA"]["changed"], {"from": flipped["NVDA"]["history"][0]["s"], "to": first["NVDA"]["signal"], "on": "2026-11-16"})
        third, _, _ = cards.build(pairs, cache, tr, second, ["NVDA"], today + timedelta(days=1), sources)
        self.assertEqual(len(third["NVDA"]["history"]), 2)   # no new line while the signal stays
        # a card made under the old rules: its history restarts, and the move is not news
        old_rules = {"NVDA": {k: v for k, v in flipped["NVDA"].items() if k != "method"}}
        fresh, _, _ = cards.build(pairs, cache, tr, old_rules, ["NVDA"], today, sources)
        self.assertIsNone(fresh["NVDA"]["changed"])
        self.assertEqual([h["s"] for h in fresh["NVDA"]["history"]], [first["NVDA"]["signal"]])

    def test_a_price_fetched_before_the_close_was_out_is_fetched_again(self):
        sat_morning = datetime(2026, 11, 21, 1, 25, tzinfo=timezone.utc)
        self.assertEqual(prices.last_session(sat_morning), "2026-11-20")                                  # Friday's close
        self.assertEqual(prices.last_session(datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)), "2026-11-19")   # not out yet
        self.assertEqual(prices.last_session(datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)), "2026-11-20")    # Monday morning
        stale = {"day": "2026-11-21", "closes": [["2026-11-19", 145.98]], "checked": "2026-11-21T01:25:00+00:00"}
        later = sat_morning + timedelta(hours=8)
        self.assertTrue(prices.needs_fetch(stale, "2026-11-21", "2026-11-20", later))      # the 14% fall must not wait a day
        self.assertFalse(prices.needs_fetch(stale, "2026-11-21", "2026-11-20", sat_morning + timedelta(minutes=30)))   # not every run
        fresh = {**stale, "closes": [["2026-11-20", 125.53]]}
        self.assertFalse(prices.needs_fetch(fresh, "2026-11-21", "2026-11-20", later))
        self.assertTrue(prices.needs_fetch(fresh, "2026-11-22", "2026-11-20", later))      # a new day: asked once more

    def test_every_stock_in_the_universe_gets_its_price_not_only_the_first_80(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(prices, "CACHE", Path(tmp) / "prices.json"):
            asked = []
            fetch = lambda s: asked.append(s) or {"name": s, "currency": "USD", "closes": [["2026-11-20", 1.0]]}
            names = [f"T{i:03d}" for i in range(150)]
            prices.refresh(names, log=lambda m: None, fetcher=fetch, pause=0, now=datetime(2026, 11, 21, 9, tzinfo=timezone.utc), limit=200)
            self.assertEqual(len(asked), 151)   # the S&P 500 and all 150
            asked.clear()
            prices.refresh(names, log=lambda m: None, fetcher=fetch, pause=0, now=datetime(2026, 11, 21, 12, tzinfo=timezone.utc), limit=200)
            self.assertEqual(asked, [])         # all have Friday's close: nothing to do

    def test_dividend_yields_kept_from_before_the_fix_are_put_right_once(self):
        old = {"ticker": "NVDA", "consensus": "Buy", "dividend_yield_pct": 34.5}   # 0.345% multiplied by 100 again
        fixed = street.upgrade(old)
        self.assertEqual((fixed["dividend_yield_pct"], fixed["units"]), (0.345, street.UNITS))
        self.assertEqual(street.upgrade(fixed), fixed)                               # never twice
        self.assertEqual(street.upgrade({"ticker": "AMZN", "dividend_yield_pct": None})["units"], street.UNITS)
        # a run turns the stored row right and the card keeps it; a fresh read from TipRanks is marked right
        store, tmp = MemoryStore(), tempfile.mkdtemp()
        demo_data.fill(store, today=date(2026, 11, 13), log=lambda m: None, work=tmp)
        (Path(tmp) / "cards.json").unlink()   # as after a lost scratch folder: the next run reads the cards back from the store
        card = store.get("stocks", "MSFT")
        card["street"] = {k: v for k, v in card["street"].items() if k != "units"}
        card["street"]["dividend_yield_pct"] = 70.0
        card["h"] = "written-by-the-old-engine"
        store.set("stocks", "MSFT", card)
        demo_data.fill(store, today=date(2026, 11, 14), log=lambda m: None, work=tmp)
        st = store.get("stocks", "MSFT")["street"]
        self.assertEqual((st["dividend_yield_pct"], st["units"]), (0.7, street.UNITS))
        self.assertTrue(all((c.get("street") or {}).get("units", street.UNITS) == street.UNITS for c in store.all("stocks").values()))

    def test_each_card_has_a_short_story_in_plain_words(self):
        base = {"ticker": "NVDA", "name": "NVIDIA", "signal": "yes", "confidence_pct": 80, "calls": {"bullish": 5, "bearish": 1},
                "street": {"consensus": "Strong Buy", "upside_pct": 20.0}, "change_pct_day": -14.01, "change_pct_month": -30.0, "as_of": "2026-11-20",
                "bulls": [{"text": "Demand is ahead of supply.", "analyst": "A"}], "bears": [{"text": "Governance risk.", "analyst": "B"}],
                "days_to_earnings": 3, "track": {"right": 4, "scored": 5}}
        s = cards.story(base)
        self.assertTrue(s.startswith("Analysts clearly favour NVIDIA: 5 of 6 calls in the videos this month were bullish and Wall Street rates it Strong Buy"))
        self.assertIn("The price fell 14.0% on Friday, and is down 30% over the month.", s)
        self.assertIn("The bull case, from A: “Demand is ahead of supply.”", s)
        self.assertIn("earnings in 3 days", s)
        self.assertIn("right 4 of 5 times", s)
        # what goes against the signal comes after "though"; a split puts the two sides side by side
        against = cards.story({**base, "signal": "no", "confidence_pct": 40, "calls": {"bullish": 1, "bearish": 0}, "street": {"consensus": "Moderate Sell"}})
        self.assertIn("leaning against NVIDIA: Wall Street rates it Moderate Sell, though the one call in the videos this month was bullish.", against)
        split = cards.story({**base, "signal": "wait", "calls": {"bullish": 3, "bearish": 3}})
        self.assertIn("split on NVIDIA: 3 of 6 calls in the videos this month were bullish, while Wall Street", split)
        self.assertTrue(cards.story({**base, "signal": "none", "calls": {"bullish": 0, "bearish": 0}, "street": None, "bulls": [], "bears": []}).startswith("No analyst has given a view on NVIDIA lately."))

    def test_stars_need_three_scored_calls(self):
        self.assertIsNone(cards.stars({"scored": 2, "hit_pct": 100, "edge": 9}))
        self.assertEqual(cards.stars({"scored": 10, "hit_pct": 100, "edge": 12}), 5)
        self.assertEqual(cards.stars({"scored": 10, "hit_pct": 0, "edge": -12}), 0.5)
        self.assertEqual(cards.stars({"scored": 10, "hit_pct": 50, "edge": 0}), 2.5)

    def test_one_failing_step_does_not_lose_the_rest(self):
        store = MemoryStore()

        class Broken(demo_data.FakeTipRanks):
            def tools(self):
                raise RuntimeError("TipRanks is down")
        notes, closes, _ = demo_data.make(date(2026, 11, 16))
        for vid, n in notes.items():
            store.set("videos", vid, {"published": n["_video"]["published"], "notes": json.dumps(n)})
        sources = engine.load_sources()
        sources["base_tickers"] = ["NVDA", "AAPL"]
        sources["packs"] = []
        status = engine.run(store, {"site": "https://x/"}, sources=sources, now=datetime(2026, 11, 16, 12, tzinfo=timezone.utc), log=lambda m: None,
                            work=self.work, read_videos=False, price_fetcher=lambda s: closes[s], tipranks_client=Broken({}))
        self.assertTrue(status["ok"])   # Wall Street's view is extra: its failure is logged, not an error
        self.assertIsNone(store.get("stocks", "NVDA")["street"])
        self.assertIsNotNone(store.get("stocks", "NVDA")["price"])


class Emails(Globals):
    TODAY = date(2026, 11, 16)   # a Monday

    def cards(self):
        store = MemoryStore()
        demo_data.fill(store, today=self.TODAY, work=self.work, log=lambda m: None)
        return store, {c["ticker"]: c for c in store.all("stocks").values()}

    def test_what_a_user_is_told_about(self):
        _, all_cards = self.cards()
        no = next(t for t, c in all_cards.items() if c["signal"] == "no")
        user = {"email": "a@b.c", "stocks": [{"t": no, "shares": 100}, {"t": "KO"}, {"t": "NOPE"}]}
        view = mail.user_view(user, all_cards)
        self.assertEqual([r["ticker"] for r in view["rows"]], [no, "KO"])
        texts = [n["text"] for n in view["notes"]]
        self.assertIn(f"You own {no} and the experts are bearish on it", texts)
        self.assertIn(f"{no} is 100% of your portfolio", texts)

    def test_who_gets_which_email(self):
        view = {"rows": [{"ticker": "A"}], "notes": [{"changed": True, "on": "2026-11-16", "text": "x", "tone": "good"}]}
        quiet = {"rows": [{"ticker": "A"}], "notes": []}
        monday, saturday = self.TODAY, date(2026, 11, 21)   # the market day the email is about
        user = lambda **prefs: {"email": "a@b.c", "prefs": prefs}
        self.assertTrue(mail.wants(user(), "daily", quiet, monday))
        self.assertFalse(mail.wants(user(), "daily", quiet, saturday))      # the market was closed: nothing new
        self.assertFalse(mail.wants(user(daily="off"), "daily", view, monday))
        self.assertTrue(mail.wants(user(daily="changes"), "daily", view, monday))
        self.assertFalse(mail.wants(user(daily="changes"), "daily", quiet, monday))
        self.assertTrue(mail.wants(user(), "weekly", quiet, saturday))
        self.assertFalse(mail.wants(user(weekly=False), "weekly", quiet, saturday))
        self.assertFalse(mail.wants({"prefs": {}}, "daily", quiet, monday))                         # no address
        self.assertFalse(mail.wants(user(), "daily", {"rows": [], "notes": []}, monday))             # no stocks

    def test_a_change_is_news_once_for_the_daily_email_and_all_week_for_the_weekly(self):
        _, all_cards = self.cards()
        all_cards["KO"]["changed"] = {"from": "wait", "to": "yes", "on": "2026-11-16"}
        user = {"email": "a@b.c", "stocks": [{"t": "KO"}]}
        changed = lambda today, days: [n["text"] for n in mail.user_view(user, all_cards, today, days)["notes"] if n.get("changed")]
        self.assertEqual(changed(date(2026, 11, 17), 1), ["KO turned Bullish (was Split)"])   # the morning after: reported, and first
        self.assertEqual(changed(date(2026, 11, 18), 1), [])                              # not again
        self.assertEqual(changed(date(2026, 11, 21), 7), ["KO turned Bullish (was Split)"])   # the weekly summary still has it

    def test_an_account_with_broken_data_is_skipped_not_fatal(self):
        _, all_cards = self.cards()
        for stocks in ("not a list", [None, 5, {"t": 7}, {"t": "NVDA", "shares": "many"}, {"t": "AAPL", "shares": True}]):
            view = mail.user_view({"email": "a@b.c", "stocks": stocks, "prefs": "x"}, all_cards, self.TODAY)
            self.assertTrue(all(r["shares"] == 0 for r in view["rows"]))
        self.assertTrue(mail.wants({"email": "a@b.c", "prefs": "x"}, "daily", {"rows": [1], "notes": []}, self.TODAY))

    def test_the_email_shows_signals_and_never_how_much_is_owned(self):
        _, all_cards = self.cards()
        user = {"email": "a@b.c", "name": "Uma <b>Mahesh</b>", "stocks": [{"t": "NVDA", "shares": 123457, "cost": 98765}, {"t": "AAPL"}]}
        subject, page, text = mail.compose(user, mail.user_view(user, all_cards), "daily", self.TODAY, "https://md.example/")
        self.assertIn("Econova", subject)
        for needle in ("NVDA", "AAPL", "https://md.example/#/account", "not personal financial advice"):
            self.assertIn(needle, page)
            self.assertIn(needle, text)
        self.assertIn("Uma", page)
        self.assertNotIn("<b>Mahesh</b>", page)          # names are escaped
        for secret in ("123457", "123,457", "98765", "98,765"):
            self.assertNotIn(secret, page + text)         # share counts and prices paid stay out of email

    def test_each_user_gets_an_email_once_a_day(self):
        store, all_cards = self.cards()
        users = {"u1": {"email": "one@x.y", "stocks": [{"t": "NVDA"}]}, "u2": {"email": "two@x.y", "stocks": [{"t": "AAPL"}], "prefs": {"daily": "off"}},
                 "u3": {"email": "three@x.y", "stocks": []}}
        sent = []
        sender = lambda settings, to, subject, page, text: sent.append(to)
        settings = {"smtp_user": "me@x.y", "smtp_password": "p", "site": "https://md.example/"}
        self.assertEqual(mail.send_all(store, settings, users, all_cards, "weekly", self.TODAY, lambda m: None, sender), 2)   # u2 only turned the daily off
        self.assertEqual(mail.send_all(store, settings, users, all_cards, "daily", self.TODAY, lambda m: None, sender), 0)    # one email a day
        self.assertEqual(mail.send_all(store, settings, users, all_cards, "daily", self.TODAY + timedelta(days=1), lambda m: None, sender), 1)
        self.assertEqual(sent, ["one@x.y", "two@x.y", "one@x.y"])
        self.assertEqual(mail.send_all(store, {"site": "x"}, users, all_cards, "weekly", self.TODAY, lambda m: None, sender), 0)   # email not set up

    def test_the_run_sends_the_daily_email_at_its_hour_and_cleans_up_after_deleted_accounts(self):
        store = MemoryStore()
        demo_data.fill(store, today=self.TODAY, work=self.work, log=lambda m: None)
        store.set("mail", "someone-who-left", {"daily": "2026-11-01"})
        sent = []
        notes, closes, _ = demo_data.make(self.TODAY)
        sources = engine.load_sources()
        sources["base_tickers"], sources["packs"] = ["NVDA"], []
        settings = {"smtp_user": "me@x.y", "smtp_password": "p", "site": "https://md.example/"}
        go = lambda hour: engine.run(store, settings, sources=sources, now=datetime(2026, 11, 17, hour, tzinfo=timezone.utc), log=lambda m: None, work=self.work,
                                     read_videos=False, price_fetcher=lambda s: closes[s], mail_sender=lambda st, to, *a: sent.append(to))
        go(1)
        self.assertEqual(sent, [])                       # before the hour set in sources.json
        go(2)
        go(3)
        self.assertEqual(sent, ["you@example.com"])      # once: Tuesday 02:00 UTC, about Monday's market
        self.assertNotIn("someone-who-left", store.all("mail"))
        sent.clear()
        engine.run(store, settings, sources=sources, now=datetime(2026, 11, 23, 2, tzinfo=timezone.utc), log=lambda m: None, work=self.work,
                   read_videos=False, price_fetcher=lambda s: closes[s], mail_sender=lambda st, to, *a: sent.append(to))
        self.assertEqual(sent, [])                       # Monday 02:00 UTC would be about Sunday: no email

    def test_only_members_get_emails(self):
        store = MemoryStore()
        demo_data.fill(store, today=self.TODAY, work=self.work, log=lambda m: None)
        store.set("users", "stranger", {**demo_data.DEMO_USER, "email": "stranger@example.com"})   # signed up before the beta closed
        sent = []
        notes, closes, _ = demo_data.make(self.TODAY)
        sources = engine.load_sources()
        sources["base_tickers"], sources["packs"] = ["NVDA"], []
        settings = {"smtp_user": "me@x.y", "smtp_password": "p", "site": "https://md.example/", "members": "YOU@example.com, friend@example.com"}
        engine.run(store, settings, sources=sources, now=datetime(2026, 11, 17, 2, tzinfo=timezone.utc), log=lambda m: None, work=self.work,
                   read_videos=False, price_fetcher=lambda s: closes[s], mail_sender=lambda st, to, *a: sent.append(to))
        self.assertEqual(sent, ["you@example.com"])
        self.assertEqual(set(store.all("members")), {"you@example.com", "friend@example.com"})

    def test_the_site_address_comes_from_the_project_when_none_is_set(self):
        import os
        keep = {k: os.environ.pop(k, None) for k in ("SITE_URL", "FIREBASE_SERVICE_ACCOUNT")}
        try:
            os.environ["FIREBASE_SERVICE_ACCOUNT"] = json.dumps({"project_id": "my-digest"})
            self.assertEqual(mail.site_from_env(), "https://my-digest.web.app/")
            os.environ["SITE_URL"] = "https://digest.example.com"
            self.assertEqual(mail.site_from_env(), "https://digest.example.com/")
        finally:
            for k, v in keep.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


class Access(unittest.TestCase):
    """The private beta: the members list, from the BETA_MEMBERS secret into Firestore."""

    def test_the_list_is_read_from_the_secret_however_it_is_written(self):
        from cloud.engine import access
        self.assertEqual(access.parse("A@x.com, b@y.org\n c@z.in;A@x.com <d@w.co> not-an-address"), ["a@x.com", "b@y.org", "c@z.in", "d@w.co"])
        self.assertIsNone(access.parse(None))
        self.assertIsNone(access.parse("   "))

    def test_firestore_follows_the_list_and_a_broken_secret_changes_nothing(self):
        from cloud.engine import access
        store, day = MemoryStore(), date(2026, 11, 22)
        self.assertEqual(access.sync(store, "a@x.com, b@y.org", day, log=lambda m: None), {"a@x.com", "b@y.org"})
        self.assertEqual(access.sync(store, "b@y.org, c@z.in", day, log=lambda m: None), {"b@y.org", "c@z.in"})   # a removed, c added
        self.assertEqual(set(store.all("members")), {"b@y.org", "c@z.in"})
        self.assertEqual(access.sync(store, None, day, log=lambda m: None), {"b@y.org", "c@z.in"})                # not set: kept
        self.assertEqual(access.sync(store, "oops, no addresses", day, log=lambda m: None), {"b@y.org", "c@z.in"})   # a typo: kept
        users = {"1": {"email": "B@Y.org"}, "2": {"email": "x@q.com"}, "3": {}}
        self.assertEqual(list(access.only_members(users, {"b@y.org"})), ["1"])

    def test_the_rules_keep_everything_behind_the_members_list(self):
        rules = (Path(__file__).resolve().parent.parent / "cloud" / "firestore.rules").read_text(encoding="utf-8")
        for path in ("stocks/{ticker}", "charts/{ticker}", "market/{page}", "public/{page}"):
            self.assertRegex(rules, r"match /" + re.escape(path) + r" +\{ allow read: if member\(\); \}")
        self.assertNotIn("if true", rules)
        self.assertIn("allow create, update: if mine(uid) && member() && validUser", rules)


class Symbols(unittest.TestCase):
    def test_the_us_lists_drop_tests_and_warrants_and_tidy_names(self):
        text = ("Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
                "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\nGOOGL|Alphabet Inc. - Class A Common Stock|Q|N|N|100|N|N\n"
                "ZTEST|Test Company|Q|Y|N|100|N|N\nABCDW|Some Corp - Warrants|Q|N|N|100|N|N\nFile Creation Time: 1116202618:00|||||||\n")
        self.assertEqual(make_symbols.us_rows(text), [("AAPL", "Apple Inc."), ("GOOGL", "Alphabet Inc.")])
        other = ("ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
                 "BRK.B|Berkshire Hathaway Inc. Class B Common Stock|N|BRK.B|N|100|N|BRK-B\n")
        self.assertEqual(make_symbols.us_rows(other), [("BRK-B", "Berkshire Hathaway Inc.")])

    def test_a_company_without_a_ticker_is_not_made_one(self):
        import insights
        table = insights.load_tickers()
        self.assertIsNone(insights.symbol_for("Anthropic", "", table))          # private: no card, no price lookups
        self.assertIsNone(insights.symbol_for("Databricks", "", table))
        self.assertEqual(insights.symbol_for("Target", "", table), "TGT")       # found by name in the search list
        self.assertEqual(insights.symbol_for("Costco", "", table), "COST")
        self.assertEqual(insights.symbol_for("Berkshire Hathaway", "BRK.B", table), "BRK-B")   # the share class as prices write it
        self.assertEqual(insights.symbol_for("Nvidia", "NVDA", table), "NVDA")

    def test_the_file_in_the_repository_is_a_sorted_list_of_pairs(self):
        rows = json.loads((Path(make_symbols.OUT)).read_text(encoding="utf-8"))
        # the full US list is kept here, so a deploy on a day Nasdaq Trader is down still searches every stock
        self.assertGreater(len(rows), 8000)
        self.assertTrue({"AAPL", "COST", "BRK-B", "SPY", "PLTR"} <= {r[0] for r in rows})
        self.assertTrue(all(isinstance(r, list) and len(r) == 2 and prices.clean(r[0]) == r[0] and r[1] for r in rows))


class Sources(unittest.TestCase):
    def test_sources_json_is_complete(self):
        s = engine.load_sources()
        self.assertGreaterEqual(len(s["channels"]), 3)
        self.assertTrue(all(digest_channel(c["url"]) for c in s["channels"]))
        for key in ("videos_per_day", "videos_per_run", "max_video_minutes", "lookback_hours", "tipranks_batch", "tipranks_calls_per_day", "tipranks_reserve"):
            self.assertIn(key, s["limits"])
        tickers = s["base_tickers"] + [t for p in s["packs"] for t in p["tickers"]]
        self.assertTrue(all(prices.clean(t) == t for t in tickers))
        self.assertTrue(all(t in s["base_tickers"] for p in s["packs"] for t in p["tickers"]), "every pack stock should be covered from day one")


class TrackRecord(unittest.TestCase):
    """Econova grading itself: the replayed signal, the live one, and the shows."""
    END = date(2026, 11, 13)

    def setUp(self):
        self.days = [d.isoformat() for d in demo_data.trading_days(self.END, 80)]
        grow = lambda rate: [[d, round(100 * (1 + rate) ** i, 4)] for i, d in enumerate(self.days)]
        self.cache = {"^GSPC": {"closes": grow(0)}, "UP": {"closes": grow(0.004)}, "DOWN": {"closes": grow(-0.004)}, "FLAT": {"closes": grow(0)}}

    def call(self, t, view, analyst, day, channel="Show A"):
        return {"ticker": t, "view": view, "analyst": analyst, "day": day, "channel": channel, "video_id": analyst + day, "reason": "", "link": ""}

    def test_bullish_picks_that_rose_and_bearish_picks_that_fell_are_right(self):
        d = self.days
        calls = [self.call("UP", "bullish", a, d[i]) for a in ("Ann", "Bo") for i in range(0, 60, 4)]
        calls += [self.call("DOWN", "bearish", a, d[i]) for a in ("Ann", "Bo") for i in range(0, 60, 4)]
        r = record.replay(calls, self.cache)
        self.assertGreaterEqual(len(r["checks"]), 5)
        self.assertEqual((r["yes"]["hit_pct"], r["no"]["hit_pct"]), (100, 100))
        self.assertGreater(r["yes"]["excess"], 5)
        self.assertLess(r["no"]["excess"], -5)
        self.assertTrue(all(c["e"] <= d[-1] for c in r["checks"]), "every check is judged on prices that exist")
        self.assertEqual(r["checks"][-1]["e"], d[-1], "the newest month is always in")

    def test_a_check_uses_only_the_calls_made_before_it(self):
        d = self.days
        late = [self.call("UP", "bullish", a, d[60]) for a in ("Ann", "Bo")]   # said after every check that can be judged
        early = [self.call("FLAT", "bullish", "Cy", d[0]), self.call("FLAT", "bearish", "Di", d[0])]
        r = record.replay(early + late, self.cache)
        self.assertNotIn("UP", {t for c in r["checks"] for t in c["picks"]})

    def test_one_or_no_call_is_not_a_signal_and_a_neutral_call_withdraws_a_vote(self):
        d0 = date.fromisoformat(self.days[10])
        self.assertIsNone(record.signal_of([], d0))
        self.assertEqual(record.signal_of([self.call("X", "bullish", "Ann", self.days[1]), self.call("X", "bullish", "Bo", self.days[2])], d0), "yes")
        turned = [self.call("X", "bullish", "Ann", self.days[1]), self.call("X", "neutral", "Ann", self.days[5]), self.call("X", "bearish", "Bo", self.days[2])]
        self.assertEqual(record.signal_of(turned, d0), "no")

    def test_the_live_record_judges_each_signal_until_it_changed(self):
        d = self.days
        card = {"history": [{"d": d[40], "s": "yes", "c": 70}, {"d": d[50], "s": "wait", "c": 30}, {"d": d[60], "s": "yes", "c": 60}, {"d": d[78], "s": "no", "c": 40}]}
        lv = record.live({"UP": card}, self.cache, self.END)
        by = {r["from"]: r for r in lv["rows"]}
        self.assertTrue(by[d[40]]["right"] and by[d[40]]["to"] == d[50])
        self.assertTrue(by[d[60]]["right"])
        self.assertNotIn("excess", by[d[78]], "a day old: too new to judge")
        self.assertTrue(by[d[78]]["open"])
        self.assertEqual((lv["yes"]["n"], lv["yes"]["right"], lv["waiting"], lv["since"]), (2, 2, 1, d[40]))

    def test_shows_with_too_few_scored_calls_come_last(self):
        d = self.days
        calls = [self.call("UP", "bullish", "Ann", d[i], "Big Show") for i in range(0, 40, 4)] + [self.call("UP", "bullish", "Bo", d[0], "Tiny Show")]
        rows = record.shows(calls, self.cache)
        self.assertEqual([r["channel"] for r in rows], ["Big Show", "Tiny Show"])
        self.assertEqual((rows[0]["hit_pct"], rows[0]["analysts"]), (100, 1))

    def test_the_headline_waits_for_enough_picks(self):
        self.assertIsNone(record.headline({"replay": {"yes": {"n": 4, "excess": 3.0}}}))
        h = record.headline({"replay": {"yes": {"n": 20, "hit_pct": 60, "excess": 1.5}, "no": {"n": 5, "excess": -1.0}, "from": "a", "to": "b"}})
        self.assertEqual((h["yes_hit_pct"], h["n"]), (60, 25))


class WhoWasRight(unittest.TestCase):
    """Per stock and per analyst: who has been right about it, the top-rated view, the mood by month, and actions."""
    END, setUp, call = TrackRecord.END, TrackRecord.setUp, TrackRecord.call

    def test_each_call_is_new_upgraded_downgraded_or_reiterated(self):
        d = self.days
        calls = [self.call("UP", "bearish", "Ann", d[1]), self.call("UP", "neutral", "Ann", d[2]), self.call("UP", "bullish", "Ann", d[3]),
                 self.call("UP", "bullish", "Ann", d[4]), self.call("UP", "bearish", "Ann", d[5]), self.call("DOWN", "bullish", "Ann", d[5])]
        acts = cards.actions(calls)
        self.assertEqual([acts[cards._key(c)] for c in calls], ["new", "upgraded", "upgraded", "reiterated", "downgraded", "new"])

    def test_who_has_been_right_about_a_stock_comes_first(self):
        d = self.days
        calls = [self.call("UP", "bullish", "Right", d[i]) for i in (0, 5, 10)] + [self.call("UP", "bearish", "Wrong", d[i]) for i in (0, 5, 10, 15)]
        calls += [self.call("UP", "bullish", "Fresh", d[-1]), self.call("DOWN", "bullish", "Right", d[0])]
        rows = cards.experts_on("UP", calls, self.cache, {})
        self.assertEqual([r["analyst"] for r in rows], ["Right", "Wrong", "Fresh"])   # too recent to judge comes last
        self.assertEqual((rows[0]["right"], rows[0]["scored"], rows[0]["calls"]), (3, 3, 3))   # calls on other stocks are not counted
        self.assertEqual((rows[1]["hit_pct"], rows[2]["scored"]), (0, 0))

    def test_the_top_rated_view_counts_only_well_rated_analysts_latest_calls(self):
        d, today = self.days, date.fromisoformat(self.days[-1])
        good = {"scored": 10, "hit_pct": 80, "edge": 8}
        records = {"Star": good, "Star2": good, "Weak": {"scored": 10, "hit_pct": 20, "edge": -8}}
        calls = [self.call("UP", "bearish", "Star", d[60]), self.call("UP", "bullish", "Star", d[70]), self.call("UP", "bullish", "Star2", d[65]),
                 self.call("UP", "bearish", "Weak", d[70])]
        v = cards.top_view("UP", calls, records, today)
        self.assertEqual((v["bullish"], v["bearish"], v["analysts"]), (2, 0, ["Star", "Star2"]))
        self.assertIsNone(cards.top_view("UP", calls[-1:], records, today))

    def test_the_mood_by_month_covers_the_last_four_months(self):
        today = date(2026, 11, 13)
        calls = [self.call("UP", "bullish", "A", "2026-11-02"), self.call("UP", "bearish", "B", "2026-09-10"), self.call("UP", "neutral", "C", "2026-09-11"),
                 self.call("UP", "bullish", "D", "2026-06-01"), self.call("DOWN", "bullish", "E", "2026-11-03")]
        rows = cards.trend("UP", calls, today)
        self.assertEqual([r["m"] for r in rows], ["2026-08", "2026-09", "2026-10", "2026-11"])
        self.assertEqual([(r["bullish"], r["bearish"], r["other"]) for r in rows], [(0, 0, 0), (0, 1, 1), (0, 0, 0), (1, 0, 0)])
        self.assertIsNone(cards.trend("FLAT", calls, today))

    def test_an_analysts_coverage_newest_first_with_the_record_on_each(self):
        d = self.days
        calls = [self.call("UP", "bullish", "Ann", d[0]), self.call("UP", "bullish", "Ann", d[10]), self.call("DOWN", "bearish", "Ann", d[20]), self.call("UP", "bearish", "Bo", d[30])]
        rows = cards.coverage("Ann", calls, self.cache)
        self.assertEqual([(r["ticker"], r["calls"], r["hit_pct"]) for r in rows], [("DOWN", 1, 100), ("UP", 2, 100)])


class MarketOdds(Globals):
    """What the money says: Kalshi's public odds, read without the network here."""
    NOW = datetime(2026, 11, 27, 9, tzinfo=timezone.utc)

    def m(self, event, sub, bid, ask, close, last=None):
        return {"event_ticker": event, "yes_sub_title": sub, "yes_bid_dollars": f"{bid:.4f}", "yes_ask_dollars": f"{ask:.4f}",
                "last_price_dollars": f"{(last if last is not None else bid):.4f}", "close_time": close + "T19:00:00Z", "title": f"{event} question"}

    def test_odds_are_the_middle_of_a_tight_market_else_the_last_trade(self):
        self.assertEqual(odds.chance(self.m("E", "x", 0.60, 0.64, "2026-12-09")), 62)
        self.assertEqual(odds.chance(self.m("E", "x", 0.10, 0.60, "2026-12-09", last=0.33)), 33)   # too wide a spread to trust
        self.assertIsNone(odds.chance({"yes_bid_dollars": "0", "yes_ask_dollars": "0", "last_price_dollars": "0"}))

    def test_the_soonest_open_event_is_read_and_next_years_recession(self):
        fed = [self.m("FED-26DEC", "Hold", 0.61, 0.63, "2026-12-09"), self.m("FED-26DEC", "Cut 25bps", 0.34, 0.36, "2026-12-09"),
               self.m("FED-26DEC", "Hike >25bps", 0.0, 0.01, "2026-12-09"), self.m("FED-27JAN", "Hold", 0.5, 0.52, "2027-01-27"),
               self.m("FED-26NOV", "Hold", 0.9, 0.92, "2026-11-01")]   # already closed
        e = odds.event_of("fed", "KXFEDDECISION", "The Fed", fed, self.NOW)
        self.assertEqual((e["event"], [r["label"] for r in e["rows"]]), ("FED-26DEC", ["Hold", "Cut 25bps"]))   # a 0% outcome is left out
        rec = [self.m("REC-26", "Yes", 0.02, 0.03, "2027-01-31"), self.m("REC-27", "Yes", 0.21, 0.23, "2028-01-31")]
        self.assertEqual(odds.event_of("recession", "KXRECSSNBER", "A recession", rec, self.NOW)["rows"], [{"label": "Yes", "pct": 22}])

    def test_a_ladder_keeps_the_likely_the_coin_toss_and_the_unlikely_step(self):
        steps = [self.m("CPI-26NOV", f"Above {x / 10:.1f}%", p / 100, p / 100 + 0.01, "2026-12-10") for x, p in ((-2, 96), (-1, 84), (0, 51), (1, 30), (2, 14), (3, 4))]
        rows = odds.event_of("cpi", "KXCPI", "CPI", steps, self.NOW)["rows"]
        self.assertEqual([r["label"] for r in rows], ["Above -0.1%", "Above 0.0%", "Above 0.2%"])

    def test_one_series_failing_keeps_the_others_and_none_means_nothing(self):
        def fetcher(series):
            if series == "KXCPI":
                raise OSError("down")
            return [self.m(series + "-1", "Yes", 0.4, 0.42, "2026-12-20")]
        got = odds.read(now=self.NOW, fetcher=fetcher, log=lambda m: None)
        self.assertEqual([e["key"] for e in got["events"]], ["fed", "jobs", "recession"])
        self.assertIsNone(odds.read(now=self.NOW, fetcher=lambda s: [], log=lambda m: None))

    def test_the_engine_reads_the_odds_once_a_day(self):
        calls = []
        def reader(now=None, log=print):
            calls.append(now)
            return {"events": [{"key": "fed", "rows": []}], "at": now.isoformat(), "source": "Kalshi"}
        store = MemoryStore()
        sources = {**engine.load_sources(), "channels": []}
        for hour in (3, 4):
            engine.run(store, {"site": "https://x/"}, sources=sources, now=datetime(2026, 11, 27, hour, tzinfo=timezone.utc), log=lambda m: None, work=self.work,
                       read_videos=False, price_fetcher=lambda s: (_ for _ in ()).throw(prices.PriceError("none")), odds_reader=reader)
        self.assertEqual(len(calls), 1)
        self.assertEqual(store.get("market", "odds")["source"], "Kalshi")


class TenThousand(unittest.TestCase):
    def test_10000_follows_the_bullish_picks_month_by_month_without_overlap(self):
        checks = [{"d": "2026-08-03", "e": "2026-09-01", "n_yes": 3, "yes_ret": 10.0, "sp500": 2.0},
                  {"d": "2026-08-10", "e": "2026-09-08", "n_yes": 4, "yes_ret": 50.0, "sp500": 9.0},   # inside the first month: skipped
                  {"d": "2026-09-02", "e": "2026-10-01", "n_yes": 0, "yes_ret": None, "sp500": -5.0},   # no Bullish pick: cash
                  {"d": "2026-10-05", "e": "2026-11-03", "n_yes": 2, "yes_ret": -10.0, "sp500": 1.0}]
        g = record.growth(checks)
        self.assertEqual((g["value"], g["sp500"]), (9900, 9787))   # S&P: 1.02 x 0.95 x 1.01
        self.assertEqual([x["v"] for x in g["path"]], [11000, 11000, 9900])
        self.assertEqual((g["from"], g["to"]), ("2026-08-03", "2026-11-03"))
        self.assertIsNone(record.growth([]))


class FollowsAndFeedback(unittest.TestCase):
    TODAY = date(2026, 11, 17)
    EXPERTS = [{"analyst": "Dan Ives", "stars": 4.5, "recent": [{"day": "2026-11-16", "view": "bullish", "ticker": "TSLA"}, {"day": "2026-11-01", "view": "bullish", "ticker": "AAPL"}]},
               {"analyst": "Tom Lee", "stars": None, "recent": [{"day": "2026-11-16", "view": "neutral", "ticker": "SPY"}]}]

    def test_new_calls_from_followed_analysts_are_news(self):
        user = {"email": "a@b.c", "follows": ["Dan Ives", "Tom Lee", 7], "stocks": [{"t": "KO"}]}
        got = mail.followed_calls(user, self.EXPERTS, self.TODAY)
        self.assertEqual([n["text"] for n in got], ["Dan Ives (4.5 stars) is bullish on TSLA"])   # an old call and a neutral one are not news
        self.assertEqual(mail.followed_calls({"follows": "Dan Ives"}, self.EXPERTS, self.TODAY), [])
        cards_ = {"KO": {"ticker": "KO", "name": "Coca-Cola", "price": 60, "currency": "USD", "signal": "wait", "confidence_pct": 30, "calls": {}}}
        view = mail.user_view({**user, "prefs": {"daily": "changes"}}, cards_, self.TODAY, analysts=self.EXPERTS)
        self.assertTrue(mail.wants({**user, "prefs": {"daily": "changes"}}, "daily", view, self.TODAY), "a followed analyst's call is reason enough")
        subject, page, text = mail.compose(user, view, "daily", self.TODAY, "https://x.example/")
        self.assertIn("Dan Ives (4.5 stars) is bullish on TSLA", page)

    def test_feedback_is_emailed_to_the_team_then_removed(self):
        store, sent = MemoryStore(), []
        store.set("feedback", "abc12345", {"by": "u1", "email": "m@x.y", "text": "Love it <b>but</b>", "page": "#/", "at": "2026-11-17T10:00:00"})
        settings = {"smtp_user": "team@x.y", "smtp_password": "pw", "site": "https://x.example/"}
        self.assertEqual(mail.forward_feedback(store, {**settings, "smtp_password": ""}, log=lambda m: None, sender=lambda *a: sent.append(a)), 0)
        self.assertEqual(len(store.all("feedback")), 1, "kept while email is not set up")
        self.assertEqual(mail.forward_feedback(store, settings, log=lambda m: None, sender=lambda *a: sent.append(a)), 1)
        to, subject, html_body = sent[0][1], sent[0][2], sent[0][3]
        self.assertEqual((to, subject), ("team@x.y", "Econova feedback: 1 new note"))
        self.assertIn("&lt;b&gt;but&lt;/b&gt;", html_body)
        self.assertEqual(store.all("feedback"), {})

    def test_feedback_that_fails_to_send_stays(self):
        store = MemoryStore()
        store.set("feedback", "abc12345", {"text": "hi"})
        def broken(*a):
            raise OSError("no network")
        with self.assertRaises(OSError):
            mail.forward_feedback(store, {"smtp_user": "t@x.y", "smtp_password": "pw"}, log=lambda m: None, sender=broken)
        self.assertEqual(len(store.all("feedback")), 1)


def digest_channel(url):
    import re
    return re.match(r"https://www\.youtube\.com/@[\w.\-]+$", url)


if __name__ == "__main__":
    unittest.main()
