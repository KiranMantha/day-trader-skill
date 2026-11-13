#!/usr/bin/env python3
"""Order tickets and the trade log for trader-broker, for Zerodha Kite. Standard library only.

This tool never talks to Zerodha and never places anything: you key every
order into the Kite app yourself. It does the paperwork around that:

  show      renders each proposed order as the fields of Kite's order window
            (exchange, product MIS, qty, price, then the stop-loss and the
            target you place after the entry fills) with the max loss and the
            Zerodha charges. An order is READY only if trader-risk passed THIS
            exact order today (matched by fingerprint) and you have not
            logged it yet.
  placed    logs that you placed ONE order in Kite (refuses an order that is
            not READY), with Kite's order id if you want it. This is what
            trader-risk counts for max trades and max daily loss.
  skip      logs that you decided not to place it.
  fill      logs a fill (an entry filling, or the stop / target / your exit).
  flatten   prints the Kite steps that close a symbol's open position by
            flat_by, and logs nothing until you tell it the fill.
  log       prints today's log.

    python3 ticket.py show                    # every order, READY or not
    python3 ticket.py show --index 1 --json   # one ticket as JSON
    python3 ticket.py placed --index 1 --kite-id 2611130012345678
    python3 ticket.py fill --symbol RELIANCE --side buy --qty 62 --price 1340.05
    python3 ticket.py fill --symbol RELIANCE --side sell --qty 62 --price 1332.05
    python3 ticket.py flatten --symbol RELIANCE --qty 62
    python3 ticket.py skip --index 1 --note "gapped away"
    python3 ticket.py log

Everything is written to trader/state/broker.json (append only). Dates are
IST dates; --now "2026-11-16 10:15" pins the clock. Zerodha has no paper
account, so every ticket is real money: there is no paper mode.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

ORDER_FIELDS = ("symbol", "exchange", "side", "qty", "product", "type", "validity", "price",
                "stop_loss_trigger", "target_price", "segment", "lot_size", "tick", "margin_required")


class TicketError(Exception):
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
        raise TicketError("--now wants a time like \"2026-10-19 10:15\" (IST) or ...Z (UTC)")
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise TicketError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise TicketError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def rec_day(rec):
    """The trading day a decision belongs to: its "date" (the day it was made under), else the day of "at"."""
    return str(rec.get("date") or str(rec.get("at", ""))[:10])



def rec_day(rec):
    """The trading day a record belongs to: its "date", else the day of "at"."""
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


def ist_iso(now_utc):
    """naive UTC -> "2026-11-16T10:15:00+05:30"."""
    return to_ist(now_utc).replace(microsecond=0).isoformat() + "+05:30"


def fingerprint(order):
    """Same function as trader-risk/check.py: identifies the exact order."""
    core = {k: order[k] for k in ORDER_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _group(s):
    """'1234567.5' -> '12,34,567.5': lakh and crore grouping, like the Kite app."""
    neg, s = s.startswith("-"), s.lstrip("-")
    i, dot, f = s.partition(".")
    head, tail = i[:-3], i[-3:]
    if head:
        head = ",".join(reversed([head[max(0, k - 2):k] for k in range(len(head), 0, -2)]))
        tail = head + "," + tail
    return ("-" if neg else "") + tail + dot + f


def _money(v):
    f = float(v)
    s = _group("{:.2f}".format(f))
    return "₹" + (s[:-3] if s.endswith(".00") else s)


def _p(v):
    return "%.2f" % float(v)


def _p(v):
    return "%.2f" % float(v)


def max_loss(order):
    stop = _f(order.get("stop_loss_trigger")) or _f((order.get("plan") or {}).get("stop"))
    entry = _f(order.get("price")) if str(order.get("type", "market")).lower() == "limit" else None
    entry = entry or _f((order.get("plan") or {}).get("entry"))
    q = _f(order.get("qty"))
    if stop is None or entry is None or q is None:
        return None, stop
    return round(q * (entry - stop), 2), stop


def plain(order):
    typ = str(order.get("type", "market")).lower()
    how = "limit %s" % _p(order["price"]) if typ == "limit" and order.get("price") else typ
    return "%s %s %s %s, %s, %s" % (str(order.get("side", "")).upper(), order.get("qty"), order.get("exchange", "NSE"),
                                    order.get("symbol"), order.get("product", "MIS"), how)


# ---------------------------------------------------------------- state

def load_state(path):
    return read_json(path, "broker state", required=False) or {"orders": []}


def latest(state, fp, today):
    found = None
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and rec_day(rec) == today:
            found = rec
    return found


def risk_verdict(risk, fp, today):
    if not risk:
        return None, "trader-risk has not checked these orders (run check.py)"
    if risk.get("date") != today:
        return None, "the risk check is from %s, not today; run check.py again" % risk.get("date")
    for r in risk.get("results", []):
        if r.get("fingerprint") == fp:
            return r, None
    return None, "this exact order was not in the last risk check (it changed or is new); run check.py again"


def status_of(order, risk, state, today):
    """(ready, label, risk_result)"""
    fp = fingerprint(order)
    rv, why = risk_verdict(risk, fp, today)
    if rv is None:
        return False, "NOT READY: " + why, None
    if rv.get("verdict") != "PASS":
        return False, "BLOCKED by trader-risk: " + "; ".join(rv.get("reasons", [])), rv
    rec = latest(state, fp, today)
    if rec:
        return False, "DONE: %s at %s" % (rec.get("status"), rec.get("at")), rv
    return True, "READY: trader-risk PASS, place it in Kite", rv


def kind_of(order, rv):
    if rv and rv.get("kind"):
        return rv["kind"]
    return "entry" if str(order.get("side", "")).lower() == "buy" else "exit"


def render(order, idx, total, risk, state, today):
    ready, label, rv = status_of(order, risk, state, today)
    loss, stop = max_loss(order)
    lines = ["ORDER %d of %d  %s" % (idx, total, label), "  " + plain(order)]
    lines.append("  Kite order window: %s  |  %s  |  qty %s  |  %s  |  price %s  |  validity %s" % (
        order.get("exchange", "NSE"), order.get("product", "MIS"), order.get("qty"),
        str(order.get("type", "market")).upper(), _p(order["price"]) if order.get("price") else "market",
        str(order.get("validity", "day")).upper()))
    if order.get("stop_loss_trigger") is not None:
        lines.append("  Then, once it fills: a stop-loss order (SL) with trigger %s" % _p(order["stop_loss_trigger"]))
    if order.get("target_price") is not None:
        lines.append("  and a sell limit at the target %s (cancel whichever you do not use: Kite has no bracket orders)"
                     % _p(order["target_price"]))
    if loss is not None:
        lines.append("  Max loss at the stop: %s%s" % (_money(loss), (" (stop %s)" % _p(stop)) if stop else ""))
    if order.get("margin_required") is not None:
        lines.append("  Margin Kite should block: about %s" % _money(order["margin_required"]))
    plan = order.get("plan") or {}
    if plan.get("flat_by"):
        lines.append("  Out by %s IST. Zerodha squares MIS off by itself a few minutes later and charges for it." % plan["flat_by"])
    if order.get("why"):
        lines.append("  Why this size: " + order["why"])
    if rv:
        for w in rv.get("warnings", []):
            lines.append("  ~ " + w)
    return "\n".join(lines), ready


def _clock(a):
    now = parse_now(getattr(a, "now", None))
    today = getattr(a, "today", None) or to_ist(now).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        raise TicketError("--today wants a date like 2026-11-16")
    return now, today


def _load(a):
    doc = read_json(a.orders, "orders file (run trader-budget first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise TicketError("no orders in %s" % a.orders)
    risk = read_json(a.risk, "risk check", required=False)
    state = load_state(a.state)
    now, today = _clock(a)
    return orders, risk, state, today, now


def _pick(orders, index):
    if index is None:
        raise TicketError("say which order: --index N")
    if not 1 <= index <= len(orders):
        raise TicketError("there is no order %d (there are %d)" % (index, len(orders)))
    return orders[index - 1]


def cmd_show(a):
    orders, risk, state, today, now = _load(a)
    picks = [(a.index, _pick(orders, a.index))] if a.index else list(enumerate(orders, 1))
    out = []
    for i, o in picks:
        text, ready = render(o, i, len(orders), risk, state, today)
        out.append({"index": i, "ready": ready, "fingerprint": fingerprint(o), "order": o, "ticket": text})
    if a.json:
        print(json.dumps(out if not a.index else out[0], indent=2))
    else:
        print("\n\n".join(x["ticket"] for x in out))
        print("\nNothing is placed by this tool. Key the order into Kite yourself, then: ticket.py placed --index N")
    return 0 if all(x["ready"] for x in out) else 1


def _log(a, order, status, now, today, extra=None):
    state = load_state(a.state)
    loss, stop = max_loss(order)
    rv, _ = risk_verdict(read_json(a.risk, "risk check", required=False), fingerprint(order), today)
    rec = {"at": ist_iso(now), "date": today, "index": a.index, "fingerprint": fingerprint(order),
           "symbol": str(order.get("symbol", "")).upper(), "side": str(order.get("side", "")).lower(),
           "plain": plain(order), "status": status, "qty": order.get("qty"), "kind": kind_of(order, rv)}
    if loss is not None:
        rec["max_loss"] = loss
    if stop is not None:
        rec["stop"] = stop
    rec.update(extra or {})
    state.setdefault("orders", []).append(rec)
    write_json(a.state, state)


def cmd_placed(a):
    orders, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    ready, label, _ = status_of(order, risk, state, today)
    if not ready:
        raise TicketError("order %d is not ready: %s" % (a.index, label))
    extra = {"broker_order_id": a.kite_id} if a.kite_id else {}
    _log(a, order, "placed", now, today, extra)
    print("Logged order %d as placed in Kite: %s." % (a.index, plain(order)))
    print("When it fills, log it: ticket.py fill --symbol %s --side %s --qty %s --price P"
          % (order.get("symbol"), order.get("side"), order.get("qty")))
    print("Then place the stop-loss (trigger %s) and the target in Kite." % _p(order.get("stop_loss_trigger") or 0))
    return 0


def cmd_skip(a):
    orders, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    _log(a, order, "skipped", now, today, {"note": a.note} if a.note else None)
    print("Logged order %d as skipped." % a.index)
    return 0


def cmd_fill(a):
    now, today = _clock(a)
    state = load_state(a.state)
    side = a.side.lower()
    if side not in ("buy", "sell"):
        raise TicketError("--side is buy or sell")
    if a.qty <= 0 or a.price <= 0:
        raise TicketError("--qty and --price must be above 0")
    sym = a.symbol.upper()
    state.setdefault("orders", []).append({
        "at": ist_iso(now), "date": today, "status": "filled", "symbol": sym, "side": side,
        "qty": int(a.qty) if a.qty == int(a.qty) else a.qty, "price": a.price,
        "plain": "%s %s %s at %s" % (side.upper(), int(a.qty), sym, _p(a.price))})
    write_json(a.state, state)
    print("Logged: %s %s %s at %s." % (side, int(a.qty), sym, _p(a.price)))
    fills = [r for r in state["orders"] if r.get("status") == "filled" and r.get("symbol") == sym and rec_day(r) == today]
    net = sum((r["qty"] if r["side"] == "buy" else -r["qty"]) for r in fills)
    if net:
        print("%s open today: %+d. Exit it in Kite (Positions > Exit) before the flat-by time." % (sym, net))
    else:
        gross = sum((1 if r["side"] == "sell" else -1) * r["qty"] * r["price"] for r in fills)
        print("%s is flat today: gross %s before Zerodha's charges (trader-budget shows them)." % (sym, _money(gross)))
    return 0


def cmd_flatten(a):
    now, today = _clock(a)
    sym = a.symbol.upper()
    cfg = read_json(a.config, "config", required=False) or {}
    plan = read_json(a.plan, "plan", required=False) or {}
    flat_by = (plan.get("flat_by") if str(plan.get("symbol", "")).upper() == sym else None) or cfg.get("flat_by") or "15:15"
    print("Close %s by %s IST (it is %s):" % (sym, flat_by, to_ist(now).strftime("%H:%M")))
    print("  1. Kite > Orders: cancel the open stop-loss and target for %s, if any." % sym)
    print("  2. Kite > Positions > %s (MIS) > Exit%s." % (sym, (", qty %d" % a.qty) if a.qty else ""))
    print("  3. When it fills: ticket.py fill --symbol %s --side sell --qty %s --price P" % (sym, a.qty or "Q"))
    print("Zerodha squares MIS off by itself a few minutes after 15:15 and charges for it.")
    return 0


def cmd_log(a):
    now, today = _clock(a)
    recs = [r for r in load_state(a.state).get("orders", []) if rec_day(r) == today]
    if not recs:
        print("Nothing logged today (%s)." % today)
        return 0
    for r in recs:
        print("%s  %-8s %s%s" % (str(r.get("at", ""))[11:16], r.get("status"), r.get("plain", ""),
                                 ("  max loss " + _money(r["max_loss"])) if r.get("max_loss") is not None else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kite order tickets and the trade log (trader-broker).")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--orders", default="trader/orders.json")
        p.add_argument("--risk", default="trader/state/risk.json")
        p.add_argument("--state", default="trader/state/broker.json")
        p.add_argument("--config", default="trader/config.json")
        p.add_argument("--now")
        p.add_argument("--today")
    p = sub.add_parser("show"); common(p)
    p.add_argument("--index", type=int); p.add_argument("--json", action="store_true")
    p = sub.add_parser("placed"); common(p)
    p.add_argument("--index", type=int); p.add_argument("--kite-id")
    p = sub.add_parser("skip"); common(p)
    p.add_argument("--index", type=int); p.add_argument("--note")
    p = sub.add_parser("fill"); common(p)
    p.add_argument("--symbol", required=True); p.add_argument("--side", required=True)
    p.add_argument("--qty", type=float, required=True); p.add_argument("--price", type=float, required=True)
    p = sub.add_parser("flatten"); common(p)
    p.add_argument("--symbol", required=True); p.add_argument("--qty", type=int)
    p.add_argument("--plan", default="trader/plan.json")
    p = sub.add_parser("log"); common(p)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"show": cmd_show, "placed": cmd_placed, "skip": cmd_skip, "fill": cmd_fill,
                "flatten": cmd_flatten, "log": cmd_log}[a.cmd](a)
    except TicketError as e:
        print("ticket.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
