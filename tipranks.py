"""Wall Street's view of the stocks, from TipRanks, once a day and inside the free tier.

TipRanks runs an MCP server (https://mcp.tipranks.com/mcp/). Its free tier allows 50 tool calls a month and 10 a
minute, so the digest makes ONE call per day: get_assets_data for every stock it cares about at once (the watchlist
and the stocks called most in today's videos). The answer is saved as tipranks_YYYY-MM-DD.json next to the digest's
other daily files, where the Econova dashboard reads it. A monthly budget (tipranks_monthly_limit, default 40) keeps a
margin for --tipranks-check; past it, the day is skipped and logged, never an error.

Set it up: get a free API key at https://mcp.tipranks.com/ and put it in digest_config.json as tipranks_api_key.
Then run `python digest.py --tipranks-check` (uses 1 of the month's calls) and look at what it prints.

Python standard library only. The key is sent in the Authorization header and never logged.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://mcp.tipranks.com/mcp/"
TOOL = "get_assets_data"
MONTHLY_LIMIT = 40          # of the free tier's 50, leaving room for checks
MAX_TICKERS = 30
SCHEMA_VERSION = "1.0"
NON_US = re.compile(r"\.(KS|KQ|PA|T|HK|L|TO|DE|AS|SW|MI)$")   # TipRanks names these differently; left out for now


class TipRanksError(RuntimeError):
    pass


class Client:
    """The smallest MCP client over Streamable HTTP: JSON-RPC posts, answered as JSON or as server-sent events."""

    def __init__(self, key, url=URL, timeout=60):
        self.key, self.url, self.timeout, self.session, self.ids = key, url, timeout, None, 0

    def _post(self, method, params=None, notify=False):
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            self.ids += 1
            body["id"] = self.ids
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": f"Bearer {self.key}", "User-Agent": "market-video-digest"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.session = r.headers.get("Mcp-Session-Id") or self.session
                text = r.read().decode("utf-8", "replace")
                kind = r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:300]
            if err.code in (401, 403):
                raise TipRanksError(f"TipRanks refused the API key (HTTP {err.code}). Check tipranks_api_key. {detail}") from None
            if err.code == 429:
                raise TipRanksError(f"TipRanks rate limit reached (HTTP 429): {detail}") from None
            raise TipRanksError(f"TipRanks answered HTTP {err.code}: {detail}") from None
        if notify:
            return None
        return self._answer(text, kind)

    @staticmethod
    def _answer(text, kind=""):
        """The JSON-RPC result from a JSON body or from the last `data:` event of an event stream."""
        if "event-stream" in kind or text.lstrip().startswith(("event:", "data:")):
            events = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            msgs = [json.loads(e) for e in events if e.startswith("{")]
            if not msgs:
                raise TipRanksError("TipRanks sent an empty event stream")
            msg = next((m for m in reversed(msgs) if "result" in m or "error" in m), msgs[-1])
        else:
            msg = json.loads(text)
        if "error" in msg:
            raise TipRanksError(f"TipRanks error: {msg['error'].get('message', msg['error'])}")
        return msg.get("result")

    def start(self):
        self._post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "market-video-digest", "version": "1.0"}})
        self._post("notifications/initialized", notify=True)

    def tools(self):
        return (self._post("tools/list") or {}).get("tools", [])

    def call(self, name, arguments):
        result = self._post("tools/call", {"name": name, "arguments": arguments}) or {}
        if result.get("isError"):
            raise TipRanksError("TipRanks tool error: " + content_text(result)[:300])
        return result


def content_text(result):
    return "\n".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))


def ticker_argument(tool):
    """(name, is_list) of the tool's argument that takes the tickers, from its input schema."""
    props = (tool or {}).get("inputSchema", {}).get("properties", {})
    for name, spec in props.items():
        if re.search(r"ticker|symbol", name, re.I):
            return name, spec.get("type") == "array"
    return "tickers", False


def payload(result):
    """The tool's answer as data: structuredContent, else the text content parsed as JSON, else the text."""
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = content_text(result)
    try:
        return json.loads(text)
    except ValueError:
        return text


# ---------------------------------------------------------------- reading the answer

