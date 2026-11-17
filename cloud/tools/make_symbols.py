"""Build cloud/web/symbols.json, the list the search box looks through: every US-listed stock and fund (from Nasdaq
Trader's public symbol directory), and India's NSE list when it answers. Run by the deploy workflow before each
deploy; a list that cannot be fetched is skipped, and the file already in the repository is kept as the base.

    python cloud/tools/make_symbols.py
"""
import csv
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "symbols.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; symbol-list-builder)"}
US = ["https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"]
NSE = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
SKIP = re.compile(r"\b(warrants?|units?|rights?|notes? due|debentures?|preferred|depositary shares? each|% )", re.I)
TAIL = re.compile(r"\s*[-,]?\s*(common stock|common shares|ordinary shares?|class [a-c]( common stock| ordinary shares?)?|american depositary shares?|"
                  r"each representing.*|depositary shares?|shares of beneficial interest|\(the\)|new)\s*$", re.I)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def tidy(name):
    name = name.split(" - ")[0].strip()
    for _ in range(3):
        name = TAIL.sub("", name).strip(" ,-")
    return name[:60]


def us_rows(text):
    """[(ticker, name)] from one of Nasdaq Trader's pipe-separated files. Test issues, warrants and units are left out."""
    lines = text.splitlines()
    head = lines[0].split("|")
    sym = head.index("Symbol") if "Symbol" in head else head.index("ACT Symbol")
    name, test = head.index("Security Name"), head.index("Test Issue")
    out = []
    for line in lines[1:]:
        f = line.split("|")
        if len(f) <= max(sym, name, test) or f[test] != "N" or line.startswith("File Creation Time"):
            continue
        t = f[sym].strip().replace(".", "-")   # BRK.B is BRK-B where the prices come from
        if not re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", t) or SKIP.search(f[name]):
            continue
        out.append((t, tidy(f[name])))
    return out


def nse_rows(text):
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        r = {k.strip(): (v or "").strip() for k, v in r.items()}
        if r.get("SERIES") == "EQ" and re.fullmatch(r"[A-Z0-9&-]{1,12}", r.get("SYMBOL", "")) and "&" not in r["SYMBOL"]:
            out.append((r["SYMBOL"] + ".NS", tidy(r.get("NAME OF COMPANY", "").title())))
    return out


def main():
    try:
        names = {t: n for t, n in json.loads(OUT.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        names = {}
    before = len(names)
    for url, parse in [(US[0], us_rows), (US[1], us_rows), (NSE, nse_rows)]:
        try:
            rows = parse(get(url))
            for t, n in rows:
                names.setdefault(t, n)   # a name already in the file (checked by hand) wins
            print(f"{len(rows):>6} from {url}")
        except Exception as err:   # a list that is down must not stop a deploy
            print(f"skipped {url}: {type(err).__name__}: {str(err)[:100]}", file=sys.stderr)
    OUT.write_text(json.dumps(sorted([t, n] for t, n in names.items() if n), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OUT.name}: {len(names)} symbols ({len(names) - before} new)")


if __name__ == "__main__":
    main()
