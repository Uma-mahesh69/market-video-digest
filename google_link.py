"""Your Google account, on your own computer: a "My portfolio" Google Sheet priced by Google Finance.

"Connect Google" in Market Digest signs you in to Google in your browser. Market Digest then creates one spreadsheet
in your Drive, "Market Digest - My portfolio", and from then on keeps it and the app in step:
  - "My stocks": the stocks you own or watch. You type the ticker, the shares you own (blank if you only watch it) and
    what you paid per share (optional). Google Finance fills in the name, price, today's change, value, gain and more.
    Edit it in Google Sheets, on your phone too, or in Market Digest: both stay the same.
  - "Prices": kept by Market Digest: Google Finance's quotes for the S&P 500 and the stocks the analysts talk about.

What Market Digest may do in your Google account: only see and change the files it created (Google's "drive.file"
permission). It cannot see any other file. The sign-in is kept in digest_config.json on this computer and is never
shown on any page; "Disconnect" removes it, and Google Account > Security > Third-party access can revoke it too.
There is no Market Digest server: your computer talks to Google directly.

Google does not let apps read GOOGLEFINANCE price history through its API, so the app records each day's prices itself
(prices.py), and fills in older history from Yahoo Finance or Stooq where it can.
Standard library only.
"""
import base64
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPE = "https://www.googleapis.com/auth/drive.file"   # only the files this app creates
TITLE = "Market Digest - My portfolio"
STOCKS, PRICES, ABOUT = "My stocks", "Prices", "About"
STOCK_HEAD = ["Ticker", "Shares you own", "Price you paid (per share)", "Name", "Price", "Today %", "Value", "Gain %",
              "52-week high", "52-week low", "P/E", "Currency"]
PRICE_HEAD = ["Ticker", "Google Finance symbol", "Name", "Price", "Today %", "Previous close", "52-week high", "52-week low",
              "P/E", "Currency"]
SP500 = ("^GSPC", "INDEXSP:.INX")
EXCHANGE = {".KS": "KRX:", ".KQ": "KOSDAQ:", ".PA": "EPA:", ".T": "TYO:", ".HK": "HKG:", ".L": "LON:", ".TO": "TSE:",
            ".DE": "ETR:", ".NS": "NSE:", ".BO": "BOM:", ".AX": "ASX:", ".SW": "SWX:", ".AS": "AMS:", ".MI": "BIT:"}
MAX_ROWS = 500


class GoogleError(RuntimeError):
    """A problem with Google, in a sentence for the person. .reconnect means the sign-in must be done again."""

    def __init__(self, message, reconnect=False):
        super().__init__(message)
        self.reconnect = reconnect


# ---------------------------------------------------------------- tickers: Google Finance names and ours

def google_symbol(ticker):
    """GOOGLEFINANCE's name for a ticker written the Yahoo way: 005930.KS -> KRX:005930, BRK-B -> BRK.B, ^GSPC -> INDEXSP:.INX."""
    t = str(ticker or "").strip().upper()
    if t == SP500[0]:
        return SP500[1]
    if ":" in t:
        return t
    for suffix, prefix in EXCHANGE.items():
        if t.endswith(suffix):
            return prefix + t[: -len(suffix)]
    return t.replace("-", ".")


def our_symbol(text):
    """Our name for what someone typed in the sheet: NASDAQ:NVDA -> NVDA, KRX:005930 -> 005930.KS, BRK.B -> BRK-B."""
    t = re.sub(r"\s+", "", str(text or "")).upper()
    if not t:
        return ""
    if t == SP500[1]:
        return SP500[0]
    if ":" in t:
        exch, sym = t.split(":", 1)
        for suffix, prefix in EXCHANGE.items():
            if prefix == exch + ":":
                return sym + suffix
        return sym.replace(".", "-")
    return t if re.search(r"\.[A-Z]{1,2}$", t) and any(t.endswith(s) for s in EXCHANGE) else t.replace(".", "-")


# ---------------------------------------------------------------- the client (from service.json, shipped with the app)

