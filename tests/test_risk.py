"""trader-risk tests on Kite tickets (the shape trader-budget writes)."""

import contextlib
import copy
import datetime
import io
import json
import os
import tempfile
import unittest

from _load import load

check = load("trader-risk", "check")
CFG = {"budget": 100000}
NOW = datetime.datetime(2026, 11, 13, 4, 30)      # 10:00 IST, a Friday
BASE = {"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "qty": 62, "product": "MIS", "type": "market",
        "validity": "DAY", "stop_loss_trigger": "1332.05", "target_price": "1356.00", "segment": "equity",
        "lot_size": 1, "tick": 0.05, "margin_required": 16616.0,
        "plan": {"entry": 1340.0, "stop": 1332.05, "target": 1356.0, "flat_by": "15:15"}}


def run(order=None, cfg=None, now=NOW, state=None, portfolio=None, prices=None):
    orders = order if isinstance(order, list) else [order or copy.deepcopy(BASE)]
    return check.check(orders, dict(CFG, **(cfg or {})), portfolio, prices, state, None, now)


def reasons(res, i=0):
    return " | ".join(res["results"][i]["reasons"])


class Pass(unittest.TestCase):
    def test_a_clean_ticket_passes_with_the_numbers(self):
        r = run()
        x = r["results"][0]
        self.assertEqual((r["pass"], r["block"], x["kind"]), (1, 0, "entry"))
        self.assertEqual((x["max_loss"], x["reward_risk"], x["risk_per_share"]), (492.9, 2.01, 7.95))
        self.assertEqual(r["now_ist"], "2026-11-13 10:00")
        self.assertEqual(r["cash_after"], 100000 - 16616)

    def test_report_is_rupees_and_says_kite(self):
        text = check.report(run())
        self.assertNotIn("$", text)
        self.assertIn("Kite", text)
        self.assertIn("₹492.90", text)


class Format(unittest.TestCase):
    def test_product_must_be_mis(self):
        o = dict(BASE, product="CNC")
        self.assertIn("intraday only", reasons(run(o)))

    def test_price_off_the_tick(self):
        o = dict(BASE, stop_loss_trigger="1332.07")
        self.assertIn("tick", reasons(run(o)))

    def test_qty_whole_and_lot_multiple(self):
        self.assertIn("whole number", reasons(run(dict(BASE, qty=1.5))))
        fno = dict(BASE, symbol="NIFTY26NOVFUT", exchange="NFO", segment="futures", lot_size=65, qty=100)
        self.assertIn("lots", reasons(run(fno)))

    def test_limit_needs_a_price(self):
        self.assertIn("needs a price", reasons(run(dict(BASE, type="limit"))))

    def test_unknown_exchange_and_symbol(self):
        self.assertIn("NSE and NFO only", reasons(run(dict(BASE, exchange="MCX"))))
        self.assertIn("trading symbol", reasons(run(dict(BASE, symbol="reliance industries"))))

    def test_fno_can_be_switched_off(self):
        fno = dict(BASE, symbol="NIFTY26NOV24000CE", exchange="NFO", segment="options", lot_size=65, qty=65)
        self.assertIn("F&O is off", reasons(run(fno, {"allow_fno": False})))

    def test_symbols_with_ampersand_and_dash_are_fine(self):
        for sym in ("M&M", "BAJAJ-AUTO", "360ONE"):
            self.assertEqual(run(dict(BASE, symbol=sym))["block"], 0, sym)


class Limits(unittest.TestCase):
    def test_loss_over_the_max(self):
        self.assertIn("loss:", reasons(run(dict(BASE, qty=100))))

    def test_stop_required_and_on_the_right_side(self):
        o = copy.deepcopy(BASE)
        del o["stop_loss_trigger"]
        del o["plan"]["stop"]
        self.assertIn("stop: no stop", reasons(run(o)))
        self.assertIn("must be below", reasons(run(dict(BASE, stop_loss_trigger="1345.00"))))

    def test_reward_risk(self):
        o = dict(BASE, target_price="1341.00")
        o["plan"] = dict(BASE["plan"], target=1341.0)
        self.assertIn("reward:risk", reasons(run(o)))

    def test_margin_over_funds(self):
        r = run(dict(BASE, margin_required=95000.0))
        self.assertIn("margin:", reasons(r))

    def test_no_margin_figure_is_a_warning_not_a_block(self):
        o = copy.deepcopy(BASE)
        del o["margin_required"]
        r = run(o)
        self.assertEqual(r["block"], 0)
        self.assertTrue(any("margin_required" in w for w in r["results"][0]["warnings"]))

    def test_position_cap_is_on_value_and_allows_leverage(self):
        self.assertEqual(run()["block"], 0)                                  # Rs 83,080 on a Rs 1,00,000 budget
        self.assertIn("position:", reasons(run(cfg={"max_position_pct": 50})))

    def test_second_entry_in_the_batch_is_checked_after_the_first(self):
        b = dict(BASE, symbol="SBIN", plan=dict(BASE["plan"]), margin_required=16616.0)
        r = run([copy.deepcopy(BASE), b], {"max_daily_loss_inr": 700})
        self.assertEqual([x["verdict"] for x in r["results"]], ["PASS", "BLOCK"])
        self.assertIn("daily loss", reasons(r, 1))

    def test_duplicate_in_batch(self):
        r = run([copy.deepcopy(BASE), copy.deepcopy(BASE)])
        self.assertIn("duplicate", reasons(r, 1))

    def test_blocked_list(self):
        self.assertIn("blocked", reasons(run(cfg={"blocked": ["RELIANCE"]})))

    def test_there_is_no_pdt_rule(self):
        state = {"orders": [{"status": "filled", "date": "2026-11-12", "symbol": s, "side": side}
                            for s in "ABCD" for side in ("buy", "sell")]}
        self.assertEqual(run(state=state, cfg={"pdt_guard": True})["block"], 0)


