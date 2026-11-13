"""trader-alerts tests. yahoo-RELIANCE.json and yahoo-INFY.json are real Yahoo chart answers (2026-11-13)."""

import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from _load import load, FIX

alerts = load("trader-alerts", "alerts")
QDIR = os.path.join(FIX, "india")
DT = datetime.datetime


def ist(text):
    return alerts.parse_now(text)


def quote(sym="RELIANCE"):
    with open(os.path.join(QDIR, "yahoo-%s.json" % sym)) as fh:
        return alerts.parse_yahoo(fh.read(), sym)


class Clock(unittest.TestCase):
    def test_open_session_and_next_open(self):
        st = alerts.market_status(ist("2026-11-13 10:00"))
        self.assertTrue(st["open"])
        self.assertEqual((st["opens"], st["closes"], st["now_ist"]), ("09:15", "15:30", "2026-11-13 10:00"))

    def test_edges_of_the_session(self):
        self.assertFalse(alerts.market_status(ist("2026-11-13 09:14"))["open"])
        self.assertTrue(alerts.market_status(ist("2026-11-13 09:15"))["open"])
        self.assertTrue(alerts.market_status(ist("2026-11-13 15:29"))["open"])
        self.assertFalse(alerts.market_status(ist("2026-11-13 15:30"))["open"])

    def test_holiday_weekend_and_next_open(self):
        st = alerts.market_status(ist("2026-11-10 10:00"))
        self.assertFalse(st["open"])
        self.assertIn("Diwali", st["reason"])
        self.assertEqual(st["next_open"], "2026-11-11 09:15")
        self.assertEqual(alerts.market_status(ist("2026-11-14 10:00"))["reason"], "weekend")

    def test_calendar_years(self):
        self.assertTrue(alerts.market_status(ist("2026-11-13 10:00"))["calendar_known"])
        self.assertFalse(alerts.market_status(ist("2027-01-04 10:00"))["calendar_known"])


class Quotes(unittest.TestCase):
    def test_real_yahoo_answer(self):
        q = quote()
        self.assertEqual((q["symbol"], q["currency"], q["source"]), ("RELIANCE", "INR", "yahoo"))
        self.assertGreater(q["price"], 100)
        self.assertTrue(q["time"].startswith("2026-11-13"))

    def test_symbol_mapping_in_the_url(self):
        self.assertIn("/RELIANCE.NS?", alerts.yahoo_url("reliance"))
        self.assertIn("/M%26M.NS?", alerts.yahoo_url("M&M"))
        self.assertIn("/^NSEI?", alerts.yahoo_url("^NSEI"))

    def test_offline_folder_and_errors(self):
        quotes, errors = alerts.get_quotes(["RELIANCE", "NOPE"], "yahoo", QDIR)
        self.assertEqual(list(quotes), ["RELIANCE"])
        self.assertEqual(len(errors), 1)

    def test_unexpected_answer(self):
        with self.assertRaises(alerts.AlertError):
            alerts.parse_yahoo("<html>", "X")

    def test_no_stooq_left(self):
        self.assertFalse(hasattr(alerts, "parse_stooq"))


def rules():
    return [{"id": "stop", "symbol": "RELIANCE", "type": "stop", "price": 1332.05, "date": "2026-11-13"},
            {"id": "tgt", "symbol": "RELIANCE", "type": "target", "price": 1356.0, "date": "2026-11-13"},
            {"id": "flat", "symbol": "RELIANCE", "type": "time", "at": "15:15", "label": "square off MIS",
             "date": "2026-11-13"}]


def at(text, price, rs=None, state=None):
    now = ist(text)
    q = {"RELIANCE": {"price": price, "prev_close": 1340.0, "open": 1340.0}}
    return alerts.evaluate(rs or rules(), q, alerts.market_status(now), state or {}, now)


class Rings(unittest.TestCase):
    def test_stop_rings_once(self):
        rings, st = at("2026-11-13 11:00", 1331.0)
        self.assertEqual([r["id"] for r in rings], ["stop"])
        self.assertIn("₹1331.00", rings[0]["message"])
        self.assertIn("at or below", rings[0]["message"])
        again, _ = at("2026-11-13 11:05", 1330.0, state=st)
        self.assertEqual(again, [])

    def test_target_rings(self):
        self.assertEqual([r["id"] for r in at("2026-11-13 11:00", 1357.0)[0]], ["tgt"])

    def test_nothing_in_between(self):
        self.assertEqual(at("2026-11-13 11:00", 1340.0)[0], [])

    def test_square_off_rings_at_15_15_and_tells_you_to_use_kite(self):
        self.assertEqual(at("2026-11-13 15:14", 1340.0)[0], [])
        rings, _ = at("2026-11-13 15:16", 1340.0)
        self.assertEqual([r["id"] for r in rings], ["flat"])
        self.assertIn("Kite", rings[0]["message"])
        self.assertIn("squares MIS off", rings[0]["message"])
        self.assertNotIn("trader-broker flatten", rings[0]["message"])

    def test_a_rule_for_another_day_is_ignored(self):
        self.assertEqual(at("2026-11-16 11:00", 1331.0)[0], [])

    def test_pct_move(self):
        rs = [{"id": "mv", "symbol": "RELIANCE", "type": "pct_move", "pct": 3}]
        self.assertEqual(at("2026-11-13 11:00", 1385.0, rs)[0][0]["id"], "mv")
        self.assertEqual(at("2026-11-13 11:00", 1350.0, rs)[0], [])

    def test_opening_bell(self):
        rs = [{"id": "bell", "type": "opening_bell"}]
        now = ist("2026-11-13 09:16")
        rings, _ = alerts.evaluate(rs, {}, alerts.market_status(now), {}, now)
        self.assertIn("the NSE is open", rings[0]["message"])


