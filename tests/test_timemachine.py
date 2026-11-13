"""trader-timemachine tests. RELIANCE.NS-60d5m.json.gz is a real Yahoo 60-day 5-minute chart (2026-11-13 10:15 IST)."""

import contextlib
import datetime
import io
import json
import os
import unittest

from _load import load, FIX
import _synth

tm = load("trader-timemachine", "timemachine")
CHART = os.path.join(FIX, "india", "RELIANCE.NS-60d5m.json.gz")
NOW = tm.parse_now("2026-11-13 10:20")
PLAN_ARGS = ["run", "--offline", CHART, "--now", "2026-11-13 10:20", "--symbol", "RELIANCE", "--date", "2026-11-13",
             "--entry", "1334.00", "--stop", "1328.80", "--target", "1344.40", "--entry-time", "10:05 AM",
             "--until", "15:15", "--json"]


def run_cli(*extra):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = tm.main(PLAN_ARGS + list(extra))
    return rc, out.getvalue()


def sessions_of(days):
    """{iso date: {slot: bar}} for synthetic days, each a list of bars (or None for a no-trade slot)."""
    bars = []
    for day, spec in days.items():
        text = _synth.chart(day, spec, "DEMO.NS")
        res = tm.chart_result(text, "DEMO")
        meta, got, _ = tm.parse_bars(res, datetime.datetime(2026, 12, 1))
        bars += got
    return tm.split_sessions(bars)


def day(n, missing=()):
    return [None if i in missing else (100 + i * 0.01, 100.5 + i * 0.01, 99.5, 100 + i * 0.01, 1000) for i in range(n)]


class Session(unittest.TestCase):
    def test_nse_constants(self):
        self.assertEqual((tm.SESSION_BARS, tm.OPEN_MIN, tm.CLOSE_MIN), (75, 9 * 60 + 15, 15 * 60 + 30))
        self.assertEqual(tm.NSE_EARLY_CLOSE, {})

    def test_full_session_has_75_slots_from_9_15(self):
        days = sessions_of({datetime.date(2026, 11, 11): day(75)})
        full, short = tm.full_sessions(days, "2026-11-12")
        self.assertEqual((len(full), short), (1, []))
        self.assertEqual(full[0][1][0]["start"], "09:15")
        self.assertEqual(full[0][1][74]["start"], "15:25")

    def test_no_trade_slots_are_filled_flat_up_to_three(self):
        days = sessions_of({datetime.date(2026, 11, 11): day(75, missing=(10, 40)),
                            datetime.date(2026, 11, 12): day(75, missing=(5, 6, 7, 8))})
        full, short = tm.full_sessions(days, "2026-11-13")
        self.assertEqual([d for d, _ in full], ["2026-11-11"])
        self.assertEqual([s["date"] for s in short], ["2026-11-12"])
        filled = full[0][1][10]
        self.assertEqual((filled["o"], filled["h"], filled["l"], filled["c"], filled["v"]),
                         (full[0][1][9]["c"],) * 4 + (0,))

    def test_a_missing_opening_slot_leaves_the_session_out(self):
        days = sessions_of({datetime.date(2026, 11, 11): day(75, missing=(0,))})
        self.assertEqual(tm.full_sessions(days, "2026-11-12")[0], [])

    def test_today_is_never_in_the_pool(self):
        days = sessions_of({datetime.date(2026, 11, 13): day(75)})
        self.assertEqual(tm.full_sessions(days, "2026-11-13")[0], [])

    def test_symbol_mapping(self):
        self.assertEqual(tm.yahoo_symbol("m&m"), "M&M.NS")
        self.assertIn("/M%26M.NS?range=60d", tm.chart_url("M&M"))

    def test_plan_symbol_regex_takes_nse_names(self):
        for sym in ("M&M", "BAJAJ-AUTO", "360ONE"):
            plan = tm.normalize_plan({"symbol": sym, "entry": 100, "stop": 99, "target": 102, "date": "2026-11-13",
                                      "entry_time": "10:05 AM"}) if hasattr(tm, "normalize_plan") else None
            self.assertEqual(plan["symbol"], sym)


class Run(unittest.TestCase):
    def test_real_chart_gives_the_recorded_odds(self):
        rc, out = run_cli()
        self.assertEqual(rc, 0, out)
        doc = json.loads(out)
        mc = doc["mc"]
        self.assertEqual((mc["p_target"], mc["p_stop"], mc["p_neither"]), (0.2409, 0.6821, 0.077))
        self.assertEqual((mc["replays"], mc["seed"], mc["bars_left"]), (10000, 19, 62))
        self.assertEqual(doc["data"]["symbol"], "RELIANCE.NS")
        self.assertEqual(doc["plan"]["entry_bar"], 9)                 # 9:15 + 9 x 5 min = 10:00 bar

    def test_same_seed_same_numbers_and_a_new_seed_differs(self):
        a, b = json.loads(run_cli()[1])["mc"], json.loads(run_cli()[1])["mc"]
        self.assertEqual(a["p_target"], b["p_target"])
        c = json.loads(run_cli("--seed", "7")[1])["mc"]
        self.assertNotEqual(a["p_target"], c["p_target"])

    def test_probabilities_add_up(self):
        mc = json.loads(run_cli()[1])["mc"]
        self.assertAlmostEqual(mc["p_target"] + mc["p_stop"] + mc["p_neither"], 1.0, places=3)

    def test_until_must_be_on_the_grid_and_inside_the_session(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run_cli("--until", "15:45")[0], 1)
            self.assertEqual(run_cli("--until", "15:17")[0], 1)

    def test_wrong_symbol_in_the_data_is_refused(self):
        out, err = io.StringIO(), io.StringIO()
        args = [a if a != "RELIANCE" else "INFY" for a in PLAN_ARGS]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tm.main(args)
        self.assertEqual(rc, 1)
        self.assertIn("RELIANCE.NS", err.getvalue())

    def test_text_report_is_in_ist_and_rupees(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tm.main([a for a in PLAN_ARGS if a != "--json"])
        text = out.getvalue()
        self.assertIn("3:15 PM", text)
        self.assertIn("RELIANCE", text)
        self.assertNotIn("$", text)
        self.assertNotIn("4:00 PM", text)


if __name__ == "__main__":
    unittest.main()