class Window(unittest.TestCase):
    def at(self, ist):
        return check.ist_to_utc(datetime.datetime.strptime(ist, "%Y-%m-%d %H:%M"))

    def test_before_09_30_and_after_15_00(self):
        self.assertIn("before 09:30", reasons(run(now=self.at("2026-11-13 09:20"))))
        self.assertIn("after 15:00", reasons(run(now=self.at("2026-11-13 15:10"))))
        self.assertEqual(run(now=self.at("2026-11-13 14:59"))["block"], 0)

    def test_market_closed_outside_the_session(self):
        self.assertIn("market is closed", reasons(run(now=self.at("2026-11-13 15:45"))))
        self.assertIn("market is closed", reasons(run(now=self.at("2026-11-13 09:00"))))

    def test_holiday_and_weekend(self):
        self.assertIn("Diwali", reasons(run(now=self.at("2026-11-10 10:00"))))
        self.assertIn("weekend", reasons(run(now=self.at("2026-11-14 10:00"))))

    def test_calendar_year_warning(self):
        r = run(now=self.at("2027-01-05 10:00"))
        self.assertTrue(any("2026 only" in w for w in r["warnings"]))


class Exits(unittest.TestCase):
    def test_an_exit_is_never_blocked_by_the_window(self):
        pf = {"cash": 50000, "positions": [{"symbol": "RELIANCE", "qty": 62}]}
        sell = {"symbol": "RELIANCE", "exchange": "NSE", "side": "SELL", "qty": 62, "product": "MIS", "type": "market",
                "validity": "DAY", "tick": 0.05}
        r = run(sell, now=check.ist_to_utc(datetime.datetime(2026, 11, 13, 15, 20)), portfolio=pf)
        self.assertEqual((r["results"][0]["kind"], r["block"]), ("exit", 0))

    def test_a_short_is_blocked(self):
        sell = {"symbol": "SBIN", "exchange": "NSE", "side": "SELL", "qty": 10, "product": "MIS", "type": "market",
                "validity": "DAY", "tick": 0.05, "plan": {"entry": 800}}
        self.assertIn("short", reasons(run(sell, prices={"SBIN": 800.0})))


class Daily(unittest.TestCase):
    def test_trades_and_orders_per_day_and_duplicates_from_the_log(self):
        placed = [{"status": "placed", "date": "2026-11-13", "symbol": s, "side": "buy", "kind": "entry", "max_loss": 100}
                  for s in ("A", "B", "C")]
        self.assertIn("trades:", reasons(run(state={"orders": placed})))
        again = [{"status": "placed", "date": "2026-11-13", "symbol": "RELIANCE", "side": "buy", "kind": "entry",
                  "max_loss": 100}]
        self.assertIn("already placed", reasons(run(state={"orders": again})))
        self.assertEqual(run(state={"orders": [dict(again[0], date="2026-11-12")]})["block"], 0)

    def test_fingerprint_changes_with_the_order(self):
        a, b = copy.deepcopy(BASE), dict(BASE, qty=61)
        self.assertNotEqual(check.fingerprint(a), check.fingerprint(b))
        self.assertEqual(check.fingerprint(a), check.fingerprint(copy.deepcopy(a)))


class Cli(unittest.TestCase):
    def test_writes_the_verdicts_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            orders, cfg, out = (os.path.join(d, n) for n in ("orders.json", "config.json", "risk.json"))
            with open(orders, "w") as fh:
                json.dump({"orders": [BASE]}, fh)
            with open(cfg, "w") as fh:
                json.dump(CFG, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = check.main(["--orders", orders, "--config", cfg, "--out", out, "--now", "2026-11-13 10:00",
                                 "--portfolio", os.path.join(d, "none"), "--prices", os.path.join(d, "none"),
                                 "--state", os.path.join(d, "none")])
            self.assertEqual(rc, 0, buf.getvalue())
            with open(out) as fh:
                rec = json.load(fh)
            self.assertEqual(rec["results"][0]["fingerprint"], check.fingerprint(BASE))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check.main(["--orders", orders, "--config", cfg, "--no-write", "--now",
                                             "2026-11-13 15:10", "--portfolio", os.path.join(d, "none"),
                                             "--prices", os.path.join(d, "none"), "--state", os.path.join(d, "none")]), 1)


if __name__ == "__main__":
    unittest.main()
