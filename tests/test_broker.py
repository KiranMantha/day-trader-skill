"""trader-broker tests: the Kite ticket and the trade log. Nothing here talks to a broker."""

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest

from _load import load

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")
size = load("trader-budget", "size")
NOW = "2026-11-13 10:00"
ORDER = {"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "qty": 62, "product": "MIS", "type": "market",
         "validity": "DAY", "stop_loss_trigger": "1332.05", "target_price": "1356.00", "segment": "equity",
         "lot_size": 1, "tick": 0.05, "margin_required": 16616.0, "why": "62 shares, bound by max loss",
         "plan": {"entry": 1340.0, "stop": 1332.05, "target": 1356.0, "flat_by": "15:15"}}


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        j = lambda n: os.path.join(self.tmp.name, n)
        self.orders, self.risk, self.state, self.cfg = j("orders.json"), j("risk.json"), j("broker.json"), j("config.json")
        with open(self.orders, "w") as fh:
            json.dump({"orders": [ORDER]}, fh)
        with open(self.cfg, "w") as fh:
            json.dump({"budget": 100000}, fh)

    def args(self, *a):
        return list(a) + ["--orders", self.orders, "--risk", self.risk, "--state", self.state, "--config", self.cfg,
                          "--now", NOW]

    def run_cli(self, *a):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ticket.main(self.args(*a))
        return rc, out.getvalue(), err.getvalue()

    def check_risk(self, now=NOW):
        with contextlib.redirect_stdout(io.StringIO()):
            return check.main(["--orders", self.orders, "--config", self.cfg, "--out", self.risk, "--now", now,
                               "--portfolio", "none", "--prices", "none", "--state", self.state])


class Show(Env):
    def test_fingerprints_match_trader_risk(self):
        self.assertEqual(ticket.fingerprint(ORDER), check.fingerprint(ORDER))

    def test_not_ready_without_a_risk_check(self):
        rc, out, _ = self.run_cli("show")
        self.assertEqual(rc, 1)
        self.assertIn("NOT READY", out)

    def test_ready_after_a_pass_and_shows_kite_fields(self):
        self.check_risk()
        rc, out, _ = self.run_cli("show")
        self.assertEqual(rc, 0, out)
        for s in ("READY", "BUY 62 NSE RELIANCE, MIS, market", "Kite order window", "trigger 1332.05", "1356.00",
                  "no bracket orders", "₹492.90", "₹16,616", "15:15 IST"):
            self.assertIn(s, out)
        self.assertNotIn("$", out)
        self.assertNotIn("Alpaca", out)

    def test_changed_order_is_not_ready(self):
        self.check_risk()
        with open(self.orders, "w") as fh:
            json.dump({"orders": [dict(ORDER, qty=61)]}, fh)
        rc, out, _ = self.run_cli("show")
        self.assertIn("NOT READY", out)

    def test_blocked_order_says_why(self):
        self.check_risk("2026-11-13 15:20")
        rc, out, _ = self.run_cli("show")
        self.assertIn("BLOCKED by trader-risk", out)
        self.assertIn("no new entries after 15:00", out)

    def test_json(self):
        self.check_risk()
        _, out, _ = self.run_cli("show", "--index", "1", "--json")
        doc = json.loads(out)
        self.assertTrue(doc["ready"])
        self.assertEqual(doc["order"]["symbol"], "RELIANCE")


class Log(Env):
    def test_placed_is_refused_unless_ready(self):
        rc, _, err = self.run_cli("placed", "--index", "1")
        self.assertEqual(rc, 1)
        self.assertIn("not ready", err)

    def test_placed_then_done_and_risk_counts_it(self):
        self.check_risk()
        rc, out, _ = self.run_cli("placed", "--index", "1", "--kite-id", "2611130012345678")
        self.assertEqual(rc, 0, out)
        with open(self.state) as fh:
            rec = json.load(fh)["orders"][0]
        self.assertEqual((rec["status"], rec["kind"], rec["max_loss"], rec["broker_order_id"]),
                         ("placed", "entry", 492.9, "2611130012345678"))
        self.assertIn("DONE", self.run_cli("show")[1])
        self.assertEqual(self.run_cli("placed", "--index", "1")[0], 1)       # not twice
        self.assertEqual(self.check_risk(), 1)                               # trader-risk now sees the duplicate

    def test_fill_tracks_the_open_position_and_the_flat(self):
        _, out, _ = self.run_cli("fill", "--symbol", "reliance", "--side", "buy", "--qty", "62", "--price", "1340.05")
        self.assertIn("open today: +62", out)
        _, out, _ = self.run_cli("fill", "--symbol", "RELIANCE", "--side", "sell", "--qty", "62", "--price", "1352")
        self.assertIn("flat today: gross ₹740.90", out)

    def test_fill_validates(self):
        self.assertEqual(self.run_cli("fill", "--symbol", "X", "--side", "hold", "--qty", "1", "--price", "1")[0], 1)
        self.assertEqual(self.run_cli("fill", "--symbol", "X", "--side", "buy", "--qty", "0", "--price", "1")[0], 1)

    def test_skip_and_log(self):
        self.run_cli("skip", "--index", "1", "--note", "gapped away")
        _, out, _ = self.run_cli("log")
        self.assertIn("skipped", out)

    def test_flatten_prints_kite_steps(self):
        _, out, _ = self.run_cli("flatten", "--symbol", "RELIANCE", "--qty", "62")
        for s in ("Positions", "Exit", "15:15", "square"):
            self.assertIn(s, out)

    def test_ist_timestamps(self):
        self.assertEqual(ticket.ist_iso(ticket.parse_now(NOW)), "2026-11-13T10:00:00+05:30")

    def test_bad_index(self):
        self.assertEqual(self.run_cli("placed", "--index", "5")[0], 1)
        self.assertEqual(self.run_cli("placed")[0], 1)


if __name__ == "__main__":
    unittest.main()
