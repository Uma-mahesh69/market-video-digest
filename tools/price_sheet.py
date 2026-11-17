"""Makes the price sheet the Econova dashboard scores the analysts' calls with.

One row per ticker in tickers.json (plus the S&P 500 as the benchmark and any --extra tickers): Google Finance's
price, day change, 52-week high and P/E, then the daily close for the last 120 days, one column per S&P 500 trading
day. Each row is live GOOGLEFINANCE() formulas, so the sheet stays current by itself.

    python price_sheet.py --extra GOOG > price_sheet.csv

Then in Google Sheets: File > Import > Upload price_sheet.csv > Replace spreadsheet (or a new spreadsheet), with
"Convert text to numbers, dates and formulas" on. When tickers.json gains a ticker, run it again and import over the
same sheet, so the dashboard keeps reading the same file.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

TICKERS = Path(__file__).resolve().parent.parent / "app" / "tickers.json"
DAYS = 120          # calendar days of closes: about 85 trading days
WIDTH = 160         # columns the sheet gets, so the closes have room to spill
FIRST = 7           # column G: the first close
EXCHANGE = {".KS": "KRX:", ".PA": "EPA:", ".T": "TYO:", ".HK": "HKG:", ".L": "LON:", ".TO": "TSE:", ".DE": "ETR:"}


def google_symbol(ticker):
    """GOOGLEFINANCE's name for a ticker written the Yahoo way (000660.KS -> KRX:000660)."""
    for suffix, prefix in EXCHANGE.items():
        if ticker.endswith(suffix):
            return prefix + ticker[: -len(suffix)]
    return ticker


def column(n):
    name = ""
    while n:
        n, r = divmod(n - 1, 26)
        name = chr(65 + r) + name
    return name


def rows(extra=()):
    table = json.loads(TICKERS.read_text(encoding="utf-8"))
    tickers = sorted({t for k, t in table.items() if not k.startswith("_")} | set(extra))
    listed = [("SPX", "INDEXSP:.INX")] + [(t, google_symbol(t)) for t in tickers]
    span = f"$1:{column(WIDTH)}$1"
    head = ["ticker", "google_finance", "price", "change_pct_day", "high_52w", "pe",
            f'=TRANSPOSE(ARRAYFORMULA(INT(QUERY(GOOGLEFINANCE("INDEXSP:.INX","close",TODAY()-{DAYS},TODAY()),'
            '"select Col1 offset 1",0))))']
    out = [head + [""] * (WIDTH - len(head))]
    for n, (ticker, symbol) in enumerate(listed, 2):
        # each quote column is one formula over every symbol; the closes are one formula per row, matched to row 1's dates
        # (the history's own header row gets -1, so the empty cells past the last date match nothing)
        quotes = [f'=MAP(B2:B{len(listed) + 1},LAMBDA(s,IFERROR(GOOGLEFINANCE(s,"{a}"),"")))'
                  for a in ("price", "changepct", "high52", "pe")] if n == 2 else [""] * 4
        closes = (f'=IFERROR(LET(h,GOOGLEFINANCE($B{n},"close",TODAY()-{DAYS},TODAY()),ARRAYFORMULA(IFERROR(VLOOKUP('
                  f'{column(FIRST)}{span},{{IFERROR(INT(INDEX(h,0,1)),-1),INDEX(h,0,2)}},2,0),""))),"")')
        out.append([ticker, symbol, *quotes, closes])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--extra", nargs="*", default=[], help="more tickers, such as a holding that tickers.json lacks")
    args = ap.parse_args()
    csv.writer(sys.stdout, lineterminator="\n").writerows(rows(args.extra))


if __name__ == "__main__":
    main()