def _num(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return x
    if isinstance(x, str):
        m = re.fullmatch(r"\s*\$?([-+]?\d+(?:\.\d+)?)\s*%?\s*", x.replace(",", ""))
        return float(m.group(1)) if m else None
    return None


def _flat(d, prefix=""):
    """Every leaf of a nested dict as {lowercased key path without separators: value}."""
    out = {}
    for k, v in d.items():
        key = prefix + re.sub(r"[^a-z0-9]", "", str(k).lower())
        if isinstance(v, dict):
            out.update(_flat(v, key))
        else:
            out[key] = v
    return out


def _pick(flat, *patterns, number=True):
    for pat in patterns:
        for k, v in flat.items():
            if re.search(pat, k) and v not in (None, ""):
                if number:
                    n = _num(v)
                    if n is not None:
                        return n
                elif isinstance(v, str):
                    return v.strip()
    return None


def _records(data):
    """The per-stock records in an answer, whatever it wraps them in: dicts that name a ticker or symbol."""
    if isinstance(data, dict):
        named = {k: v for k, v in data.items() if isinstance(v, dict)}
        if data.get("ticker") or data.get("symbol"):
            return [data]
        for v in data.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return [r for x in v for r in _records(x)]
        if named and all(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", k) for k in named):   # {"AAPL": {...}, ...}
            return [dict(v, ticker=k) for k, v in named.items()]
        return [r for v in named.values() for r in _records(v)]
    if isinstance(data, list):
        return [r for x in data for r in _records(x)]
    return []


def rows(data):
    """One row per stock with the fields the dashboard shows. Fields TipRanks does not send stay None."""
    out = []
    for rec in _records(data):
        flat = _flat(rec)
        ticker = str(rec.get("ticker") or rec.get("symbol") or "").upper()
        if not ticker:
            continue
        out.append({
            "ticker": ticker,
            "consensus": _pick(flat, r"consensus(rating|text|label)?$", r"analystconsensus", r"^rating$", number=False),
            "analysts": _pick(flat, r"(numberof|num|total)analysts", r"analystscount", r"analystcount"),
            "buy": _pick(flat, r"(^|consensus|ratings?)buy(s|count)?$"),
            "hold": _pick(flat, r"(^|consensus|ratings?)hold(s|count)?$"),
            "sell": _pick(flat, r"(^|consensus|ratings?)sell(s|count)?$"),
            "price_target": _pick(flat, r"(average|avg|mean|consensus)?pricetarget$", r"pricetarget(average|avg|mean|value)$", r"^pt$"),
            "upside_pct": _pick(flat, r"upside(percent|pct)?$", r"pricetargetupside"),
            "smart_score": _pick(flat, r"smartscore$", r"smartscore(value|score)?$"),
            "price": _pick(flat, r"^(last|current)?price$", r"pricelast"),
        })
    return out


# ---------------------------------------------------------------- the daily snapshot

def file_name(day):
    return f"tipranks_{day:%Y-%m-%d}.json"


def usable(tickers):
    return [t for t in dict.fromkeys(t.upper() for t in tickers if t) if not NON_US.search(t)][:MAX_TICKERS]


def budget(state, cfg, day):
    """(may call now, why not). One call a day, and no more than tipranks_monthly_limit a month."""
    use = state.setdefault("tipranks", {})
    month = f"{day:%Y-%m}"
    if use.get("month") != month:
        use.update(month=month, calls=0)
    limit = int(cfg.get("tipranks_monthly_limit") or MONTHLY_LIMIT)
    if use.get("last_day") == f"{day:%Y-%m-%d}":
        return False, "already fetched today"
    if use.get("calls", 0) >= limit:
        return False, f"this month's {limit} TipRanks calls are used"
    return True, ""


def spend(state, day):
    use = state.setdefault("tipranks", {})
    use["calls"] = use.get("calls", 0) + 1
    use["last_day"] = f"{day:%Y-%m-%d}"


def snapshot(cfg, state, day, tickers, folder, log, client=None):
    """Fetch and save the day's TipRanks file. Returns its path, or None. Never raises: TipRanks is extra."""
    if not cfg.get("tipranks_api_key"):
        return None
    tickers = usable(tickers)
    ok, why = budget(state, cfg, day)
    if not ok or not tickers:
        log(f"TipRanks: skipped ({why or 'no US tickers to look up'})")
        return None
    try:
        tr = client or Client(cfg["tipranks_api_key"])
        tr.start()
        tool = next((t for t in tr.tools() if t.get("name") == TOOL), None)
        if tool is None:
            raise TipRanksError(f"TipRanks has no {TOOL} tool any more")
        arg, is_list = ticker_argument(tool)
        spend(state, day)   # counted before the call: a call that fails still uses the month's budget
        data = payload(tr.call(TOOL, {arg: tickers if is_list else ",".join(tickers)}))
        found = rows(data)
        doc = {"schema_version": SCHEMA_VERSION, "date": f"{day:%Y-%m-%d}", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "source": "TipRanks MCP (free tier), " + TOOL, "tickers": tickers, "rows": found, "raw": data}
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / file_name(day)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        log(f"Saved {path} ({len(found)} of {len(tickers)} stocks; {state['tipranks']['calls']} TipRanks calls this month)")
        return path
    except Exception as err:
        log(f"TipRanks: not saved: {err}")
        return None


def check(cfg, state, log=print):
    """Show what TipRanks offers and what one stock looks like. Uses 1 of the month's calls. True if it works."""
    if not cfg.get("tipranks_api_key"):
        print("TipRanks: not set up (no tipranks_api_key in digest_config.json)")
        return True
    try:
        tr = Client(cfg["tipranks_api_key"])
        tr.start()
        tools = tr.tools()
        print(f"TipRanks: connected, {len(tools)} tools")
        tool = next((t for t in tools if t.get("name") == TOOL), None)
        if tool is None:
            print(f"  FAILED: no {TOOL} tool. Tools: {', '.join(t.get('name', '?') for t in tools[:40])}")
            return False
        arg, is_list = ticker_argument(tool)
        print(f"  {TOOL} takes the tickers in '{arg}' ({'a list' if is_list else 'comma-separated text'})")
        print("  its inputs: " + json.dumps(tool.get("inputSchema", {}).get("properties", {}))[:600])
        spend(state, datetime.now())
        data = payload(tr.call(TOOL, {arg: ["AAPL"] if is_list else "AAPL"}))
        print(f"  AAPL as the dashboard will read it: {json.dumps(rows(data)[:1])}")
        print("  the raw answer (first 1,500 characters): " + json.dumps(data, ensure_ascii=False)[:1500])
        print(f"  {state['tipranks']['calls']} TipRanks calls used this month")
        return True
    except Exception as err:
        print(f"TipRanks: FAILED: {err}")
        return False
