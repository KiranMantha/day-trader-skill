#!/usr/bin/env python3
"""Position sizing for trader-budget, for Zerodha intraday on NSE. Standard library only.

Sizes ONE day trade from trader/plan.json (written by trader-exit) to your
budget and your max loss per trade, and writes one order ticket to
trader/orders.json. It never places anything: trader-risk checks the ticket
and you key it into the Kite app yourself.

    python3 size.py                                  # trader/plan.json + trader/config.json
    python3 size.py --write                          # write trader/orders.json
    python3 size.py --limit                          # a limit order at the plan's entry
    python3 size.py --limit 1342.50 --write          # a limit order at 1342.50
    python3 size.py --now "2026-11-16 10:15" --json  # pin the clock (IST)
    python3 size.py --segment futures --lot-size 65 --margin-per-lot 180000   # a futures lot
    python3 size.py --segment options --lot-size 65                           # a long option

Intraday only (Zerodha product MIS). The margin Zerodha asks is the only
"cash" this tool knows: equity MIS leverage comes from Zerodha's public list
(https://api.kite.trade/margins/equity: mis_margin is the percent of the trade
value Kite blocks, 20 = 5x). --margins FILE reads a saved copy; --margin-pct
overrides it. A symbol missing from the list has no MIS: no order.

How many shares (or lots). Whole units only; F&O in whole lots.

    qty = floor of the smallest of
      max loss       max_loss_per_trade_inr / risk per share (entry minus stop)
      position cap   budget x max_position_pct (of trade VALUE) / entry
      max order      max_order_inr / entry
      margin         (budget minus the buffer) / margin per share

Margin per share: equity = entry x mis_margin%; a long option = the full
premium (a bought option needs no more); a future = --margin-per-lot / lot
size, read off Kite's order window (the SPAN margin changes daily and this
tool does not guess it).

Prices sit on the exchange tick (Rs 0.05 for NSE stocks and options, change it
with "tick" in the plan or --tick): Kite rejects any other price.

Round-trip charges use Zerodha's published schedule (zerodha.com/charges):
brokerage, STT, exchange charges, SEBI fee, stamp duty and 18% GST. They are
shown at the stop and at the target and are NOT part of the sizing; your max
loss per trade is the gross move. Zerodha's own calculator is the reference.
"""

import argparse
import datetime
import json
import math
import os
import re
import sys
import urllib.request

DEFAULTS = {
    "budget": None,
    "cash_buffer_pct": 10,
    "max_position_pct": 500,
    "max_order_inr": 500000,
    "min_order_inr": 1000,
    "max_loss_per_trade_inr": 500,
    "max_daily_loss_inr": 1500,
    "max_trades_per_day": 3,
    "max_orders_per_day": 10,
    "min_reward_risk": 1.0,
    "require_stop": True,
    "no_entries_before": "09:30",
    "no_entries_after": "15:00",
    "flat_by": "15:15",
    "broker": "zerodha",
    "product": "MIS",
    "tick": 0.05,
    "blocked": [],
    "allow_fno": True,
    "allow_short": False,
}
EPS = 1e-9
FRESH_MINUTES = 15
MARGINS_URL = "https://api.kite.trade/margins/equity"
SEGMENTS = ("equity", "futures", "options")
SETUP_WORDS = {"orb": "opening-range breakout", "flag": "flag", "bounce": "oversold bounce"}


class SizeError(Exception):
    pass


# ---------------------------------------------------------------- time (IST, no tz files)

IST = 19800  # seconds ahead of UTC: India has no daylight saving


def to_ist(utc):
    return utc.replace(tzinfo=None) + datetime.timedelta(seconds=IST)


def ist_to_utc(local):
    return local - datetime.timedelta(seconds=IST)


def parse_now(text):
    """ISO time -> naive UTC. A time without an offset is taken as IST."""
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise SizeError("--now wants a time like \"2026-10-19 10:15\" (IST) or ...Z (UTC)")
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def parse_utc(text):
    """"2026-10-19T14:52:13Z" -> naive UTC, or None."""
    if not text:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = (dt - dt.utcoffset()).replace(tzinfo=None)
    return dt


