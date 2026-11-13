"""trader-scanner tests. EQUITY_L.csv and margins-equity.json are cut from NSE's and Zerodha's real files (2026-11-13);
_synth.py builds exact bars."""

import contextlib
import datetime
import io
import json
import os
import shutil
import tempfile
import unittest

from _load import load, FIX
import _synth

scan = load("trader-scanner", "scan")
IN = os.path.join(FIX, "india")
DAY = datetime.date(2026, 11, 12)


def read(name):
    with open(os.path.join(IN, name), encoding="utf-8") as fh:
        return fh.read()


def day_series(closes_by_slot, highs=None):
    """A v8 series for DAY with one bar per slot from 9:15."""
    bars = []
    for i, c in enumerate(closes_by_slot):
        h = (highs or {}).get(i, c + 0.5)
        bars.append((c, h, c - 0.5, c, 1000))
    return scan.parse_chart(_synth.chart(DAY, bars), "DEMO")


def cutoff(text):
    return datetime.datetime.strptime("2026-11-12 " + text, "%Y-%m-%d %H:%M")


class Universe(unittest.TestCase):
    def build(self):
        return scan.build_universe({"EQUITY_L.csv": read("EQUITY_L.csv"), "margins-equity.json": read("margins-equity.json")})

    def test_keeps_eq_series_with_mis_at_zerodha(self):
        kept, counts = self.build()
        syms = [k for k, _ in kept]
        self.assertEqual(syms, ["BAJAJ-AUTO", "HDFCBANK", "INFY", "M&M", "RELIANCE", "SBIN", "TCS"])
        self.assertEqual(counts["not EQ series"], 1)        # a BE (trade-for-trade) row
        self.assertEqual(counts["no MIS at Zerodha"], 1)    # an EQ row Zerodha gives no MIS on
        self.assertEqual(dict(kept)["RELIANCE"], "Reliance Industries Limited")

    def test_classify(self):
        mis = {"A": 20.0}
        self.assertEqual(scan.classify({"SYMBOL": "A", "SERIES": "EQ"}, mis), "keep")
        self.assertEqual(scan.classify({"SYMBOL": "A", "SERIES": "BE"}, mis), "not EQ series")
        self.assertEqual(scan.classify({"SYMBOL": "A", "SERIES": "SM"}, mis), "not EQ series")
        self.assertEqual(scan.classify({"SYMBOL": "B", "SERIES": "EQ"}, mis), "no MIS at Zerodha")
        self.assertEqual(scan.classify({"SYMBOL": "A B", "SERIES": "EQ"}, mis), "not a plain ticker")

    def test_header_with_spaces_and_bad_files(self):
        rows = scan.parse_equity_l(read("EQUITY_L.csv"))
        self.assertEqual(rows[0]["SERIES"], "EQ")
        with self.assertRaises(scan.ScanError):
            scan.parse_equity_l("<html>")
        with self.assertRaises(scan.ScanError):
            scan.parse_mis("<html>")

    def test_universe_command_offline_writes_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("EQUITY_L.csv", "margins-equity.json"):
                shutil.copy(os.path.join(IN, n), d)
            out = os.path.join(d, "universe.txt")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = scan.main(["universe", "--offline", d, "--out", out])
            self.assertEqual(rc, 0, buf.getvalue())
            with open(out) as fh:
                self.assertIn("M&M|Mahindra & Mahindra Limited", fh.read())
        self.assertIn("NSE EQ-series stocks you can trade intraday on Zerodha", buf.getvalue())

    def test_missing_file_is_a_scan_error(self):
        with self.assertRaises(scan.ScanError):
            scan.build_universe({"EQUITY_L.csv": read("EQUITY_L.csv")})


class Symbols(unittest.TestCase):
    def test_yahoo_mapping_and_spark_path(self):
        self.assertEqual(scan.to_yahoo("reliance"), "RELIANCE.NS")
        self.assertEqual(scan.to_yahoo("BAJAJ-AUTO"), "BAJAJ-AUTO.NS")
        self.assertIn("symbols=RELIANCE.NS,M%26M.NS,", scan.spark_path(["RELIANCE", "M&M", "X"], "1d", "5m") + ",")

    def test_spark_answer_maps_back_to_our_symbols(self):
        doc = {"spark": {"result": [{"symbol": "RELIANCE.NS", "response": [{"meta": {"regularMarketPrice": 1340},
               "timestamp": [1], "indicators": {"quote": [{"close": [1340.0]}]}}]}], "error": None}}
        self.assertEqual(list(scan.parse_spark(doc)), ["RELIANCE"])
        self.assertEqual(list(scan.parse_spark(doc, {"RELIANCE.NS": "RELIANCE"})), ["RELIANCE"])


