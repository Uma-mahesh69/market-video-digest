"""Tests for google_link.py and the app's Google routes, against a stand-in for Google (sign-in and Sheets).
The stand-in fills GOOGLEFINANCE's columns with made-up quotes, the way Google does a moment after tickers are typed.
Run from the project folder: python -m unittest -v"""
import json
import re
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import app
import digest
import google_link
import prices

QUOTE = {"NVDA": 190.5, "AAPL": 270.0, "INDEXSP:.INX": 6800.0, "MSFT": 500.0, "KRX:005930": 95000.0}


class FakeGoogle(BaseHTTPRequestHandler):
    """Just enough of oauth2.googleapis.com and sheets.googleapis.com."""
    state = None

    def log_message(self, *a):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)

    def authorized(self):
        ok = self.headers.get("Authorization") == f"Bearer {self.state['access']}"
        if not ok:
            self.reply(401, {"error": {"code": 401}})
        return ok

    def do_POST(self):
        st = self.state
        if self.path == "/token":
            form = dict(urllib.parse.parse_qsl(self.body().decode()))
            st["token_calls"].append(form)
            if form["grant_type"] == "authorization_code":
                return self.reply(200, {"access_token": st["access"], "refresh_token": "refresh-1", "expires_in": 3600, "scope": google_link.SCOPE})
            if form.get("refresh_token") != "refresh-1" or st["revoked"]:
                return self.reply(400, {"error": "invalid_grant"})
            return self.reply(200, {"access_token": st["access"], "expires_in": 3600})
        if self.path == "/revoke":
            st["revoked"] = True
            return self.reply(200, {})
        if not self.authorized():
            return
        body = json.loads(self.body() or b"{}")
        if self.path == "/v4/spreadsheets":
            st["sheets"]["S1"] = {"My stocks": {}, "Prices": {}, "About": {}}
            st["created"] += 1
            return self.reply(200, {"spreadsheetId": "S1", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/S1/edit",
                                    "sheets": [{"properties": {"title": t, "sheetId": i}} for i, t in enumerate(("My stocks", "Prices", "About"))]})
        m = re.match(r"/v4/spreadsheets/(\w+)/values:batchUpdate", self.path)
        if m:
            for d in body["data"]:
                self.put(st["sheets"][m.group(1)], d["range"], d["values"])
            return self.reply(200, {})
        if re.match(r"/v4/spreadsheets/\w+:batchUpdate", self.path):
            st["formatted"] = True
            return self.reply(200, {})
        self.reply(404, {})

    def do_GET(self):
        if not self.authorized():
            return
        m = re.match(r"/v4/spreadsheets/(\w+)/values:batchGet\?(.*)", self.path)
        if not m or m.group(1) not in self.state["sheets"]:
            return self.reply(404, {})
        tabs = self.state["sheets"][m.group(1)]
        out = []
        for r in [v for k, v in urllib.parse.parse_qsl(m.group(2)) if k == "ranges"]:
            out.append({"range": r, "values": self.get(tabs, r)})
        self.reply(200, {"valueRanges": out})

    # a sheet is {tab: {(row, col): value}}, both from 1
    @staticmethod
    def a1(ref):
        tab, cells = ref.rsplit("!", 1)
        start = cells.split(":")[0]
        col = 0
        for ch in re.match(r"[A-Z]+", start).group(0):
            col = col * 26 + ord(ch) - 64
        return tab.strip("'"), int(re.search(r"\d+", start).group(0)), col

    def put(self, tabs, ref, values):
        tab, r0, c0 = self.a1(ref)
        for i, row in enumerate(values):
            for j, v in enumerate(row):
                tabs[tab][(r0 + i, c0 + j)] = v

    def get(self, tabs, ref):
        tab, r0, c0 = self.a1(ref)
        cells, rows = tabs[tab], []
        last = max([r for r, _ in cells] or [0])
        for r in range(r0, last + 1):
            if tab == "My stocks":
                t = cells.get((r, 1), "")
                q = QUOTE.get(str(t).upper(), QUOTE.get("NASDAQ:" + str(t).upper().split(":")[-1])) if t else None
                shares, cost = cells.get((r, 2), ""), cells.get((r, 3), "")
                row = [t, shares, cost] + ([f"{t} Inc", q, 1.5, (float(shares) * q) if shares not in ("", None) else "",
                                            round((q / float(cost) - 1) * 100, 2) if cost not in ("", None) else "", q * 1.2, q * 0.6, 30, "USD"]
                                           if q else [""] * 9)
            else:
                t, g = cells.get((r, 1), ""), cells.get((r, 2), "")
                q = QUOTE.get(g) if g else None
                row = [t, g] + ([f"{t} name", q, -0.5, q * 0.99, q * 1.1, q * 0.7, 25, "USD"] if q else [""] * 8)
            rows.append([v for v in row])
        while rows and not any(str(v) for v in rows[-1]):
            rows.pop()
        return [row[c0 - 1:] for row in rows]


