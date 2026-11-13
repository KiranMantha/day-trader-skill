"""trader-deals tests. largedeal.json and pit-RELIANCE.json are NSE's real answers (2026-11-13), the first rows."""

import contextlib
import io
import json
import os
import unittest

from _load import load, FIX

deals = load("trader-deals", "deals")
IN = os.path.join(FIX, "india")


def read(name):
    with open(os.path.join(IN, name), encoding="utf-8") as fh:
        return json.load(fh)


class Today(unittest.TestCase):
    def test_all_kinds_ordered_bulk_block_short(self):
        r = deals.deals_today(read("largedeal.json"))
        self.assertEqual(r["date"], "12-Nov-2026")
        kinds = [d["kind"] for d in r["deals"]]
        self.assertEqual(kinds, sorted(kinds, key=["bulk", "block", "short"].index))
        d = next(x for x in r["deals"] if x["kind"] == "bulk")
        self.assertIsInstance(d["qty"], int)
        self.assertIn(d["side"], ("BUY", "SELL"))

    def test_filters(self):
        doc = read("largedeal.json")
        sym = doc["BULK_DEALS_DATA"][0]["symbol"]
        r = deals.deals_today(doc, ("bulk",), [sym.lower()])
        self.assertTrue(r["deals"] and all(d["symbol"] == sym for d in r["deals"]))
        self.assertEqual(deals.deals_today(doc, ("bulk",), None, 10 ** 12)["deals"], [])
        self.assertEqual(deals.deals_today(doc, ("bulk",), ["NOPE"])["deals"], [])

    def test_short_deals_have_no_side_or_price(self):
        d = deals.deals_today(read("largedeal.json"), ("short",))["deals"][0]
        self.assertIsNone(d["side"])

    def test_bad_answer(self):
        with self.assertRaises(deals.DealsError):
            deals.deals_today([])


class Insider(unittest.TestCase):
    def test_rows_newest_first_with_a_value_even_when_the_buy_value_is_zero(self):
        rows = deals.insiders(read("pit-RELIANCE.json"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["date"], "18-Feb-2026")
        self.assertEqual(rows[0]["side"], "Sell")
        self.assertEqual(rows[0]["value"], 3294168.0)
        buy = next(r for r in rows if r["side"] == "Buy")
        self.assertGreater(buy["value"], 0)

    def test_bad_answer(self):
        with self.assertRaises(deals.DealsError):
            deals.insiders({"nope": 1})


class Format(unittest.TestCase):
    def test_lakh_crore(self):
        self.assertEqual(deals.inr(3294168), "₹32,94,168")
        self.assertEqual(deals.inr(503), "₹503")
        self.assertEqual(deals.inr(13.37), "₹13.37")
        self.assertEqual(deals.inr(10 ** 8), "₹10,00,00,000")


class Cli(unittest.TestCase):
    def run_cli(self, *a):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = deals.main(list(a) + ["--offline", IN])
        return rc, out.getvalue(), err.getvalue()

    def test_today(self):
        rc, out, _ = self.run_cli("today", "--show", "2")
        self.assertEqual(rc, 0)
        self.assertIn("12-Nov-2026", out)
        self.assertIn("not a signal", out)
        self.assertNotIn("$", out)

    def test_today_nothing_matched_exits_1(self):
        rc, out, _ = self.run_cli("today", "--symbols", "NOPE")
        self.assertEqual(rc, 1)
        self.assertIn("Nothing matched for NOPE", out)

    def test_insider(self):
        rc, out, _ = self.run_cli("insider", "RELIANCE", "--days", "300")
        self.assertEqual(rc, 0)
        self.assertIn("RELIANCE insider disclosures", out)
        self.assertIn("₹32,94,168", out)
        self.assertIn("read the mode", out)

    def test_insider_json(self):
        rc, out, _ = self.run_cli("insider", "RELIANCE", "--json")
        self.assertEqual(json.loads(out)["symbol"], "RELIANCE")

    def test_missing_offline_file_is_an_error_not_a_crash(self):
        rc, _, err = self.run_cli("insider", "NOPE")
        self.assertEqual(rc, 1)
        self.assertIn("deals.py:", err)

    def test_no_command_prints_help(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(deals.main([]), 1)


if __name__ == "__main__":
    unittest.main()