def utc_iso(now_utc=None):
    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return now_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- inputs

def read_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise SizeError("no %s at %s" % (what, path))
    except json.JSONDecodeError as e:
        raise SizeError("%s is not valid JSON: %s" % (path, e))


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.exists(path):
        cfg.update(read_json(path, "config"))
    return cfg


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_prices(path):
    if not path:
        return {}
    data = read_json(path, "prices")
    prices = data.get("prices", data) if isinstance(data, dict) else {}
    out = {}
    for t, p in prices.items():
        try:
            out[str(t).upper()] = float(p)
        except (TypeError, ValueError):
            continue
    return out


def price_time(doc, sym):
    """When this symbol's price is from: the quote's own time (detail[sym].time), else when it
    was fetched (detail[sym].fetched), else the file's as_of."""
    det = ((doc or {}).get("detail") or {}).get(sym) or {}
    for key in ("time", "fetched"):
        t = parse_utc(det.get(key))
        if t:
            return t
    return parse_utc((doc or {}).get("as_of"))


def fresh_price(doc, sym, now_utc, minutes=FRESH_MINUTES):
    """(price, fetched_utc, fresh) for sym from a prices.json doc, or (None, None, False)."""
    if not isinstance(doc, dict):
        return None, None, False
    p = _f((doc.get("prices") or {}).get(sym))
    if p is None or p <= 0:
        return None, None, False
    t = price_time(doc, sym)
    if t is None:
        return p, None, False
    age = (now_utc - t).total_seconds()
    return p, t, -60 <= age <= minutes * 60



# ---------------------------------------------------------------- money helpers

def round_tick(x, tick):
    """Round a price to the exchange tick (half up). Exact in integer paise."""
    t = max(int(round(float(tick) * 100)), 1)
    return (int(math.floor(float(x) * 100 / t + 0.5 + EPS)) * t) / 100.0


def units_for(inr, per_unit):
    """Whole units that fit in inr at per_unit, in exact integer paise."""
    u, p = int(round(float(inr) * 100)), int(round(float(per_unit) * 100))
    if p <= 0 or u <= 0:
        return 0
    return u // p


def _price(x):
    return "%.2f" % round(float(x) + EPS, 2)


def _num(x):
    x = round(float(x), 2)
    if abs(x - round(x)) < 0.005:
        return str(int(round(x)))
    return "%.2f" % x


def _group(s):
    """'1234567.5' -> '12,34,567.5': lakh and crore grouping, like the Kite app."""
    neg, s = s.startswith("-"), s.lstrip("-")
    i, dot, f = s.partition(".")
    head, tail = i[:-3], i[-3:]
    if head:
        head = ",".join(reversed([head[max(0, k - 2):k] for k in range(len(head), 0, -2)]))
        tail = head + "," + tail
    return ("-" if neg else "") + tail + dot + f


def money(x):
    x = float(x)
    if abs(x - round(x)) < 0.005:
        return "₹" + _group("{:.0f}".format(round(x)))
    return "₹" + _group("{:.2f}".format(x))



# ---------------------------------------------------------------- Zerodha charges (zerodha.com/charges, read 2026-11-13)

CHARGE_RATES = {   # percent of turnover unless noted; NSE exchange charges
    "equity":  {"brok_pct": 0.03, "brok_cap": 20.0, "stt_sell": 0.025, "txn": 0.00307, "stamp_buy": 0.003},
    "futures": {"brok_pct": 0.03, "brok_cap": 20.0, "stt_sell": 0.05, "txn": 0.00183, "stamp_buy": 0.002},
    "options": {"brok_pct": None, "brok_cap": 20.0, "stt_sell": 0.15, "txn": 0.03553, "stamp_buy": 0.003},
}
SEBI_PER_CRORE = 10.0
GST_PCT = 18.0