def client():
    """{"id", "secret"} of the app's Google sign-in, or None when this version has none. For a desktop app Google does
    not treat the secret as secret: the sign-in is protected by the code exchange below (PKCE) and the user's consent."""
    try:
        doc = json.loads((HERE / "service.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cid = str(doc.get("google_client_id") or "").strip()
    return {"id": cid, "secret": str(doc.get("google_client_secret") or "").strip()} if cid.endswith(".apps.googleusercontent.com") else None


def available():
    return client() is not None


# ---------------------------------------------------------------- signing in (OAuth for installed apps, with PKCE)

_pending = {}   # state -> (verifier, redirect_uri, when)


def start(redirect_uri):
    """The Google sign-in address to send the browser to."""
    c = client()
    if not c:
        raise GoogleError("Google sign-in is not set up in this version of Market Digest.")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    _pending.clear()
    _pending[state] = (verifier, redirect_uri, time.time())
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["id"], "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"})


def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as err:
        try:
            body = json.loads(err.read().decode("utf-8") or "{}")
        except ValueError:
            body = {}
        if body.get("error") == "invalid_grant":
            raise GoogleError("Google no longer accepts this sign-in (it was revoked or expired). Connect Google again.", reconnect=True)
        raise GoogleError(f"Google refused the sign-in ({body.get('error_description') or body.get('error') or err.code}).")
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise GoogleError(f"Could not reach Google ({err.__class__.__name__}). Check the internet connection.")


def finish(state, code):
    """Exchange the code Google sent back for a lasting sign-in. Returns the refresh token (to keep in the settings)."""
    pending = _pending.pop(state, None)
    if not pending or time.time() - pending[2] > 900:
        raise GoogleError("That sign-in had expired or was not started here. Click Connect Google again.")
    verifier, redirect_uri, _ = pending
    c = client()
    tokens = post_form(TOKEN_URL, {"code": code, "client_id": c["id"], "client_secret": c["secret"], "redirect_uri": redirect_uri,
                                   "grant_type": "authorization_code", "code_verifier": verifier})
    if not tokens.get("refresh_token"):
        raise GoogleError("Google did not give a lasting sign-in. Click Connect Google again.")
    if SCOPE not in str(tokens.get("scope", SCOPE)):
        raise GoogleError("Market Digest needs the permission to keep its own spreadsheet. Connect again and leave that box ticked.")
    _access.update(token=tokens.get("access_token"), until=time.time() + int(tokens.get("expires_in", 3000)) - 60,
                   refresh=tokens["refresh_token"])
    return tokens["refresh_token"]


_access = {"token": None, "until": 0, "refresh": None}


def access_token(refresh_token):
    if _access["token"] and _access["refresh"] == refresh_token and time.time() < _access["until"]:
        return _access["token"]
    c = client()
    if not c:
        raise GoogleError("Google sign-in is not set up in this version of Market Digest.")
    tokens = post_form(TOKEN_URL, {"client_id": c["id"], "client_secret": c["secret"], "refresh_token": refresh_token,
                                   "grant_type": "refresh_token"})
    _access.update(token=tokens["access_token"], until=time.time() + int(tokens.get("expires_in", 3000)) - 60, refresh=refresh_token)
    return _access["token"]


def revoke(refresh_token):
    try:
        post_form(REVOKE_URL, {"token": refresh_token})
    except GoogleError:
        pass
    _access.update(token=None, until=0, refresh=None)


# ---------------------------------------------------------------- the Sheets API

def api(refresh_token, method, url, body=None, retry=True):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {access_token(refresh_token)}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as err:
        if err.code == 401 and retry:
            _access.update(token=None, until=0)
            return api(refresh_token, method, url, body, retry=False)
        if err.code in (403, 404):
            raise GoogleError("Your portfolio spreadsheet could not be opened (it may have been deleted).", reconnect=False) from err
        if err.code == 429 or err.code >= 500:
            raise GoogleError("Google Sheets is busy. Market Digest tries again later.")
        raise GoogleError(f"Google Sheets said no ({err.code}).")
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise GoogleError(f"Could not reach Google Sheets ({err.__class__.__name__}). Check the internet connection.")


def stock_formulas():
    """Row 2 of "My stocks": one formula per column for every row, so new rows fill in by themselves."""
    g = lambda attr: f'MAP(A2:A{MAX_ROWS},LAMBDA(t,IF(t="","",IFERROR(GOOGLEFINANCE(t,"{attr}"),""))))'
    return [f"={g('name')}", f"={g('price')}", f"={g('changepct')}",
            f'=MAP(B2:B{MAX_ROWS},E2:E{MAX_ROWS},LAMBDA(s,p,IF(OR(s="",p=""),"",s*p)))',
            f'=MAP(C2:C{MAX_ROWS},E2:E{MAX_ROWS},LAMBDA(c,p,IF(OR(c="",c=0,p=""),"",ROUND((p/c-1)*100,2))))',
            f"={g('high52')}", f"={g('low52')}", f"={g('pe')}", f"={g('currency')}"]


