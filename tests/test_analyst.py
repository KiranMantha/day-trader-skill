"""trader-analyst tests. results-INFY.json and results-SBIN.json are NSE's real results-comparision answers (2026-11-13)."""

import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest

from _load import load, FIX

facts = load("trader-analyst", "facts")
IN = os.path.join(FIX, "india")
TODAY = datetime.date(2026, 11, 13)


def read(name):
    with open(os.path.join(IN, name), encoding="utf-8") as fh:
        return fh.read()


def infy():
    q, bank = facts.parse_results(read("results-INFY.json"), "INFY")
    return facts.analyse(q, TODAY), bank


class Parse(unittest.TestCase):
    def test_five_quarters_oldest_first_in_crore(self):
        q, bank = facts.parse_results(read("results-INFY.json"), "INFY")
        self.assertFalse(bank)
        self.assertEqual([x["end"] for x in q][-1], "2024-12-31")
        self.assertEqual(len(q), 5)
        last = q[-1]
        self.assertEqual(last["revenue"], 34915.0)          # NSE says 3491500 lakh
        self.assertEqual(last["net_profit"], 6358.0)
        self.assertEqual(last["eps_diluted"], 15.29)

    def test_bank_layout_has_no_revenue(self):
        q, bank = facts.parse_results(read("results-SBIN.json"), "SBIN")
        self.assertTrue(bank)
        self.assertTrue(all(x["revenue"] is None for x in q))
        self.assertIsNotNone(q[-1]["net_profit"])

    def test_bad_answers(self):
        with self.assertRaises(facts.FactsError):
            facts.parse_results("<html>", "X")
        with self.assertRaises(facts.FactsError):
            facts.parse_results(json.dumps({"resCmpData": []}), "X")

    def test_a_non_quarter_row_is_ignored(self):
        doc = json.loads(read("results-INFY.json"))
        row = dict(doc["resCmpData"][0], re_from_dt="01-APR-2024", re_to_dt="31-MAR-2025")   # a year
        doc["resCmpData"].append(row)
        q, _ = facts.parse_results(json.dumps(doc), "INFY")
        self.assertEqual(len(q), 5)


class Analyse(unittest.TestCase):
    def test_growth_margin_and_ttm(self):
        res, _ = infy()
        last = res["quarters"][-1]
        self.assertEqual(last["revenue_yoy"], 7.5)
        self.assertEqual(last["profit_yoy"], -3.0)
        self.assertEqual(last["net_margin"], 18.2)
        self.assertEqual(res["quarters"][0]["revenue_yoy"], None)       # no year-ago quarter in 5
        self.assertEqual(res["ttm_net_profit"], 27419.0)
        self.assertEqual(res["ttm_eps"], 65.95)

    def test_stale_flag(self):
        res, _ = infy()
        self.assertTrue(res["stale"])
        self.assertEqual(res["age_days"], 682)
        q, _ = facts.parse_results(read("results-INFY.json"), "INFY")
        fresh = facts.analyse(q, datetime.date(2025, 2, 1))
        self.assertFalse(fresh["stale"])

    def test_pct_handles_zero_and_none(self):
        self.assertIsNone(facts.pct(5, 0))
        self.assertIsNone(facts.pct(None, 5))
        self.assertEqual(facts.pct(110, 100), 10.0)
        self.assertEqual(facts.pct(-50, -100), 50.0)


class Cli(unittest.TestCase):
    def run_cli(self, *a):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = facts.main(list(a) + ["--offline", IN, "--today", "2026-11-13"])
        return rc, out.getvalue(), err.getvalue()

    def test_table_says_standalone_stale_and_rupees_crore(self):
        rc, out, _ = self.run_cli("INFY")
        self.assertEqual(rc, 0)
        for s in ("standalone", "STALE", "rupees crore", "2024-12-31", "34,915"):
            self.assertIn(s, out)
        self.assertNotIn("$", out)
        self.assertNotIn("SEC", out)

    def test_a_missing_symbol_is_reported_and_the_rest_still_run(self):
        rc, out, err = self.run_cli("INFY", "NOPE")
        self.assertEqual(rc, 1)
        self.assertIn("NOPE", err)
        self.assertIn("INFY", out)

    def test_json_and_metrics_merge(self):
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, "m.json")
            with open(m, "w") as fh:
                json.dump({"OLD": {"x": 1}}, fh)
            rc, out, _ = self.run_cli("INFY", "--metrics", m, "--json")
            self.assertEqual(rc, 0)
            self.assertIn("INFY", json.loads(out))
            with open(m) as fh:
                doc = json.load(fh)
        self.assertEqual(sorted(doc), ["INFY", "OLD"])
        self.assertEqual(doc["INFY"]["ttm_net_profit_cr"], 27419.0)

    def test_quarters_flag_trims_after_growth_is_computed(self):
        _, out, _ = self.run_cli("INFY", "--quarters", "1", "--json")
        q = json.loads(out)["INFY"]["quarters"]
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["revenue_yoy"], 7.5)


if __name__ == "__main__":
    unittest.main()
