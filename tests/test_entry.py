"""trader-entry tests. tests/fixtures/india/RELIANCE.NS.json is a real Yahoo 5-day 5-minute chart for
RELIANCE.NS (fetched 2026-11-13 15:10 IST). _synth.py builds exact synthetic sessions for the edge cases."""

import datetime
import os
import unittest

from _load import load, FIX
import _synth

entry = load("trader-entry", "entry")
RELIANCE = os.path.join(FIX, "india", "RELIANCE.NS.json")
DAY = datetime.date(2026, 11, 12)    # a Thursday, a full 75-bar session in the fixture
IST = entry.ist_to_utc


def now(text):
    return entry.parse_now(text)


def real(text="2026-11-12 10:15", **kw):
    with open(RELIANCE) as fh:
        chart = entry.parse_chart(fh.read(), "RELIANCE")
    return entry.evaluate(chart, now(text), **kw)


def synth(bars, text, symbol="DEMO.NS", **kw):
    return entry.evaluate(entry.parse_chart(_synth.chart(DAY, bars, symbol), symbol), now(text), **kw)


# 15-minute range 100..105 (three bars), then bars that do not break out
RANGE = [(100, 104, 99, 103, 1000), (103, 105, 101, 104, 1000), (104, 105, 100, 102, 1000)]
FLAT = (102, 104, 101, 103, 1000)


class Time(unittest.TestCase):
    def test_ist_has_no_daylight_saving(self):
        d = datetime.datetime(2026, 11, 12, 3, 45)
        self.assertEqual(entry.to_ist(d), datetime.datetime(2026, 11, 12, 9, 15))
        self.assertEqual(entry.ist_to_utc(entry.to_ist(d)), d)
        summer = datetime.datetime(2026, 7, 1, 3, 45)
        self.assertEqual(entry.to_ist(summer).hour, 9)

    def test_parse_now_is_ist_unless_it_says_otherwise(self):
        self.assertEqual(entry.parse_now("2026-11-12 10:15"), datetime.datetime(2026, 11, 12, 4, 45))
        self.assertEqual(entry.parse_now("2026-11-12T10:15:00Z"), datetime.datetime(2026, 11, 12, 10, 15))
        with self.assertRaises(entry.EntryError):
            entry.parse_now("tuesday")

    def test_calendar(self):
        self.assertEqual(entry.session(DAY), (datetime.time(9, 15), datetime.time(15, 30)))
        self.assertEqual(entry.trading_day(datetime.date(2026, 11, 10)), (False, "NSE holiday: Diwali-Balipratipada"))
        self.assertEqual(entry.trading_day(datetime.date(2026, 11, 14)), (False, "weekend"))
        self.assertIsNone(entry.session(datetime.date(2026, 1, 26)))        # Republic Day
        self.assertEqual(entry.next_open(datetime.date(2026, 11, 9)), "2026-11-11 09:15")  # Diwali holiday skipped

    def test_symbol_mapping(self):
        self.assertEqual(entry.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(entry.yahoo_symbol("M&M"), "M&M.NS")
        self.assertEqual(entry.yahoo_symbol("500325.BO"), "500325.BO")
        self.assertEqual(entry.yahoo_symbol("^nsei"), "^NSEI")
        self.assertEqual(entry.chart_path("M&M", "1d", "5m"), "/v8/finance/chart/M%26M.NS?range=1d&interval=5m")


class RealSession(unittest.TestCase):
    def test_triggers_on_the_first_close_above_the_range_high(self):
        r = real("2026-11-12 10:15")
        self.assertEqual(r["status"], "triggered")
        self.assertEqual((r["opens"], r["closes"]), ("09:15", "15:30"))
        self.assertEqual(r["opening_range"]["high"], 1339.4)
        self.assertEqual(r["opening_range"]["low"], 1331.9)
        t = r["trigger"]
        self.assertEqual((t["time"], t["bar_start"], t["price"]), ("9:55 AM", "09:50", 1341.5))

    def test_waits_while_the_bar_is_still_forming(self):
        r = real("2026-11-12 09:40")
        self.assertEqual(r["status"], "waiting")
        self.assertIsNone(r.get("trigger"))

    def test_holiday_is_closed(self):
        r = real("2026-11-10 10:15")
        self.assertIn(r["status"], ("no-data", "closed"))
        self.assertIn("Diwali", r["reason"])

    def test_level_setup(self):
        r = real("2026-11-12 10:15", setup="level", level=1330.0)
        self.assertEqual(r["trigger"]["price"], 1337.4)
        self.assertEqual(r["trigger"]["time"], "9:30 AM")


class Edges(unittest.TestCase):
    def test_a_wick_above_the_high_is_not_a_trigger(self):
        bars = RANGE + [(104, 108, 103, 104, 1000)]       # high 108 > 105, close 104
        self.assertEqual(synth(bars, "2026-11-12 09:50")["status"], "waiting")

    def test_a_close_at_the_high_is_not_a_trigger(self):
        bars = RANGE + [(104, 106, 103, 105, 1000)]       # close == range high 105
        self.assertEqual(synth(bars, "2026-11-12 09:50")["status"], "waiting")

    def test_a_close_above_triggers_at_the_bar_close_time(self):
        bars = RANGE + [(104, 107, 103, 106, 1000)]
        r = synth(bars, "2026-11-12 09:50")
        self.assertEqual(r["status"], "triggered")
        self.assertEqual((r["trigger"]["time"], r["trigger"]["price"]), ("9:35 AM", 106.0))

    def test_a_bar_that_has_not_closed_does_not_count(self):
        bars = RANGE + [(104, 107, 103, 106, 1000)]
        self.assertEqual(synth(bars, "2026-11-12 09:32")["status"], "waiting")   # the 9:30 bar closes 9:35

    def test_the_live_tick_off_the_grid_is_dropped(self):
        text = _synth.chart(DAY, RANGE + [FLAT], live_tick=(4 * 300 + 40, 120.0))
        r = entry.evaluate(entry.parse_chart(text, "DEMO.NS"), now("2026-11-12 09:40"))
        self.assertEqual(r["status"], "waiting")

    def test_expired_after_no_entries_after(self):
        bars = RANGE + [FLAT] * 71                        # 75 bars, never above 105
        r = synth(bars, "2026-11-12 15:10")
        self.assertEqual(r["status"], "expired")
        self.assertEqual(r["no_entries_after"], "15:00")

    def test_min_volume_filter_moves_the_trigger(self):
        bars = RANGE + [(104, 107, 103, 106, 1100), (106, 108, 105, 107, 4000)]
        self.assertEqual(synth(bars, "2026-11-12 10:00")["trigger"]["time"], "9:35 AM")
        r = synth(bars, "2026-11-12 10:00", min_volume_x=2.0)
        self.assertEqual(r["trigger"]["time"], "9:40 AM")

    def test_no_early_close_on_nse(self):
        self.assertEqual(entry.NSE_EARLY_CLOSE, {})


if __name__ == "__main__":
    unittest.main()
