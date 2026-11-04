"""Tests for price_sheet.py: the Google Sheet of prices the dashboard scores the calls with. No network.
Run from the project folder: python -m unittest -v"""
import csv
import io
import json
import unittest

import price_sheet as ps


class PriceSheet(unittest.TestCase):
    def test_one_row_per_ticker_after_the_benchmark(self):
        rows = ps.rows(["GOOG"])
        tickers = {t for k, t in json.loads(ps.TICKERS.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        self.assertEqual(rows[0][:6], ["ticker", "google_finance", "price", "change_pct_day", "high_52w", "pe"])
        self.assertEqual(rows[1][:2], ["SPX", "INDEXSP:.INX"])
        self.assertEqual({r[0] for r in rows[2:]}, tickers | {"GOOG"})
        self.assertEqual(len(rows[0]), ps.WIDTH)   # the sheet is wide enough for the closes to spill

    def test_google_finance_names(self):
        self.assertEqual(ps.google_symbol("000660.KS"), "KRX:000660")
        self.assertEqual(ps.google_symbol("MC.PA"), "EPA:MC")
        self.assertEqual(ps.google_symbol("BRK.B"), "BRK.B")

    def test_formulas_point_at_their_own_row(self):
        rows = ps.rows()
        self.assertIn('MAP(B2:B{},'.format(len(rows)), rows[1][2])           # one quote formula covers every symbol
        self.assertIn("GOOGLEFINANCE($B5,", rows[4][6])                        # each history reads its own symbol
        self.assertIn("G$1:FD$1", rows[4][6])                                  # matched to the dates in row 1
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        self.assertEqual(list(csv.reader(io.StringIO(buf.getvalue())))[4][6], rows[4][6])   # survives CSV quoting


if __name__ == "__main__":
    unittest.main()