def price_formulas():
    g = lambda attr: f'MAP(B2:B{MAX_ROWS},LAMBDA(t,IF(t="","",IFERROR(GOOGLEFINANCE(t,"{attr}"),""))))'
    return [f"={g(a)}" for a in ("name", "price", "changepct", "closeyest", "high52", "low52", "pe", "currency")]


ABOUT_TEXT = [
    ["Market Digest - My portfolio"],
    [""],
    ["Type your stocks in the \"My stocks\" tab: the ticker (like NVDA, or NASDAQ:NVDA), the shares you own (leave it empty if you"],
    ["only watch the stock) and, if you like, the price you paid per share. Google Finance fills in the rest."],
    ["Market Digest reads this tab each day and checks each stock against what the analysts are saying."],
    [""],
    ["The \"Prices\" tab is kept by Market Digest. Please do not edit it."],
    [""],
    ["Only Market Digest on your own computer reads this file. It is not shared with anyone unless you share it."],
    ["Prices come from Google Finance and can be delayed by up to 20 minutes. This is information, not investment advice."],
]


def create_sheet(refresh_token, stocks=()):
    """Create the portfolio spreadsheet in the person's Drive and fill it in. Returns {"id", "url"}."""
    doc = api(refresh_token, "POST", SHEETS, {
        "properties": {"title": TITLE, "autoRecalc": "HOUR"},
        "sheets": [{"properties": {"title": STOCKS, "gridProperties": {"frozenRowCount": 1, "rowCount": MAX_ROWS, "columnCount": len(STOCK_HEAD)}}},
                   {"properties": {"title": PRICES, "gridProperties": {"frozenRowCount": 1, "rowCount": MAX_ROWS, "columnCount": len(PRICE_HEAD)}}},
                   {"properties": {"title": ABOUT, "gridProperties": {"rowCount": 30, "columnCount": 2}}}]})
    sid, url = doc["spreadsheetId"], doc.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{doc['spreadsheetId']}/edit"
    ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in doc.get("sheets", [])}
    rows = [[google_symbol(s["ticker"]), s.get("shares") or "", s.get("cost") or ""] for s in stocks]
    write(refresh_token, sid, [
        {"range": f"'{STOCKS}'!A1:L1", "values": [STOCK_HEAD]},
        {"range": f"'{STOCKS}'!D2:L2", "values": [stock_formulas()]},
        {"range": f"'{PRICES}'!A1:J1", "values": [PRICE_HEAD]},
        {"range": f"'{PRICES}'!C2:J2", "values": [price_formulas()]},
        {"range": f"'{ABOUT}'!A1:A{len(ABOUT_TEXT)}", "values": ABOUT_TEXT},
    ] + ([{"range": f"'{STOCKS}'!A2:C{len(rows) + 1}", "values": rows}] if rows else []))
    blue = {"red": 0.91, "green": 0.93, "blue": 0.98}
    fmt = []
    for title, width in ((STOCKS, len(STOCK_HEAD)), (PRICES, len(PRICE_HEAD))):
        fmt += [{"repeatCell": {"range": {"sheetId": ids[title], "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": width},
                                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": blue, "wrapStrategy": "WRAP"}},
                                "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy)"}},
                {"updateDimensionProperties": {"range": {"sheetId": ids[title], "dimension": "COLUMNS", "startIndex": 0, "endIndex": width},
                                               "properties": {"pixelSize": 120}, "fields": "pixelSize"}}]
    fmt.append({"repeatCell": {"range": {"sheetId": ids[STOCKS], "startRowIndex": 1, "endRowIndex": MAX_ROWS, "startColumnIndex": 0, "endColumnIndex": 3},
                               "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 0.98, "blue": 0.9}}},
                               "fields": "userEnteredFormat.backgroundColor"}})   # the columns you type in
    fmt.append({"updateDimensionProperties": {"range": {"sheetId": ids[ABOUT], "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                                              "properties": {"pixelSize": 900}, "fields": "pixelSize"}})
    api(refresh_token, "POST", f"{SHEETS}/{sid}:batchUpdate", {"requests": fmt})
    return {"id": sid, "url": url}


def write(refresh_token, sid, data):
    api(refresh_token, "POST", f"{SHEETS}/{sid}/values:batchUpdate", {"valueInputOption": "USER_ENTERED", "data": data})


def read(refresh_token, sid, ranges):
    q = urllib.parse.urlencode([("ranges", r) for r in ranges] + [("valueRenderOption", "UNFORMATTED_VALUE")])
    out = api(refresh_token, "GET", f"{SHEETS}/{sid}/values:batchGet?{q}")
    return [vr.get("values", []) for vr in out.get("valueRanges", [])]


def number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def cell(row, i):
    return row[i] if i < len(row) else ""


def read_stocks(rows):
    """[{"ticker", "symbol", "shares", "cost", quote fields...}] from the "My stocks" tab's rows (header left out)."""
    out, seen = [], set()
    for r in rows:
        typed = str(cell(r, 0)).strip()
        t = our_symbol(typed)
        if not t or t in seen:
            continue
        seen.add(t)
        out.append({"ticker": t, "symbol": typed, "shares": number(cell(r, 1)), "cost": number(cell(r, 2)),
                    "name": str(cell(r, 3) or ""), "price": number(cell(r, 4)), "change_pct_day": number(cell(r, 5)),
                    "value": number(cell(r, 6)), "gain_pct": number(cell(r, 7)), "high_52w": number(cell(r, 8)),
                    "low_52w": number(cell(r, 9)), "pe": number(cell(r, 10)), "currency": str(cell(r, 11) or "")})
    return out


def read_prices(rows):
    out = {}
    for r in rows:
        t = str(cell(r, 0)).strip()
        if t:
            out[t] = {"name": str(cell(r, 2) or ""), "price": number(cell(r, 3)), "change_pct_day": number(cell(r, 4)),
                      "close_prev": number(cell(r, 5)), "high_52w": number(cell(r, 6)), "low_52w": number(cell(r, 7)),
                      "pe": number(cell(r, 8)), "currency": str(cell(r, 9) or "")}
    return out


def loading(rows):
    return any(isinstance(v, str) and v.lower().startswith("loading") for r in rows for v in r)


def sync(cfg, extra_tickers=(), wait=True, log=print):
    """Read the person's stocks from their sheet, refresh the Prices tab, and return
    {"stocks": [...], "quotes": {ticker: {...}}, "url"}. Raises GoogleError. cfg needs google_token and google_sheet."""
    token, sid = cfg["google_token"], cfg["google_sheet"]["id"]
    stock_rows = read(token, sid, [f"'{STOCKS}'!A2:L{MAX_ROWS}"])[0]
    stocks = read_stocks(stock_rows)
    wanted = list(dict.fromkeys([SP500[0], *(s["ticker"] for s in stocks), *[t for t in extra_tickers if t]]))[: MAX_ROWS - 1]
    listed = [[t, google_symbol(t)] for t in wanted]
    write(token, sid, [{"range": f"'{PRICES}'!A2:B{MAX_ROWS}", "values": listed + [["", ""]] * (MAX_ROWS - 1 - len(listed))}])
    for attempt in range(6 if wait else 1):   # Google Finance fills new rows in a few seconds
        stock_rows, price_rows = read(token, sid, [f"'{STOCKS}'!A2:L{MAX_ROWS}", f"'{PRICES}'!A2:J{MAX_ROWS}"])
        if not (loading(stock_rows) or loading(price_rows)):
            break
        time.sleep(3)
    stocks = read_stocks(stock_rows)
    quotes = read_prices(price_rows)
    for s in stocks:   # the stocks tab has the freshest view of your own stocks
        q = quotes.setdefault(s["ticker"], {})
        for k in ("name", "price", "change_pct_day", "high_52w", "low_52w", "pe", "currency"):
            if s.get(k) not in (None, ""):
                q[k] = s[k]
    priced = sum(1 for q in quotes.values() if q.get("price") is not None)
    log(f"Google Finance: {len(stocks)} of your stocks, {priced} prices read")
    return {"stocks": stocks, "quotes": quotes, "url": cfg["google_sheet"].get("url"), "synced": datetime.now().isoformat(timespec="minutes")}


def put_stocks(cfg, stocks):
    """Write the stocks typed in Market Digest to the sheet's "My stocks" tab (ticker, shares, price paid)."""
    rows = [[google_symbol(s["ticker"]), "" if not s.get("shares") else s["shares"], "" if not s.get("cost") else s["cost"]] for s in stocks]
    rows += [["", "", ""]] * max(0, 60 - len(rows))   # clears rows that were removed
    write(cfg["google_token"], cfg["google_sheet"]["id"], [{"range": f"'{STOCKS}'!A2:C{len(rows) + 1}", "values": rows}])