class Google(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        FakeGoogle.state = {"access": "access-1", "revoked": False, "sheets": {}, "created": 0, "token_calls": []}
        self.fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeGoogle)
        threading.Thread(target=self.fake.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{self.fake.server_address[1]}"
        self.patches = [mock.patch.object(google_link, "TOKEN_URL", base + "/token"), mock.patch.object(google_link, "REVOKE_URL", base + "/revoke"),
                        mock.patch.object(google_link, "SHEETS", base + "/v4/spreadsheets"),
                        mock.patch.object(google_link, "client", lambda: {"id": "x.apps.googleusercontent.com", "secret": "s"}),
                        mock.patch.object(prices, "CACHE", self.tmp / "prices.json"), mock.patch.object(google_link.time, "sleep", lambda s: None)]
        for p in self.patches:
            p.start()
        google_link._access.update(token=None, until=0, refresh=None)
        self.saved = {k: getattr(digest, k) for k in ("CONFIG", "CACHE_DIR", "STATE")}
        digest.CONFIG, digest.CACHE_DIR, digest.STATE = self.tmp / "cfg.json", self.tmp / "cache", self.tmp / "state.json"
        digest.CONFIG.write_text(json.dumps({"gemini_api_key": "AIzaSyA1234567890abcdefghijklmnopqrstuv", "channels": ["@x"],
                                             "watchlist": ["NVDA", "AAPL"], "holdings": {"NVDA": 10}, "costs": {"NVDA": 100}}))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for k, v in self.saved.items():
            setattr(digest, k, v)
        self.fake.shutdown()
        self.fake.server_close()

    def sign_in(self):
        url = google_link.start("http://127.0.0.1:8765/oauth/callback")
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual((q["scope"], q["code_challenge_method"], q["access_type"]), (google_link.SCOPE, "S256", "offline"))
        return google_link.finish(q["state"], "the-code")

    def test_symbols_both_ways(self):
        for ours, theirs in (("NVDA", "NVDA"), ("005930.KS", "KRX:005930"), ("BRK-B", "BRK.B"), ("^GSPC", "INDEXSP:.INX"), ("VOD.L", "LON:VOD")):
            self.assertEqual(google_link.google_symbol(ours), theirs)
            self.assertEqual(google_link.our_symbol(theirs), ours)
        self.assertEqual(google_link.our_symbol("NASDAQ:NVDA"), "NVDA")

    def test_sign_in_uses_pkce_and_keeps_a_lasting_token(self):
        token = self.sign_in()
        self.assertEqual(token, "refresh-1")
        exchange = FakeGoogle.state["token_calls"][0]
        self.assertTrue(exchange["code_verifier"])
        with self.assertRaises(google_link.GoogleError):   # a sign-in can be finished once only
            google_link.finish("unknown-state", "code")

    def test_create_sync_and_write_back(self):
        token = self.sign_in()
        sheet = google_link.create_sheet(token, app.stock_rows(json.loads(digest.CONFIG.read_text())))
        self.assertEqual(sheet["id"], "S1")
        tabs = FakeGoogle.state["sheets"]["S1"]
        self.assertEqual(tabs["My stocks"][(2, 1)], "NVDA")
        self.assertTrue(str(tabs["My stocks"][(2, 4)]).startswith("=MAP("))   # Google Finance formulas, once, in row 2
        self.assertTrue(FakeGoogle.state["formatted"])
        cfg = {"google_token": token, "google_sheet": sheet}
        got = google_link.sync(cfg, extra_tickers=["MSFT"], log=lambda m: None)
        nvda = next(s for s in got["stocks"] if s["ticker"] == "NVDA")
        self.assertEqual((nvda["shares"], nvda["cost"], nvda["price"], nvda["value"]), (10.0, 100.0, 190.5, 1905.0))
        self.assertEqual(got["quotes"]["^GSPC"]["price"], 6800.0)   # the S&P 500 always comes along
        self.assertEqual(got["quotes"]["MSFT"]["price"], 500.0)
        google_link.put_stocks(cfg, [{"ticker": "005930.KS", "shares": 3}])   # edits made in the app
        self.assertEqual((tabs["My stocks"][(2, 1)], tabs["My stocks"][(3, 1)]), ("KRX:005930", ""))

    def test_a_revoked_sign_in_asks_to_connect_again(self):
        token = self.sign_in()
        google_link.revoke(token)
        with self.assertRaises(google_link.GoogleError) as caught:
            google_link.read(token, "S1", ["'My stocks'!A2:C"])
        self.assertTrue(caught.exception.reconnect)

    def test_the_daily_run_updates_settings_and_prices_from_the_sheet(self):
        token = self.sign_in()
        sheet = google_link.create_sheet(token, [{"ticker": "NVDA", "shares": 5, "cost": 150}, {"ticker": "AAPL"}])
        cfg = json.loads(digest.CONFIG.read_text())
        cfg.update(google_token=token, google_sheet=sheet)
        digest.CONFIG.write_text(json.dumps(cfg))
        with mock.patch.object(digest, "log", lambda m: None):
            self.assertTrue(digest.sync_google(cfg, extra=["MSFT"]))
        saved = json.loads(digest.CONFIG.read_text())
        self.assertEqual((saved["watchlist"], saved["holdings"], saved["costs"]), (["NVDA", "AAPL"], {"NVDA": 5.0}, {"NVDA": 150.0}))
        q = prices.quote("NVDA")
        self.assertEqual((q["price"], q["source"], q["pe"]), (190.5, "Google Finance", 30))
        self.assertEqual(len(prices.series("NVDA")), 1)   # today's price starts the stock's own history

    def test_the_page_never_sees_the_sign_in(self):
        cfg = {"google_token": "refresh-1", "google_sheet": {"id": "S1", "url": "https://docs.google.com/x"}}
        page = json.dumps(app.public(cfg))
        self.assertNotIn("refresh-1", page)
        self.assertTrue(app.public(cfg)["google"]["connected"])


if __name__ == "__main__":
    unittest.main()