def charges(segment, buy_value, sell_value):
    """Zerodha's intraday round trip (one buy, one sell) -> dict of rupees. Options use the premium."""
    r = CHARGE_RATES[segment]

    def brok(v):
        return r["brok_cap"] if r["brok_pct"] is None else min(r["brok_cap"], v * r["brok_pct"] / 100.0)
    turnover = buy_value + sell_value
    out = {"brokerage": brok(buy_value) + brok(sell_value),
           "stt": sell_value * r["stt_sell"] / 100.0,
           "exchange": turnover * r["txn"] / 100.0,
           "sebi": turnover * SEBI_PER_CRORE / 1e7,
           "stamp": buy_value * r["stamp_buy"] / 100.0}
    out["gst"] = (out["brokerage"] + out["exchange"] + out["sebi"]) * GST_PCT / 100.0
    out = {k: round(v, 2) for k, v in out.items()}
    out["total"] = round(sum(out.values()), 2)
    return out


# ---------------------------------------------------------------- Zerodha equity MIS margins

def parse_margins(text):
    """api.kite.trade/margins/equity JSON -> {SYMBOL: mis_margin percent}. Rows without MIS are left out."""
    try:
        rows = json.loads(text)
    except ValueError as e:
        raise SizeError("the Zerodha margin list is not JSON: %s" % e)
    if not isinstance(rows, list):
        raise SizeError("the Zerodha margin list is not a list")
    out = {}
    for r in rows:
        pct = _f(r.get("mis_margin")) if isinstance(r, dict) else None
        if pct and pct > 0:
            out[str(r.get("tradingsymbol", "")).upper()] = pct
    return out


def load_margins(path=None, fetch=None):
    """--margins FILE, else Zerodha's public list. Cached per IST day in trader/state/zerodha-margins.json."""
    if path:
        with open(path, encoding="utf-8") as fh:
            return parse_margins(fh.read())
    fetch = fetch or _http_get
    return parse_margins(fetch(MARGINS_URL))


def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; day-trader-skill/3.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except OSError as e:
        raise SizeError("could not read Zerodha's margin list (%s). Save it from %s and pass --margins FILE, "
                        "or pass --margin-pct (the 20 in a 5x stock)" % (e, MARGINS_URL))


# ---------------------------------------------------------------- sizing