class FromPlan(unittest.TestCase):
    PLAN = {"symbol": "RELIANCE", "stop": 1332.05, "target": 1356.0, "date": "2026-11-13"}

    def test_three_rules_and_the_default_square_off_is_15_15(self):
        rs = alerts.rules_from_plan(self.PLAN)
        self.assertEqual([r["type"] for r in rs], ["stop", "target", "time"])
        self.assertEqual((rs[2]["at"], rs[2]["label"]), ("15:15", "square off MIS"))
        self.assertTrue(all(r["date"] == "2026-11-13" for r in rs))

    def test_plan_without_a_stop_is_refused(self):
        with self.assertRaises(alerts.AlertError):
            alerts.rules_from_plan({"symbol": "X", "target": 5})


class Watch(unittest.TestCase):
    def args(self, d, *extra):
        return ["watch", "--rules", os.path.join(d, "alerts.json"), "--state", os.path.join(d, "s.json"),
                "--prices-out", os.path.join(d, "p.json"), "--offline", QDIR, "--no-notify"] + list(extra)

    def test_single_pass_replay_rings_and_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "alerts.json"), "w") as fh:
                json.dump({"rules": [{"id": "above", "symbol": "RELIANCE", "type": "above", "price": 100}]}, fh)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = alerts.main(self.args(d, "--now", "2026-11-13 10:00"))
            self.assertEqual(rc, 0, out.getvalue())
            self.assertIn("ALERT RELIANCE", out.getvalue())
            self.assertIn("nothing was placed", out.getvalue())
            # the state file is shared with check: a second pass rings nothing
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = alerts.main(["check", "--rules", os.path.join(d, "alerts.json"), "--state", os.path.join(d, "s.json"),
                                  "--prices-out", os.path.join(d, "p.json"), "--offline", QDIR, "--now", "2026-11-13 10:05"])
            self.assertEqual(rc, 1)
            with open(os.path.join(d, "p.json")) as fh:
                self.assertIn("RELIANCE", json.load(fh)["prices"])

    def test_notification_is_sent_without_a_shell(self):
        with mock.patch.object(alerts.subprocess, "run") as run, mock.patch.object(alerts.sys, "platform", "darwin"):
            alerts.notify('T "quoted"', 'msg"; do shell script "x')
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "osascript")
        self.assertIn('msg"; do shell script "x', argv)        # passed as an argument, never spliced into the script

    def test_watch_stops_by_itself_after_the_close(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "alerts.json"), "w") as fh:
                json.dump({"rules": [{"id": "r", "symbol": "RELIANCE", "type": "above", "price": 1e9}]}, fh)
            real_now = alerts.parse_now
            with mock.patch.object(alerts, "parse_now", lambda t=None: real_now("2026-11-13 15:31")):
                out = io.StringIO()
                args = ["watch", "--rules", os.path.join(d, "alerts.json"), "--state", os.path.join(d, "s.json"),
                        "--prices-out", os.path.join(d, "p.json"), "--no-notify", "--no-write"]
                with mock.patch.object(alerts, "get_quotes", return_value=({"RELIANCE": {"price": 1.0}}, [])), \
                        contextlib.redirect_stdout(out):
                    rc = alerts.main(args)
            self.assertEqual(rc, 1)
            self.assertIn("The NSE has closed", out.getvalue())


class Cli(unittest.TestCase):
    def test_clock(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            alerts.main(["clock", "--now", "2026-11-13 10:00"])
        self.assertIn("NSE OPEN", out.getvalue())
        self.assertIn("09:15 to 15:30", out.getvalue())

    def test_add_from_plan_writes_rules(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "plan.json")
            with open(plan, "w") as fh:
                json.dump(FromPlan.PLAN, fh)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = alerts.main(["add", "--from-plan", "--plan", plan, "--rules", os.path.join(d, "a.json"),
                                  "--config", os.path.join(d, "none")])
            self.assertEqual(rc, 0)
            with open(os.path.join(d, "a.json")) as fh:
                self.assertEqual(len(json.load(fh)["rules"]), 3)
            self.assertNotIn("bracket", out.getvalue())


if __name__ == "__main__":
    unittest.main()
