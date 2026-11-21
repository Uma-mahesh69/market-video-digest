"""Tests for the cloud version: the shared engine (cloud/engine) and its tools. No network, no Firebase: the engine
runs against an in-memory store with invented data. Run from the project folder: python -m unittest -v"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import digest
import prices
import tipranks

from cloud.engine import cards, mail, run as engine, street, videos
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
        self.assertEqual(sorted(store.all("market")), ["analysts", "calendar", "meta", "overview", "status", "videos"])
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
        videos_and_user = len(store.all("videos")) + 1   # the example data is put in again by fill()
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
        self.assertIn(f"You own {no}: analysts say No", texts)
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
        self.assertEqual(changed(date(2026, 11, 17), 1), ["KO turned YES (was WAIT)"])   # the morning after: reported, and first
        self.assertEqual(changed(date(2026, 11, 18), 1), [])                              # not again
        self.assertEqual(changed(date(2026, 11, 21), 7), ["KO turned YES (was WAIT)"])   # the weekly summary still has it

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
        self.assertIn("Market Digest", subject)
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


def digest_channel(url):
    import re
    return re.match(r"https://www\.youtube\.com/@[\w.\-]+$", url)


if __name__ == "__main__":
    unittest.main()