class Orb(unittest.TestCase):
    def test_session_is_75_bars_and_starts_at_9_15(self):
        s = day_series([100] * 75)
        bars = scan.session_bars(s, DAY, cutoff("15:30"))
        self.assertEqual(len(bars), 75)
        self.assertEqual(bars[0]["start"], cutoff("09:15"))
        self.assertEqual(bars[-1]["start"], cutoff("15:25"))

    def test_a_bar_counts_only_when_complete_at_the_cutoff(self):
        s = day_series([100] * 75)
        self.assertEqual(len(scan.session_bars(s, DAY, cutoff("10:15"))), 12)     # 9:15..10:10 close by 10:15

    def test_usable_needs_every_slot(self):
        s = day_series([100] * 75)
        bars = scan.session_bars(s, DAY, cutoff("10:15"))
        self.assertTrue(scan.usable(bars, DAY, cutoff("10:15"), 3))
        self.assertFalse(scan.usable(bars[:5] + bars[6:], DAY, cutoff("10:15"), 3))   # a no-trade slot

    def test_a_null_bar_makes_a_chart_unusable_not_a_crash(self):
        bars = [(100, 101, 99, 100, 10)] * 12
        bars[5] = None
        s = scan.parse_chart(_synth.chart(DAY, bars), "DEMO")
        self.assertFalse(scan.usable(scan.session_bars(s, DAY, cutoff("10:15")), DAY, cutoff("10:15"), 3))

    def test_hit_is_the_first_close_above_the_range_high(self):
        closes = [100, 101, 100, 100, 101, 106, 107, 108, 108, 108, 108, 108]
        s = day_series(closes, highs={0: 101, 1: 102, 2: 101})
        bars = scan.session_bars(s, DAY, cutoff("10:15"))
        self.assertTrue(scan.orb_candidate(bars, 3))
        h = scan.orb_hit(bars, 3)
        self.assertEqual((h["price"], h["bar_start"], h["at"]), (106.0, "09:40", "9:45 AM"))
        self.assertEqual((h["or_high"], h["or_low"]), (102.0, 99.5))

    def test_a_wick_is_not_a_hit(self):
        closes = [100, 101, 100, 100, 101, 101, 101, 101, 101, 101, 101, 101]
        s = day_series(closes, highs={5: 120})
        self.assertIsNone(scan.orb_hit(scan.session_bars(s, DAY, cutoff("10:15")), 3))

    def test_window_messages_are_ist_and_9_15(self):
        now = scan.ist_to_utc(cutoff("09:20"))
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(now, None, 15, None, DAY)
        self.assertIn("IST", str(cm.exception))
        self.assertIn("9:15", str(cm.exception))
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(scan.ist_to_utc(datetime.datetime(2026, 11, 10, 10, 0)), None, 15, None, datetime.date(2026, 11, 10))
        self.assertIn("Diwali", str(cm.exception))
        day, cut = scan.orb_window(scan.ist_to_utc(cutoff("10:20")), None, 15, datetime.time(15, 0), DAY)
        self.assertEqual((day, cut), (DAY, cutoff("10:20")))

    def test_scan_orb_end_to_end_on_synthetic_stage1_data(self):
        win = day_series([100, 101, 100, 100, 101, 106, 107, 108, 108, 108, 108, 108], {0: 101, 1: 102, 2: 101})
        flat = day_series([100] * 12)
        hits, counts, failed = scan.scan_orb({"WIN": win, "FLAT": flat}, ["WIN", "FLAT"], DAY, cutoff("10:15"), 15)
        self.assertEqual([h["symbol"] for h in hits], ["WIN"])
        self.assertEqual((counts["scanned"], counts["candidates"], counts["hits"]), (2, 2, 1))   # a flat chart is a stage-1 candidate, never a hit


class Daily(unittest.TestCase):
    def test_default_floors_are_rupee_floors(self):
        import argparse
        ap_defaults = {}
        old = scan.cmd_daily
        try:
            scan.cmd_daily = lambda a: ap_defaults.update(vars(a)) or 0
            scan.main(["daily"])
        finally:
            scan.cmd_daily = old
        self.assertEqual((ap_defaults["min_price"], ap_defaults["min_volume"]), (50.0, 500000))

    def test_setups_from_closes(self):
        closes = [100 + i * 0.2 for i in range(60)] + [125]
        tags, _ = scan.find_setups(closes)
        self.assertIn("breakout_20d", tags)


if __name__ == "__main__":
    unittest.main()
