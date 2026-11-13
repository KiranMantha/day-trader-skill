"""trader-exit tests: stop and target on the NSE tick (Rs 0.05)."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from decimal import Decimal

from _load import load

exit_ = load("trader-exit", "exit")
D = Decimal


def plan(entry, rule="or_mid", param=None, target=("r", D(2)), oh=None, ol=None, tick="0.05"):
    exit_.TICK = D(tick)
    try:
        return exit_.compute(entry, rule, param, target[0], target[1], oh, ol)
    finally:
        exit_.TICK = D("0.05")


class Tick(unittest.TestCase):
    def test_stop_rounds_down_to_the_tick_away_from_the_entry(self):
        self.assertEqual(exit_.floor_cents("1334.275"), D("1334.25"))
        self.assertEqual(exit_.floor_cents("1334.30"), D("1334.30"))
        self.assertEqual(exit_.floor_cents("100.04"), D("100.00"))

    def test_target_rounds_half_up_to_the_tick(self):
        self.assertEqual(exit_.cents("1359.025"), D("1359.05"))
        self.assertEqual(exit_.cents("1359.02"), D("1359.00"))
        self.assertEqual(exit_.cents("1359.07"), D("1359.05"))

    def test_money_has_rupee_sign_and_lakh_grouping(self):
        self.assertEqual(exit_.money("1342.5"), "₹1,342.50")
        self.assertEqual(exit_.money("1234567.5"), "₹12,34,567.50")


class Compute(unittest.TestCase):
    def test_or_mid_stop_and_2r_target(self):
        c = plan("1342.50", oh="1340", ol="1328.55")
        self.assertEqual(c["stop"], D("1334.25"))
        self.assertEqual(c["risk"], D("8.25"))
        self.assertEqual(c["target"], D("1359.00"))
        self.assertEqual(c["reward_risk"], D("2.00"))

    def test_every_price_is_a_multiple_of_the_tick(self):
        for entry in ("101.13", "257.77", "1342.50", "3999.95"):
            c = plan(entry, "pct", D("1.3"))
            for k in ("stop", "target"):
                self.assertEqual(c[k] % D("0.05"), 0, (entry, k, c[k]))

    def test_other_tick(self):
        c = plan("100.00", "pct", D("1"), tick="0.01")
        self.assertEqual(c["stop"], D("99.00"))

    def test_refusals(self):
        with self.assertRaises(exit_.PlanError):
            plan("100", "price", D("100"))                      # stop at the entry
        with self.assertRaises(exit_.PlanError):
            plan("100", "price", D("101"))                      # stop above
        with self.assertRaises(exit_.PlanError):
            plan("1000", "price", D("999.95"))                  # under 0.05% of the price
        with self.assertRaises(exit_.PlanError):
            plan("100", "price", D("99"), target=("price", D("100")))   # target at the entry
        with self.assertRaises(exit_.PlanError):
            plan("100", "or_mid", None)                         # no opening range

    def test_error_text_uses_rupees(self):
        with self.assertRaises(exit_.PlanError) as cm:
            plan("0", "pct", D("1"))
        self.assertIn("₹0", str(cm.exception))


class Cli(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = exit_.main(list(argv))
        return rc, out.getvalue()

    def test_plan_writes_the_json_the_next_skills_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plan.json")
            rc, text = self.run_cli("plan", "--symbol", "RELIANCE", "--entry", "1342.50", "--or-high", "1340",
                                    "--or-low", "1328.55", "--setup", "orb", "--date", "2026-11-13",
                                    "--time", "10:15 AM", "--now", "2026-11-13 10:20", "--write", path,
                                    "--config", os.path.join(d, "none.json"))
            self.assertEqual(rc, 0, text)
            with open(path) as fh:
                p = json.load(fh)
        self.assertEqual((p["symbol"], p["stop"], p["target"], p["flat_by"], p["tick"]),
                         ("RELIANCE", 1334.25, 1359.0, "15:15", 0.05))
        self.assertIn("15:15 IST", text)
        self.assertIn("₹1,342.50", text)

    def test_flat_by_comes_from_the_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "c.json")
            with open(cfg, "w") as fh:
                json.dump({"flat_by": "14:45"}, fh)
            rc, text = self.run_cli("plan", "--symbol", "SBIN", "--entry", "800", "--setup", "level",
                                    "--stop", "pct:1", "--date", "2026-11-13", "--time", "10:15 AM",
                                    "--now", "2026-11-13 10:20", "--config", cfg, "--json")
        self.assertEqual(json.loads(text)["flat_by"], "14:45")

    def test_a_short_is_refused(self):
        rc, _ = self.run_cli("plan", "--symbol", "SBIN", "--entry", "800", "--setup", "level", "--stop", "pct:1",
                             "--side", "sell", "--now", "2026-11-13 10:20")
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
