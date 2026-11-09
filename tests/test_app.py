"""Tests for app.py, the Market Digest app: settings checks, secrets never reaching the page, and the local server's guards.
Run from the project folder: python -m unittest -v"""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import app
import digest

KEY = "AIzaSyA1234567890abcdefghijklmnopqrstuv"
GOOD = {"gemini_api_key": KEY, "channels": ["@TheStreet"], "daily_time": "06:45", "schedule_on": True}


class Settings(unittest.TestCase):
    def test_a_good_form_has_no_problems(self):
        cfg, errors = app.merged(GOOD, {})
        self.assertEqual(errors, {})
        self.assertEqual(cfg["gemini_api_key"], KEY)
        self.assertEqual(cfg["daily_time"], "06:45")
        self.assertEqual(cfg["smtp_port"], 465)

    def test_problems_are_named_per_field(self):
        _, errors = app.merged({"gemini_api_key": "short", "channels": ["cnbc"], "email_to": "bob@x", "daily_time": "25:00",
                                "tipranks_api_key": "abc", "watchlist_csv": "docs.google.com/x", "max_videos": "500"}, {})
        self.assertEqual(set(errors), {"gemini_api_key", "channels", "email_to", "smtp_user", "smtp_password", "daily_time",
                                       "tipranks_api_key", "watchlist_csv", "max_videos"})

    def test_channel_links_and_handles_are_accepted(self):
        for ch in ("@TheStreet", "https://www.youtube.com/@CNBCtelevision/videos", "youtube.com/channel/UC" + "a" * 22, "https://m.youtube.com/@x.y"):
            _, errors = app.merged({**GOOD, "channels": [ch]}, {})
            self.assertNotIn("channels", errors, ch)

    def test_a_blank_secret_keeps_the_saved_one_and_clear_removes_it(self):
        saved = {"gemini_api_key": KEY, "smtp_password": "abcdefghijklmnop", "tipranks_api_key": "tr_live_" + "a" * 32,
                 "email_to": ["a@example.com"], "smtp_user": "a@example.com", "channels": ["@x"]}
        cfg, errors = app.merged({"gemini_api_key": "", "smtp_password": "", "tipranks_api_key": "", "tipranks_api_key_clear": True}, saved)
        self.assertEqual(errors, {})
        self.assertEqual(cfg["gemini_api_key"], KEY)
        self.assertEqual(cfg["smtp_password"], "abcdefghijklmnop")
        self.assertEqual(cfg["tipranks_api_key"], "")

    def test_app_password_spaces_are_removed_and_sender_defaults_to_the_recipient(self):
        cfg, errors = app.merged({**GOOD, "email_to": "anil@example.com, b@example.com", "smtp_password": "abcd efgh ijkl mnop"}, {})
        self.assertEqual(errors, {})
        self.assertEqual(cfg["smtp_password"], "abcdefghijklmnop")
        self.assertEqual(cfg["smtp_user"], "anil@example.com")
        self.assertEqual(cfg["email_to"], ["anil@example.com", "b@example.com"])

    def test_the_page_never_sees_a_secret(self):
        cfg = {"gemini_api_key": KEY, "smtp_password": "abcdefghijklmnop", "tipranks_api_key": "tr_live_" + "z" * 32}
        page = json.dumps(app.public(cfg))
        for secret in cfg.values():
            self.assertNotIn(secret, page)
        self.assertEqual(app.public(cfg)["gemini_api_key"], {"saved": True, "hint": "ends in stuv"})
        self.assertEqual(app.public(cfg)["smtp_password"], {"saved": True, "hint": "saved"})

    def test_the_example_placeholder_counts_as_no_key(self):
        self.assertTrue(app.public({"gemini_api_key": "PASTE YOUR GEMINI KEY HERE"})["first_time"])

    def test_next_run(self):
        from datetime import datetime
        self.assertEqual(app.next_run("07:30", datetime(2026, 11, 9, 6, 0)), "today at 07:30")
        self.assertEqual(app.next_run("07:30", datetime(2026, 11, 9, 8, 0)), "tomorrow at 07:30")


class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(digest, k) for k in ("CONFIG", "OUT_DIR", "LAST_RUN", "STATE", "CACHE_DIR", "JSON_DIR")}
        digest.CONFIG, digest.OUT_DIR, digest.LAST_RUN = self.tmp / "cfg.json", self.tmp / "digests", self.tmp / "last_run.json"
        digest.STATE, digest.CACHE_DIR, digest.JSON_DIR = self.tmp / "state.json", self.tmp / "cache", self.tmp / "json"
        self.schedule, app.schedule = app.schedule, lambda on, at: f"Scheduled at {at}."
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        app.Handler.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        app.schedule = self.schedule
        for k, v in self.saved.items():
            setattr(digest, k, v)

    def call(self, path, body=None, host=None, ctype="application/json"):
        port = app.Handler.port
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                     headers={"Host": host or f"127.0.0.1:{port}", "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode()

    def test_save_then_read_back_without_secrets(self):
        code, body = self.call("/api/save", {**GOOD, "email_to": "a@example.com", "smtp_password": "abcdefghijklmnop"})
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)["schedule"], "Scheduled at 06:45.")
        saved = json.loads(digest.CONFIG.read_text())
        self.assertEqual(saved["gemini_api_key"], KEY)
        if os.name != "nt":
            self.assertEqual(digest.CONFIG.stat().st_mode & 0o777, 0o600)
        code, body = self.call("/api/settings")
        self.assertEqual(code, 200)
        self.assertNotIn(KEY, body)
        self.assertNotIn("abcdefghijklmnop", body)

    def test_save_with_problems_changes_nothing(self):
        code, body = self.call("/api/save", {"gemini_api_key": "x", "channels": []})
        self.assertEqual(code, 400)
        self.assertIn("channels", json.loads(body)["fields"])
        self.assertFalse(digest.CONFIG.exists())

    def test_other_sites_are_refused(self):
        self.assertEqual(self.call("/api/settings", host="evil.example:80")[0], 403)          # DNS rebinding
        self.assertEqual(self.call("/api/save", GOOD, ctype="text/plain")[0], 403)            # a form post from another site
        self.assertFalse(digest.CONFIG.exists())

    def test_only_saved_digests_are_served(self):
        digest.OUT_DIR.mkdir()
        (digest.OUT_DIR / "digest-2026-11-09-0731.html").write_text("<h1>today</h1>")
        digest.CONFIG.write_text(json.dumps({"gemini_api_key": KEY}))
        self.assertEqual(self.call("/digests/digest-2026-11-09-0731.html"), (200, "<h1>today</h1>"))
        self.assertEqual(self.call("/digests/..%2Fcfg.json")[0], 404)
        self.assertEqual(self.call("/digests/cfg.json")[0], 404)

    def test_pages(self):
        self.assertIn("<title>Market Digest</title>", self.call("/")[1])
        self.assertIn("<title>Market Digest</title>", self.call("/settings")[1])
        self.assertIn("Digest chat", self.call("/chat")[1])
        self.assertIn("Digest chat", self.call("/?video=abcdefghijk")[1])   # links in saved digests

    def test_status_reads_the_last_run(self):
        digest.LAST_RUN.write_text(json.dumps({"finished_at": "2026-11-09T07:31:00", "ok": False, "message": "No internet."}))
        code, body = self.call("/api/status")
        st = json.loads(body)
        self.assertEqual(code, 200)
        self.assertFalse(st["configured"])
        self.assertEqual(st["last_run"]["message"], "No internet.")


if __name__ == "__main__":
    unittest.main()
