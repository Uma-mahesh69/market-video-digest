"""Tests for the parts that make Market Digest a product: the daily run with its retries, one-click updates, the
connection to the Claude desktop app, and the tools Claude gets (mcp_server.py). No network, nothing outside a temp folder.
Run from the project folder: python -m unittest -v"""
import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import app
import digest
import mcp_server

KEY = "AIzaSyA1234567890abcdefghijklmnopqrstuv"


class Folder(unittest.TestCase):
    """Each test gets its own program folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(digest, k) for k in ("HERE", "CONFIG", "OUT_DIR", "LAST_RUN", "STATE", "CACHE_DIR", "JSON_DIR")}
        digest.HERE, digest.CONFIG, digest.OUT_DIR = self.tmp, self.tmp / "digest_config.json", self.tmp / "digests"
        digest.LAST_RUN, digest.STATE = self.tmp / "last_run.json", self.tmp / "state.json"
        digest.CACHE_DIR, digest.JSON_DIR = self.tmp / "digest_cache", self.tmp / "digest_json"
        (self.tmp / "VERSION").write_text("1.2.0\n")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(digest, k, v)


class DailyRun(Folder):
    def run_with(self, codes):
        calls = []

        def fake(cmd, **kw):
            kw["stdout"].write("ran\n")
            if cmd[-1] == "--due":   # the weekly and monthly digests, after a good daily run
                calls.append("period")
                return mock.Mock(returncode=0)
            calls.append(cmd)
            return mock.Mock(returncode=codes[len([c for c in calls if c != "period"]) - 1])
        with mock.patch.object(app.subprocess, "run", fake), mock.patch.object(app.time, "sleep") as sleep, \
                mock.patch.object(app, "notify") as notify:
            code = app.daily_run()
        return code, calls, sleep, notify

    def test_a_good_run_runs_once(self):
        code, calls, sleep, notify = self.run_with([0])
        self.assertEqual((code, len(calls)), (0, 2))
        self.assertTrue(calls[0][-1].endswith("digest.py"))
        self.assertEqual(calls[1], "period")   # then the weekly and monthly digests, if due
        sleep.assert_not_called()
        notify.assert_not_called()

    def test_a_failed_run_is_tried_again_and_logged(self):
        code, calls, sleep, notify = self.run_with([1, 1, 0])
        self.assertEqual((code, len(calls)), (0, 4))
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual((self.tmp / "digest.log").read_text().count("trying again in 30 minutes"), 2)
        notify.assert_not_called()

    def test_after_the_last_try_a_notice_says_so(self):
        code, calls, sleep, notify = self.run_with([1, 1, 1, 1])
        self.assertEqual((code, len(calls)), (1, 4))
        self.assertNotIn("period", calls)   # no weekly digest after a failed day
        notify.assert_called_once()


class Updates(Folder):
    def release(self, version="1.3.0", drop=None, **replace):
        names = ["app.py", "VERSION", "MANIFEST", "digest.py", "chat.py", "tickers.json", "brand_new.py"]   # a release may add a file
        files = {name: b"{}" if name.endswith(".json") else f"# {name} {version}\n".encode() for name in names}
        files["VERSION"], files["MANIFEST"] = version.encode(), "\n".join(names).encode()
        files.update({k.replace("__", "."): v for k, v in replace.items()})
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in files.items():
                if name != drop:
                    z.writestr("market-video-digest-master/" + name, data)
        return lambda: buf.getvalue()

    def test_the_manifest_matches_the_files_in_the_project(self):
        root = Path(app.__file__).resolve().parent
        names = app.program_files((root / "MANIFEST").read_text())
        self.assertEqual([n for n in names if not (root / n).exists()], [])
        for must in ("app.py", "app.html", "mcp_server.py", "digest.py", "chat.py", "ytmd", "VERSION", "MANIFEST"):
            self.assertIn(must, names)

    def test_versions_compare_as_numbers(self):
        self.assertGreater(app.version_key("1.10.0"), app.version_key("1.9.3"))
        self.assertEqual(app.version(), "1.2.0")

    def test_an_update_replaces_the_program_and_nothing_else(self):
        digest.CONFIG.write_text(json.dumps({"gemini_api_key": KEY}))
        self.assertEqual(app.apply_update(self.release()), "1.3.0")
        self.assertEqual(app.version(), "1.3.0")
        self.assertIn("1.3.0", (self.tmp / "digest.py").read_text())
        self.assertEqual(json.loads(digest.CONFIG.read_text())["gemini_api_key"], KEY)   # settings untouched
        self.assertEqual([p.name for p in self.tmp.glob("*.new")], [])
        self.assertTrue((self.tmp / "brand_new.py").exists())   # a file the old version never knew of

    def test_a_broken_or_incomplete_update_changes_nothing(self):
        (self.tmp / "digest.py").write_text("# the working one\n")
        for bad in (self.release(digest__py=b"def broken(:\n"), self.release(drop="chat.py"), self.release(version="1.2.0"),
                    self.release(drop="MANIFEST"), self.release(MANIFEST=b"app.py\nVERSION\n../evil.py\n"), lambda: b"not a zip"):
            with self.assertRaises(RuntimeError):
                app.apply_update(bad)
            self.assertEqual((self.tmp / "digest.py").read_text(), "# the working one\n")
            self.assertEqual(app.version(), "1.2.0")

    def test_the_page_is_told_only_about_a_newer_version(self):
        app.Update.checked = 9e12   # no lookup during the test
        app.Update.latest = "1.3.0"
        self.assertEqual(app.Update.info(), {"version": "1.2.0", "latest": "1.3.0"})
        app.Update.latest = "1.2.0"
        self.assertIsNone(app.Update.info()["latest"])


class Claude(Folder):
    def setUp(self):
        super().setUp()
        self.cfg = self.tmp / "home" / "Claude" / "claude_desktop_config.json"
        self.paths = mock.patch.object(app, "claude_config_paths", lambda: [self.cfg])
        self.paths.start()

    def tearDown(self):
        self.paths.stop()
        super().tearDown()

    def test_without_the_claude_app_nothing_is_written(self):
        self.assertEqual(app.claude_status(), {"installed": False, "connected": False})
        with self.assertRaises(ValueError):
            app.claude_connect()
        self.assertFalse(self.cfg.exists())

    def test_connecting_keeps_what_claude_already_had(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
        self.assertEqual(app.claude_connect(), {"installed": True, "connected": True})
        doc = json.loads(self.cfg.read_text())
        self.assertEqual(doc["theme"], "dark")
        self.assertEqual(doc["mcpServers"]["other"], {"command": "x"})
        self.assertTrue(doc["mcpServers"]["market-digest"]["args"][0].endswith("mcp_server.py"))
        self.assertTrue(self.cfg.with_suffix(".before-market-digest.json").exists())   # a copy of the file as it was
        self.assertFalse(app.claude_connect(on=False)["connected"])
        self.assertEqual(list(json.loads(self.cfg.read_text())["mcpServers"]), ["other"])

    def test_a_settings_file_that_cannot_be_read_is_left_alone(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text("{ not json")
        with self.assertRaises(ValueError):
            app.claude_connect()
        self.assertEqual(self.cfg.read_text(), "{ not json")


class ClaudeTools(Folder):
    def setUp(self):
        super().setUp()
        digest.CACHE_DIR.mkdir()
        mcp_server.chat._meta.clear()
        now = datetime.now(timezone.utc)
        self.video(1, "Dan Ives: Nvidia has more room", "Dan Ives", now - timedelta(days=1),
                   [{"name": "Nvidia", "ticker": "NVDA", "view": "bullish", "reason": "AI demand", "analyst": "Dan Ives", "seconds": 95}])
        self.video(2, "Mike Wilson turns cautious", "Mike Wilson", now - timedelta(days=2),
                   [{"name": "Nvidia", "ticker": "", "view": "bearish", "reason": "valuation", "analyst": "", "seconds": None}])
        self.video(3, "An old one", "Dan Ives", now - timedelta(days=40), [{"name": "Tesla", "ticker": "TSLA", "view": "bullish", "reason": "r"}])
        digest.CONFIG.write_text(json.dumps({"gemini_api_key": KEY, "smtp_password": "abcdefghijklmnop", "channels": ["@TheStreet"], "analysts": ["Dan Ives"]}))

    def video(self, n, title, speaker, when, stocks):
        vid = f"video{n:06d}"
        notes = {"summary": "s", "speakers": [{"name": speaker, "role": ""}], "key_points": [{"point": "p", "seconds": 70}], "stocks": stocks,
                 "_video": {"id": vid, "title": title, "channel": "CNBC Television", "published": when.isoformat(),
                            "url": f"https://www.youtube.com/watch?v={vid}", "duration": 600}}
        (digest.CACHE_DIR / f"{vid}.json").write_text(json.dumps(notes))

    def call(self, name, **arguments):
        reply = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        result = reply["result"]
        return result["isError"], result["content"][0]["text"]

    def test_the_handshake_lists_the_tools_and_prompts(self):
        hello = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})["result"]
        self.assertEqual(hello["protocolVersion"], "2025-06-18")
        self.assertIn("not investment advice", hello["instructions"])
        self.assertIsNone(mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual(len(tools), 10)
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")
        self.assertEqual(len(mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/list"})["result"]["prompts"]), 3)
        self.assertEqual(mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"})["error"]["code"], -32601)

    def test_calls_on_a_stock_come_with_who_why_and_a_link(self):
        err, body = self.call("stock_calls", ticker="nvda")
        calls = json.loads(body)["calls"]
        self.assertFalse(err)
        self.assertEqual([(c["view"], c["analyst"]) for c in calls], [("bullish", "Dan Ives"), ("bearish", "Mike Wilson")])   # the lone speaker fills in
        self.assertTrue(calls[0]["link"].endswith("&t=95s"))
        self.assertEqual(json.loads(self.call("stock_calls")[1])["stocks"][0], {"ticker": "NVDA", "name": "Nvidia", "bullish": 1, "bearish": 1, "neutral": 0, "mixed": 0})
        self.assertEqual(json.loads(self.call("stock_calls", ticker="TSLA", days=14)[1])["count"], 0)   # the old video is outside 14 days

    def test_videos_filter_by_analyst(self):
        videos = json.loads(self.call("list_videos", analyst="wilson")[1])["videos"]
        self.assertEqual([v["title"] for v in videos], ["Mike Wilson turns cautious"])

    def test_no_tool_returns_a_key_or_password(self):
        for name in ("digest_overview", "list_videos", "stock_calls"):
            body = self.call(name)[1]
            self.assertNotIn(KEY, body)
            self.assertNotIn("abcdefghijklmnop", body)

    def test_following_changes_are_checked_like_the_settings_page(self):
        err, body = self.call("update_following", add_channels=["not a channel"])
        self.assertTrue(err)
        self.assertIn("Nothing was changed", body)
        err, body = self.call("update_following", add_analysts=["Mike Wilson"], remove_analysts=["dan ives"])
        self.assertFalse(err)
        saved = json.loads(digest.CONFIG.read_text())
        self.assertEqual(saved["analysts"], ["Mike Wilson"])
        self.assertEqual(saved["gemini_api_key"], KEY)

    def test_a_wrong_argument_is_an_answer_not_a_crash(self):
        self.assertTrue(self.call("get_video", video_id="nope")[0])
        self.assertTrue(self.call("stock_calls", nonsense=1)[0])
        self.assertTrue(self.call("no_such_tool")[0])


class Delivery(unittest.TestCase):
    def test_opening_the_digest_is_on_unless_email_is_set_up(self):
        self.assertTrue(app.open_when_ready({}))
        self.assertFalse(app.open_when_ready({"email_to": ["a@example.com"]}))
        self.assertTrue(app.open_when_ready({"email_to": ["a@example.com"], "open_when_ready": True}))
        cfg, errors = app.merged({"gemini_api_key": KEY, "channels": ["@TheStreet"], "notify": False, "open_when_ready": False}, {})
        self.assertEqual((errors, cfg["notify"], cfg["open_when_ready"]), ({}, False, False))


if __name__ == "__main__":
    unittest.main()


class EmailService(Folder):
    """The app against a stand-in for the Apps Script email service, which answers a POST with a redirect to the result."""

    def setUp(self):
        super().setUp()
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        test = self
        self.requests, self.answers = [], {}

        class Fake(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.requests.append(req)
                answer = {"ok": True}
                if req["action"] == "confirm":
                    answer = {"ok": True, "key": "k" * 64} if req.get("code") == "123456" else {"ok": False, "error": "That code is not right."}
                test.answers[str(len(test.requests))] = answer
                self.send_response(302)
                self.send_header("Location", f"/echo?id={len(test.requests)}")
                self.end_headers()

            def do_GET(self):
                body = json.dumps(test.answers[self.path.split("=")[-1]]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        self.service = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.service.serve_forever, daemon=True).start()
        self.patch = mock.patch.object(digest, "service", lambda: {"url": f"http://127.0.0.1:{self.service.server_address[1]}/exec", "token": "t"})
        self.patch.start()
        digest.CONFIG.write_text(json.dumps({"gemini_api_key": KEY, "channels": ["@TheStreet"]}))

    def tearDown(self):
        self.patch.stop()
        self.service.shutdown()
        self.service.server_close()
        super().tearDown()

    def test_confirm_then_send_through_the_service(self):
        with self.assertRaises(digest.ServiceError):
            digest.call_service("confirm", email="a@example.com", code="000000")
        answer = digest.call_service("confirm", email="a@example.com", code="123456")   # after the redirect, like Apps Script
        cfg = {"gemini_api_key": KEY, "email_to": ["a@example.com"], "email_key": answer["key"]}
        self.assertTrue(digest.send(cfg, "Digest", "<p>hi</p>", "hi"))
        self.assertEqual({k: self.requests[-1][k] for k in ("action", "email", "key", "token")},
                         {"action": "send", "email": "a@example.com", "key": "k" * 64, "token": "t"})

    def test_the_settings_need_no_gmail_password_once_confirmed(self):
        saved = {"gemini_api_key": KEY, "channels": ["@TheStreet"], "email_to": ["a@example.com"], "email_key": "k" * 64}
        cfg, errors = app.merged({"email_to": "a@example.com"}, saved)
        self.assertEqual(errors, {})
        self.assertNotIn("k" * 64, json.dumps(app.public(cfg)))   # the key never reaches the page
        self.assertEqual(app.public(cfg)["email_confirmed"], "a@example.com")
        cfg, errors = app.merged({"email_to": "b@example.com"}, saved)   # a different address must be confirmed again
        self.assertEqual(cfg["email_key"], "")
        self.assertIn("smtp_password", errors)


class Stocks(Folder):
    def test_watchlist_and_holdings_from_the_settings_page(self):
        cfg, errors = app.merged({"gemini_api_key": KEY, "channels": ["@TheStreet"],
                                  "stocks": [{"ticker": " nvda ", "shares": "10"}, {"ticker": "AAPL", "shares": ""}, {"ticker": "brk-b", "shares": "1,500"}]}, {})
        self.assertEqual(errors, {})
        self.assertEqual(cfg["watchlist"], ["NVDA", "AAPL", "BRK-B"])
        self.assertEqual(cfg["holdings"], {"NVDA": 10.0, "BRK-B": 1500.0})
        _, errors = app.merged({"gemini_api_key": KEY, "channels": ["@TheStreet"], "stocks": [{"ticker": "NVDA", "shares": "ten"}]}, {})
        self.assertIn("stocks", errors)
        _, errors = app.merged({"gemini_api_key": KEY, "channels": ["@TheStreet"], "stocks": [{"ticker": "Nvidia Corp", "shares": ""}]}, {})
        self.assertIn("stocks", errors)


class Scoring(unittest.TestCase):
    """How a call is judged, and when the weekly and monthly digests are due."""

    def setUp(self):
        days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
        self.cache = {"^GSPC": {"closes": [[d, 100 + i] for i, d in enumerate(days)]},          # S&P 500: +4%
                      "UP": {"closes": [[d, 50 + 5 * i] for i, d in enumerate(days)]},          # +40%
                      "DOWN": {"closes": [[d, 50 - 5 * i] for i, d in enumerate(days)]}}        # -40%

    def call(self, ticker, view, day="2026-11-01"):
        return {"ticker": ticker, "view": view, "day": day}

    def test_a_call_is_right_when_it_beats_the_sp500_its_way(self):
        import insights
        self.assertTrue(insights.score(self.call("UP", "bullish"), self.cache)["right"])
        self.assertFalse(insights.score(self.call("DOWN", "bullish"), self.cache)["right"])
        self.assertTrue(insights.score(self.call("DOWN", "bearish"), self.cache)["right"])
        s = insights.score(self.call("UP", "bullish"), self.cache)
        self.assertEqual((s["stock_pct"], s["sp500_pct"], s["edge"], s["since"]), (40.0, 4.0, 36.0, "2026-11-02"))

    def test_too_soon_or_neutral_is_not_scored(self):
        import insights
        self.assertIsNone(insights.score(self.call("UP", "bullish", day="2026-11-05"), self.cache))   # 1 trading day since
        self.assertIsNone(insights.score(self.call("UP", "neutral"), self.cache))
        self.assertIsNone(insights.score(self.call("NOPRICE", "bullish"), self.cache))

    def test_weekly_and_monthly_periods(self):
        import period
        from datetime import date
        self.assertEqual(period.bounds("week", date(2026, 11, 7)), (date(2026, 10, 31), date(2026, 11, 7), "2026-11-07"))   # a Saturday
        self.assertEqual(period.bounds("week", date(2026, 11, 11))[2], "2026-11-07")   # the Wednesday after: the same week
        self.assertEqual(period.bounds("month", date(2026, 11, 11)), (date(2026, 10, 1), date(2026, 11, 1), "2026-10"))
        self.assertEqual(period.due({}, {"last_week": "2026-11-07", "last_month": "2026-10"}, date(2026, 11, 11)), [])
        self.assertEqual(period.due({"monthly": False}, {}, date(2026, 11, 14)), ["week"])


class Checkup(Folder):
    """The plain-language check-up of each stock."""

    def setUp(self):
        super().setUp()
        digest.CACHE_DIR.mkdir()
        from datetime import date, datetime, timedelta, timezone
        self.today = date.today()
        n = 0
        for view, ticker, who, count in (("bullish", "NVDA", "Dan Ives", 5), ("bearish", "TSLA", "Mike Wilson", 3), ("bullish", "TSLA", "Tom Lee", 1)):
            for _ in range(count):
                n += 1
                when = datetime.now(timezone.utc) - timedelta(days=n % 10 + 1)
                (digest.CACHE_DIR / f"v{n:010d}.json").write_text(json.dumps({
                    "summary": "s", "speakers": [{"name": who}], "stocks": [{"name": ticker, "ticker": ticker, "view": view, "reason": "r", "analyst": who}],
                    "_video": {"id": f"v{n:010d}", "title": "t", "channel": "c", "published": when.isoformat(), "url": f"https://www.youtube.com/watch?v=v{n:010d}"}}))
        self.patch = mock.patch.object(app.insights, "tipranks_latest", lambda cfg: {"NVDA": {"ticker": "NVDA", "consensus": "Strong Buy", "upside_pct": 20.0, "days_to_earnings": 4}})
        self.patch.start()
        self.cache = mock.patch.object(app.prices, "CACHE", self.tmp / "prices.json")
        self.cache.start()
        rows = [[(self.today - timedelta(days=i)).isoformat(), 100.0] for i in range(30, -1, -1)]
        (self.tmp / "prices.json").write_text(json.dumps({"NVDA": {"closes": rows}, "TSLA": {"closes": rows}, "AAPL": {"closes": rows}, "^GSPC": {"closes": rows}}))

    def tearDown(self):
        self.patch.stop()
        self.cache.stop()
        super().tearDown()

    def test_verdicts_and_reasons(self):
        c = app.insights.checkup({"watchlist": ["NVDA", "TSLA", "AAPL"], "holdings": {"NVDA": 10, "TSLA": 1}}, days=30)
        by = {s["ticker"]: s for s in c["stocks"]}
        self.assertEqual(by["NVDA"]["verdict"], "positive")
        self.assertIn("Strong Buy", " ".join(by["NVDA"]["for"]))
        self.assertTrue(any("Earnings in 4 days" in w for w in by["NVDA"]["watch"]))
        self.assertEqual(by["TSLA"]["verdict"], "cautious")
        self.assertIn("3 of 4 analyst calls", " ".join(by["TSLA"]["against"]))
        self.assertEqual(by["AAPL"]["verdict"], "quiet")
        self.assertEqual([s["ticker"] for s in c["stocks"]][:2], ["TSLA", "NVDA"])   # what you own first, the cautious ones on top
        self.assertTrue(any("NVDA is 91%" in h for h in c["health"]))                # too much in one stock
        self.assertTrue(any("cautious on TSLA" in h for h in c["health"]))

    def test_a_record_is_trusted_only_when_it_beat_the_market_and_was_right_half_the_time(self):
        self.assertTrue(app.insights.good_record({"scored": 4, "edge": 2.0, "hit_pct": 75}))
        self.assertFalse(app.insights.good_record({"scored": 29, "edge": 0.5, "hit_pct": 41}))
        self.assertFalse(app.insights.good_record({"scored": 2, "edge": 5.0, "hit_pct": 100}))


class Import(unittest.TestCase):
    def test_a_google_tracker_exported_as_csv(self):
        import base64
        text = "Investment tracker\n\nSymbol,Stock name,# Shares,Cost per share\nNASDAQ:NVDA,NVIDIA,20,120.5\nAAPL,Apple,\"1,500\",\nTotal,,,\n"
        got = app.import_file({"name": "t.csv", "data": base64.b64encode(text.encode()).decode()})
        self.assertEqual(got["stocks"], [{"ticker": "NVDA", "shares": "20", "cost": "120.5"}, {"ticker": "AAPL", "shares": "1500", "cost": ""}])
        with self.assertRaises(ValueError):
            app.import_file({"name": "x.csv", "data": base64.b64encode(b"a,b\n1,2\n").decode()})


class Paste(unittest.TestCase):
    """Tickers from a page copied on google.com/finance, or a typed list."""

    def test_a_copied_google_finance_page(self):
        page = ("Your watchlists\nWatchlist\nNVDA\nNVIDIA Corp\n$173.73\n0.00%\nRELIANCE\nReliance Industries Ltd\n₹1,412.30\n-0.85%\n"
                "https://www.google.com/finance/quote/TCS:NSE\nBRK.B\nBerkshire Hathaway\nUSD\nS&P 500\nINDEXSP:.INX\nNVDA:NASDAQ\n")
        self.assertEqual(app.find_tickers(page), ["TCS.NS", "NVDA", "RELIANCE.NS", "BRK-B"])

    def test_a_typed_list_but_not_a_sentence(self):
        self.assertEqual(app.find_tickers("msft\nAMZN, GOOGL"), ["MSFT", "AMZN", "GOOGL"])
        self.assertEqual(app.find_tickers("Hello there, nothing here"), [])
