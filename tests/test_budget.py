"""trader-budget tests. margins-equity.json is Zerodha's real public MIS list cut to a few symbols (2026-11-13)."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from _load import load, FIX

size = load("trader-budget", "size")
MARGINS = os.path.join(FIX, "india", "margins-equity.json")
PLAN = {"symbol": "RELIANCE", "side": "buy", "setup": "orb", "date": "2026-11-13", "entry": 1340.0,
        "stop": 1332.05, "target": 1356.0, "flat_by": "15:15"}
CFG = {"budget": 100000}
with open(MARGINS) as _fh:
    M = size.parse_margins(_fh.read())


def s(plan=None, cfg=None, **kw):
    kw.setdefault("margins", M)
    return size.size_trade(plan or PLAN, dict(CFG, **(cfg or {})), **kw)


class Margins(unittest.TestCase):
    def test_zerodha_list_parses(self):
        self.assertEqual(M["RELIANCE"], 20.0)
        self.assertIn("M&M", M)

    def test_rows_without_mis_are_left_out(self):
        got = size.parse_margins(json.dumps([{"tradingsymbol": "A", "mis_margin": 20.0},
                                             {"tradingsymbol": "B", "mis_margin": 0}, {"tradingsymbol": "C"}]))
        self.assertEqual(got, {"A": 20.0})

    def test_bad_answer(self):
        with self.assertRaises(size.SizeError):
            size.parse_margins("<html>")


class Sizing(unittest.TestCase):
    def test_max_loss_binds(self):
        r = s()
        self.assertEqual(r["qty"], 62)               # floor(500 / 7.95)
        self.assertEqual(r["bound_by"], "max loss")
        self.assertEqual(r["max_loss"], 492.9)
        self.assertEqual(r["value"], 83080.0)
        self.assertEqual(r["margin_used"], 16616.0)  # 20% of the value: 5x leverage
        self.assertIsNone(r["refusal"])

    def test_margin_binds_when_funds_are_small(self):
        r = s(cfg={"budget": 10000, "max_loss_per_trade_inr": 5000})
        self.assertEqual(r["bound_by"], "margin")
        self.assertLessEqual(r["margin_used"], 9000)          # budget less the 10% buffer
        self.assertEqual(r["qty"], int(9000 // (1340 * 0.2)))

    def test_symbol_without_mis_is_refused(self):
        with self.assertRaises(size.SizeError) as cm:
            s(dict(PLAN, symbol="NOMIS"))
        self.assertIn("MIS", str(cm.exception))

    def test_margin_pct_override(self):
        r = s(dict(PLAN, symbol="NOMIS"), margin_pct=50, margins={})
        self.assertEqual(r["margin_per_unit"], 670.0)

    def test_prices_sit_on_the_tick(self):
        r = s(limit=1340.03)
        self.assertEqual(r["entry"], 1340.05)
        self.assertEqual(size.round_tick(1332.07, 0.05), 1332.05)
        self.assertEqual(size.round_tick(1332.08, 0.05), 1332.10)

    def test_stop_above_entry_is_refused(self):
        with self.assertRaises(size.SizeError):
            s(dict(PLAN, stop=1341.0))

    def test_reward_risk_under_minimum_is_a_refusal_not_an_order(self):
        r = s(dict(PLAN, target=1341.0))
        self.assertIn("reward:risk", r["refusal"])
        self.assertIsNone(size.order_ticket(r))

    def test_too_wide_a_stop_for_the_max_loss(self):
        r = s(dict(PLAN, stop=1000.0), cfg={"max_loss_per_trade_inr": 100})
        self.assertEqual(r["qty"], 0)
        self.assertIn("max loss", r["refusal"])

    def test_a_plan_for_another_day_is_refused(self):
        with self.assertRaises(size.SizeError):
            s(today="2026-11-16")

    def test_shorts_and_blocked_symbols_are_refused(self):
        with self.assertRaises(size.SizeError):
            s(dict(PLAN, side="sell"))
        with self.assertRaises(size.SizeError):
            s(cfg={"blocked": ["reliance"]})

    def test_fresh_price_above_the_plan_raises_the_risk(self):
        r = s(price=1345.0)
        self.assertEqual(r["entry"], 1345.0)
        self.assertLess(r["qty"], 62)


class FnO(unittest.TestCase):
    def test_options_size_in_lots_and_need_the_premium(self):
        plan = dict(PLAN, symbol="NIFTY26NOV24000CE", entry=100.0, stop=90.0, target=120.0)
        r = s(plan, cfg={"budget": 200000, "max_loss_per_trade_inr": 3000}, segment="options", lot_size=65, margins={})
        self.assertEqual(r["qty"] % 65, 0)
        self.assertEqual(r["qty"], 260)                       # 4 lots: floor(3000 / (10 x 65)) = 4
        self.assertEqual(r["margin_used"], 26000.0)           # the full premium
        self.assertEqual(size.order_ticket(r)["exchange"], "NFO")

    def test_futures_need_the_margin_per_lot(self):
        plan = dict(PLAN, symbol="NIFTY26NOVFUT", entry=24000.0, stop=23950.0, target=24100.0)
        with self.assertRaises(size.SizeError):
            s(plan, segment="futures", lot_size=65, margins={})
        r = s(plan, cfg={"budget": 500000, "max_loss_per_trade_inr": 5000, "max_order_inr": 2000000}, segment="futures", lot_size=65,
              margin_per_lot=180000, margins={})
        self.assertEqual(r["qty"], 65)                        # one lot: 5000 / (50 x 65) = 1.5 lots
        self.assertEqual(r["margin_used"], 180000.0)

    def test_lot_size_is_required(self):
        with self.assertRaises(size.SizeError):
            s(dict(PLAN, symbol="X"), segment="options", margins={})


class Charges(unittest.TestCase):
    def test_equity_intraday_round_trip(self):
        c = size.charges("equity", 83080.0, 82589.1)          # 62 shares: buy at 1340, sell at 1332.05
        self.assertEqual(c["brokerage"], 40.0)                # Rs 20 cap on each leg
        self.assertEqual(c["stt"], 20.65)                     # 0.025% of the sell side
        self.assertEqual(c["stamp"], 2.49)                    # 0.003% of the buy side
        self.assertEqual(c["gst"], round((c["brokerage"] + c["exchange"] + c["sebi"]) * 0.18, 2))
        self.assertAlmostEqual(c["total"], 76.55, places=2)

    def test_brokerage_is_the_lower_of_20_and_0_03_percent(self):
        c = size.charges("equity", 10000.0, 10000.0)
        self.assertEqual(c["brokerage"], 6.0)                 # 0.03% of 10,000 is 3 a leg

    def test_options_brokerage_is_flat_20_a_leg(self):
        c = size.charges("options", 26000.0, 30000.0)
        self.assertEqual(c["brokerage"], 40.0)
        self.assertEqual(c["stt"], 45.0)                      # 0.15% of the sell premium

    def test_futures_stt_is_on_the_sell_side(self):
        c = size.charges("futures", 1560000.0, 1560000.0)
        self.assertEqual(c["stt"], 780.0)                     # 0.05%


class Format(unittest.TestCase):
    def test_lakh_grouping(self):
        self.assertEqual(size.money(1250000), "₹12,50,000")
        self.assertEqual(size.money(492.9), "₹492.90")
        self.assertEqual(size.money(100000), "₹1,00,000")
        self.assertEqual(size._group("-12345.67"), "-12,345.67")

    def test_no_dollar_signs_in_a_report(self):
        r = s()
        text = size.plan_report(r, size.order_ticket(r))
        self.assertNotIn("$", text)
        self.assertIn("Kite", text)
        self.assertIn("Zerodha charges", text)


class Ticket(unittest.TestCase):
    def test_ticket_is_kite_shaped(self):
        o = size.order_ticket(s())
        self.assertEqual((o["exchange"], o["product"], o["type"], o["validity"], o["side"]), ("NSE", "MIS", "market", "DAY", "BUY"))
        self.assertEqual((o["qty"], o["stop_loss_trigger"], o["target_price"], o["margin_required"]), (62, "1332.05", "1356.00", 16616.0))
        self.assertNotIn("bracket", json.dumps(o).lower())

    def test_limit_ticket_carries_a_price(self):
        self.assertEqual(size.order_ticket(s(limit=1339.5))["price"], "1339.50")


class Cli(unittest.TestCase):
    def test_write_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            plan, cfg, out = (os.path.join(d, n) for n in ("plan.json", "config.json", "orders.json"))
            for path, doc in ((plan, PLAN), (cfg, CFG)):
                with open(path, "w") as fh:
                    json.dump(doc, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = size.main(["--plan", plan, "--config", cfg, "--margins", MARGINS, "--write", out,
                                "--now", "2026-11-13 10:00"])
            self.assertEqual(rc, 0, buf.getvalue())
            with open(out) as fh:
                doc = json.load(fh)
            self.assertEqual(doc["broker"], "zerodha")
            self.assertEqual(doc["orders"][0]["qty"], 62)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(size.main(["--plan", plan, "--config", cfg, "--margins", MARGINS,
                                            "--now", "2026-11-16 10:00"]), 1)
            self.assertIn("2026-11-13", err.getvalue())


if __name__ == "__main__":
    unittest.main()