def size_trade(plan, cfg, budget=None, limit=None, price=None, today=None, margins=None,
               segment=None, lot_size=None, margin_per_lot=None, margin_pct=None, tick=None):
    """Pure function: one plan + your rules -> the sizing (a dict). qty may be 0.

    limit    the limit price (None = market)
    price    a FRESH latest price; a market order is sized at the higher of it and the plan's entry
    today    IST date (YYYY-MM-DD); a plan for another day is refused
    margins  {SYMBOL: mis_margin percent} from Zerodha (equity only)
    segment  equity (default), futures or options; F&O sizes in whole lots (lot_size)"""
    c = dict(DEFAULTS)
    c.update(cfg or {})
    if not isinstance(plan, dict):
        raise SizeError("the plan is not a JSON object")
    sym = str(plan.get("symbol") or "").strip().upper()
    if not sym:
        raise SizeError("the plan has no symbol (run trader-exit)")
    side = str(plan.get("side") or "buy").strip().lower()
    if side != "buy":
        raise SizeError("this pack sizes long (buy) day trades only; the plan says %r" % side)
    if today and plan.get("date") and str(plan["date"]) != today:
        raise SizeError("the plan is for %s and today is %s in IST: make a new plan with trader-exit"
                        % (plan["date"], today))
    segment = str(segment or plan.get("segment") or "equity").lower()
    if segment not in SEGMENTS:
        raise SizeError("segment must be one of %s, not %r" % (", ".join(SEGMENTS), segment))
    lot = 1
    if segment != "equity":
        lot = int(_f(lot_size if lot_size is not None else plan.get("lot_size")) or 0)
        if lot < 1:
            raise SizeError("%s needs the lot size: --lot-size N (Kite shows it in the order window)" % segment)
    tk = _f(tick if tick is not None else (plan.get("tick") or c.get("tick"))) or 0.05
    entry_plan, stop, target = (_f(plan.get(k)) for k in ("entry", "stop", "target"))
    for name, v in (("entry", entry_plan), ("stop", stop), ("target", target)):
        if v is None or v <= 0:
            raise SizeError("the plan needs a positive %s (run trader-exit)" % name)
    if sym in {str(b).upper() for b in (c.get("blocked") or [])}:
        raise SizeError("%s is on your blocked list" % sym)

    budget = float(budget if budget is not None else (c.get("budget") or 0))
    if budget <= 0:
        raise SizeError("no budget: pass --budget or set \"budget\" in trader/config.json (the margin in your Kite account)")
    buf_pct = float(c.get("cash_buffer_pct") or 0)
    if not 0 <= buf_pct < 100:
        raise SizeError("cash_buffer_pct must be between 0 and 100")

    if limit is not None:
        ref, ref_from = round_tick(limit, tk), "limit"
    elif price is not None and round_tick(price, tk) > round_tick(entry_plan, tk):
        ref, ref_from = round_tick(price, tk), "price"
    else:
        ref, ref_from = round_tick(entry_plan, tk), "plan"
    stop, target = round_tick(stop, tk), round_tick(target, tk)
    if stop >= ref:
        raise SizeError("the stop %s is not below the entry %s; a long trade needs its stop underneath"
                        % (_price(stop), _price(ref)))
    if target <= ref:
        raise SizeError("the target %s is not above the entry %s: the move has already happened. "
                        "Skip it or make a new plan with trader-exit" % (_price(target), _price(ref)))
    risk_p = int(round((ref - stop) * 100))
    reward_p = int(round((target - ref) * 100))
    risk = risk_p / 100.0

    # margin Kite blocks per unit (share, or one unit of a lot)
    mis_pct = None
    if segment == "equity":
        mis_pct = margin_pct if margin_pct is not None else (margins or {}).get(sym)
        if not mis_pct or mis_pct <= 0:
            raise SizeError("%s is not in Zerodha's MIS list, so it cannot be traded intraday on margin "
                            "(or pass --margin-pct)" % sym)
        margin_unit, margin_how = ref * mis_pct / 100.0, "%s MIS margin %s%%" % (sym, _num(mis_pct))
    elif segment == "options":
        margin_unit, margin_how = ref, "the full premium (a bought option)"
    else:
        mpl = _f(margin_per_lot)
        if not mpl or mpl <= 0:
            raise SizeError("futures need --margin-per-lot: the margin Kite shows for one lot")
        margin_unit, margin_how = mpl / lot, "%s per lot" % money(mpl)

    margin_buffer = round(budget * buf_pct / 100.0, 2)
    available = max(round(budget - margin_buffer, 2), 0.0)

    def lots(inr, per_unit):
        return (units_for(inr, per_unit) // lot) * lot

    limits = []
    max_loss = _f(c.get("max_loss_per_trade_inr"))
    if max_loss:
        limits.append({"name": "max loss", "inr": max_loss, "per": risk, "units": lots(max_loss, risk),
                       "how": "%s max loss / %s risk a share" % (money(max_loss), _price(risk))})
    cap_pct = _f(c.get("max_position_pct"))
    if cap_pct:
        cap = round(budget * cap_pct / 100.0, 2)
        limits.append({"name": "position cap", "inr": cap, "per": ref, "units": lots(cap, ref),
                       "how": "%s%% of %s = %s / %s" % (_num(cap_pct), money(budget), money(cap), _price(ref))})
    max_order = _f(c.get("max_order_inr"))
    if max_order:
        limits.append({"name": "max order", "inr": max_order, "per": ref, "units": lots(max_order, ref),
                       "how": "%s / %s" % (money(max_order), _price(ref))})
    limits.append({"name": "margin", "inr": available, "per": margin_unit, "units": lots(available, margin_unit),
                   "how": "budget %s minus %s buffer = %s / %s (%s)" % (
                       money(budget), money(margin_buffer), money(available), money(margin_unit), margin_how)})

    qty = max(0, min(l["units"] for l in limits))
    bound = [l["name"] for l in limits if l["units"] == qty]
    for l in limits:
        l["binds"] = l["name"] == bound[0]
    value = round(qty * ref, 2)
    loss = round(qty * risk_p / 100.0, 2)
    gain = round(qty * reward_p / 100.0, 2)
    ch_stop = charges(segment, qty * ref, qty * stop) if qty else None
    ch_target = charges(segment, qty * ref, qty * target) if qty else None
    unit = "share" if segment == "equity" else "unit"
    refusal = None
    if qty == 0:
        if bound[0] == "max loss":
            refusal = ("one %s risks %s (entry %s minus stop %s)%s, more than your %s max loss per trade. "
                       "No order. Skip this trade, or plan a closer stop with trader-exit."
                       % (unit if lot == 1 else "lot", money(risk * lot), _price(ref), _price(stop),
                          "" if lot == 1 else " x %d" % lot, money(max_loss)))
        else:
            refusal = ("one %s of %s needs %s, more than your %s limit (%s). No order."
                       % (unit if lot == 1 else "lot", sym, money((margin_unit if bound[0] == "margin" else ref) * lot),
                          bound[0], limits[[l["name"] for l in limits].index(bound[0])]["how"]))
    elif _f(c.get("min_reward_risk")) and reward_p < _f(c["min_reward_risk"]) * risk_p - EPS:
        refusal = ("reward:risk %.2f (target %s, entry %s, stop %s) is under your minimum %s, so trader-risk "
                   "would block it. No order. Skip it, or make a new plan with trader-exit."
                   % (reward_p / float(risk_p), _price(target), _price(ref), _price(stop), _num(c["min_reward_risk"])))
    elif value < float(c.get("min_order_inr") or 0) - 0.005:
        refusal = ("%d %s of %s is %s, under your %s minimum order. No order."
                   % (qty, unit + ("" if qty == 1 else "s"), sym, money(value), money(c["min_order_inr"])))
    return {
        "symbol": sym, "side": "buy", "segment": segment, "lot_size": lot, "tick": tk, "product": c["product"],
        "setup": plan.get("setup", ""), "date": plan.get("date"),
        "entry_time": plan.get("entry_time", ""), "entry_plan": round_tick(entry_plan, tk),
        "entry": ref, "entry_from": ref_from, "stop": stop, "target": target,
        "risk_per_share": risk, "reward_risk": round(reward_p / float(risk_p), 2),
        "stop_label": plan.get("stop_label", ""), "target_label": plan.get("target_label", ""),
        "budget": budget, "cash_buffer_pct": buf_pct, "margin_buffer": margin_buffer, "margin_available": available,
        "mis_margin_pct": mis_pct, "margin_per_unit": round(margin_unit, 4), "margin_used": round(qty * margin_unit, 2),
        "max_loss_per_trade_inr": max_loss, "limits": limits, "qty": qty, "bound_by": bound[0],
        "value": value, "max_loss": loss, "max_gain": gain, "charges_at_stop": ch_stop, "charges_at_target": ch_target,
        "flat_by": plan.get("flat_by") or c.get("flat_by"),
        "order_type": "limit" if limit is not None else "market", "refusal": refusal,
    }


def order_ticket(s):
    """The one proposed order, in the words of Kite's order window, plus why and plan."""
    if s["refusal"] or s["qty"] <= 0:
        return None
    o = {"symbol": s["symbol"], "exchange": "NFO" if s["segment"] != "equity" else "NSE", "side": "BUY",
         "qty": int(s["qty"]), "product": s["product"], "type": s["order_type"], "validity": "DAY"}
    if s["order_type"] == "limit":
        o["price"] = _price(s["entry"])
    setup = SETUP_WORDS.get(s["setup"], s["setup"] or "day trade")
    names = {"max loss": "%s max loss per trade" % money(s["max_loss_per_trade_inr"] or 0), "position cap": "position cap",
             "max order": "max order", "margin": "margin after the buffer"}
    why = ("%s on %s: %d %s, bound by your %s (%d x %s = %s at the stop)"
           % (setup, s["symbol"], s["qty"], "shares" if s["segment"] == "equity" else "units", names[s["bound_by"]],
              s["qty"], _price(s["risk_per_share"]), money(s["max_loss"])))
    o.update({
        "margin_required": round(s["margin_used"], 2),
        "stop_loss_trigger": _price(s["stop"]),
        "target_price": _price(s["target"]),
        "segment": s["segment"], "lot_size": s["lot_size"], "tick": s["tick"],
        "why": why,
        "plan": {"entry": s["entry"], "stop": s["stop"], "target": s["target"],
                 "risk_per_share": s["risk_per_share"], "max_loss": s["max_loss"], "setup": s["setup"],
                 "entry_time": s["entry_time"], "flat_by": s["flat_by"]},
    })
    return o


def _charge_line(label, ch):
    return ("  %-10s %s  (brokerage %s, STT %s, exchange %s, GST %s, stamp %s, SEBI %s)"
            % (label, money(ch["total"]), money(ch["brokerage"]), money(ch["stt"]), money(ch["exchange"]),
               money(ch["gst"]), money(ch["stamp"]), money(ch["sebi"])))


def plan_report(s, order, notes=()):
    lines = []
    setup = SETUP_WORDS.get(s["setup"], s["setup"] or "setup")
    lines.append("%s buy (%s, %s), %s, entry %s%s" % (s["symbol"], s["segment"], s["product"], setup,
                                                       _price(s["entry_plan"]),
                                                       (" at " + s["entry_time"]) if s["entry_time"] else ""))
    lines.append("Stop %s%s. Target %s%s." % (_price(s["stop"]), (": " + s["stop_label"]) if s["stop_label"] else "",
                                             _price(s["target"]),
                                             (": " + s["target_label"]) if s["target_label"] else ""))
    for n in notes:
        lines.append(n)
    src = {"plan": "the plan's entry", "price": "the latest price, above the plan's entry",
           "limit": "your limit price"}[s["entry_from"]]
    lines.append("Sized at %s (%s). Risk %s a share (entry %s minus stop %s). Reward:risk %.2f."
                 % (_price(s["entry"]), src, _price(s["risk_per_share"]), _price(s["entry"]), _price(s["stop"]),
                    s["reward_risk"]))
    lines.append("")
    lines.append("Limits (whole %s; the smallest one wins):" % ("shares" if s["lot_size"] == 1 else "lots of %d" % s["lot_size"]))
    for l in s["limits"]:
        lines.append("  %-13s %-72s %6d%s" % (l["name"], l["how"], l["units"], "  <- binds" if l["binds"] else ""))
    lines.append("")
    if order is None:
        lines.append("No order: " + s["refusal"])
        lines.append("Education and tooling, not financial advice.")
        return "\n".join(lines)
    lines.append("Size: %d %s of %s, value %s, margin Kite blocks about %s. Max loss at the stop: %d x %s = %s; "
                 "max gain at the target %s."
                 % (s["qty"], "shares" if s["segment"] == "equity" else "units", s["symbol"], money(s["value"]),
                    money(s["margin_used"]), s["qty"], _price(s["risk_per_share"]), money(s["max_loss"]),
                    money(s["max_gain"])))
    lines.append("Zerodha charges for the round trip (not in the sizing):")
    lines.append(_charge_line("at stop", s["charges_at_stop"]))
    lines.append(_charge_line("at target", s["charges_at_target"]))
    lines.append("Net after charges: %s lost at the stop, %s gained at the target." % (
        money(s["max_loss"] + s["charges_at_stop"]["total"]), money(s["max_gain"] - s["charges_at_target"]["total"])))
    lines.append("A stop is an order, not a promise: in a fast market it can fill below %s." % _price(s["stop"]))
    lines.append("")
    lines.append("Proposed order for the Kite app (nothing has been placed):")
    how = "limit %s" % order["price"] if order["type"] == "limit" else "market"
    lines.append("  BUY %s %s %s, %s, %s, DAY; then a stop-loss trigger %s and a target sell at %s"
                 % (order["qty"], order["exchange"], order["symbol"], order["product"], how,
                    order["stop_loss_trigger"], order["target_price"]))
    if s["flat_by"]:
        lines.append("Flat by %s IST: anything still open then gets closed by you (trader-alerts rings). "
                     "Zerodha squares MIS off itself late in the session and charges for it." % s["flat_by"])
    lines.append("")
    lines.append("Next: trader-risk checks it, then you place it in Kite.")
    lines.append("Education and tooling, not financial advice.")
    return "\n".join(lines)


# ---------------------------------------------------------------- orders file

def write_orders(path, orders, cfg, source="", now_utc=None):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    doc = {
        "created_by": "trader-budget",
        "created_at": utc_iso(now_utc),
        "status": "proposed",
        "broker": "zerodha",
        "note": ("Proposals only. Nothing is placed by this pack: trader-risk checks each order and "
                 "you place it yourself in the Kite app."),
        "source": source,
        "orders": orders,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- main

def run_plan(a, cfg):
    now = parse_now(a.now)
    today = to_ist(now).date().isoformat()
    plan = read_json(a.plan, "plan (run trader-exit first)")
    limit = None
    if a.limit is not None:
        if a.limit == "plan":
            limit = _f((plan or {}).get("entry"))
        else:
            limit = _f(a.limit)
            if limit is None or limit <= 0:
                raise SizeError("--limit wants a price, like --limit 1342.50")
    sym = str((plan or {}).get("symbol") or "").upper()
    segment = str(a.segment or (plan or {}).get("segment") or "equity").lower()
    notes, price = [], None
    ppath = a.prices or ("trader/prices.json" if os.path.exists("trader/prices.json") else None)
    if ppath and limit is None and sym:
        pdoc = read_json(ppath, "prices")
        p, t, fresh = fresh_price(pdoc, sym, now)
        if p is not None and fresh:
            price = p
            if p > (_f(plan.get("entry")) or 0):
                notes.append("%s last %s (as of %s IST) is above the plan's entry %s, so the risk "
                             "is bigger: sized at %s." % (sym, _price(p), to_ist(t).strftime("%H:%M"),
                                                          _price(plan.get("entry")), _price(p)))
        elif p is not None:
            notes.append("%s in %s is %s: not used (older than %d minutes). Sized at the plan's entry."
                         % (sym, ppath, ("from " + to_ist(t).strftime("%Y-%m-%d %H:%M") + " IST")
                            if t else "undated", FRESH_MINUTES))
    margins = None
    if segment == "equity" and a.margin_pct is None:
        margins = load_margins(a.margins)
    s = size_trade(plan, cfg, a.budget, limit, price, today, margins, segment, a.lot_size, a.margin_per_lot,
                   a.margin_pct, a.tick)
    order = order_ticket(s)
    if order and a.write:
        src = "trader/plan.json (%s %s %s)" % (s["symbol"], s["setup"] or "plan", s["date"] or today)
        write_orders(a.write, [order], cfg, src, now)
    if a.json:
        print(json.dumps({"sizing": s, "orders": [order] if order else [], "notes": notes}, indent=2))
    else:
        print(plan_report(s, order, notes))
        if order and a.write:
            print("Wrote 1 proposed order to %s" % a.write)
    return 0 if order else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Size a day trade to your Zerodha margin and max loss (trader-budget).")
    ap.add_argument("--plan", default="trader/plan.json", help="the trade plan (default trader/plan.json)")
    ap.add_argument("--config", default="trader/config.json", help="rules (default trader/config.json)")
    ap.add_argument("--budget", type=float, help="override the budget in the config (your Kite margin, in rupees)")
    ap.add_argument("--limit", nargs="?", const="plan", metavar="PRICE",
                    help="a limit order instead of market, at the plan's entry or at PRICE")
    ap.add_argument("--prices", help="prices JSON (default trader/prices.json if it exists)")
    ap.add_argument("--now", help="pretend it is this IST, e.g. \"2026-11-16 10:15\"")
    ap.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH",
                    help="write the proposed order (default trader/orders.json)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of the report")
    ap.add_argument("--segment", choices=SEGMENTS, help="equity (default), futures or options")
    ap.add_argument("--lot-size", type=int, help="F&O lot size (Kite's order window shows it)")
    ap.add_argument("--margin-per-lot", type=float, help="futures: the margin Kite shows for one lot, in rupees")
    ap.add_argument("--margin-pct", type=float, help="equity: the MIS margin percent (20 = 5x), instead of Zerodha's list")
    ap.add_argument("--margins", metavar="FILE", help="a saved copy of " + MARGINS_URL)
    ap.add_argument("--tick", type=float, help="price tick in rupees (default 0.05)")
    a = ap.parse_args(argv)
    try:
        return run_plan(a, load_config(a.config))
    except SizeError as e:
        print("size.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
