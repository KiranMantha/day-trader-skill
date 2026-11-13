#!/usr/bin/env python3
"""Bulk / block deals and insider trades for trader-deals. Standard library only.

The Indian stand-in for "what are the big, informed buyers doing": NSE's
published bulk and block deals (the last session's) and the insider
disclosures listed companies must file under SEBI's PIT rules.

    python3 deals.py today                          # last session's bulk, block and short deals
    python3 deals.py today --symbols RELIANCE INFY  # only these
    python3 deals.py today --kind block --min-qty 100000
    python3 deals.py insider RELIANCE               # insider trades, last 90 days
    python3 deals.py insider SBIN --days 30 --json
    python3 deals.py today --offline tests/fixtures/trader-deals

Sources (free, NSE, unofficial; they refuse a call without a browser-like
User-Agent and a Referer, so both are sent):
  https://www.nseindia.com/api/snapshot-capital-market-largedeal
  https://www.nseindia.com/api/corporates-pit?index=equities&symbol=RELIANCE&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY

What the words mean:
  bulk deal   one client traded 0.5% or more of a company's shares in a day
  block deal  a large trade in the special block window, at least Rs 10 crore
  short deal  short sales reported by brokers (symbol and quantity only)
  insider     a promoter, director or designated person bought or sold; the
              rows come from their own filings (they can be late, and a sale
              can be a pledge or an inter-se transfer: read the mode)

A deal is a fact about the past: it is not a signal, and the other side of a
bulk deal is often another fund. Exit 0 when anything printed, 1 when nothing.
--offline DIR reads DIR/largedeal.json and DIR/pit-<SYMBOL>.json.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

LARGE_URL = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
PIT_URL = ("https://www.nseindia.com/api/corporates-pit?index=equities&symbol=%s&from_date=%s&to_date=%s")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
KINDS = {"bulk": "BULK_DEALS_DATA", "block": "BLOCK_DEALS_DATA", "short": "SHORT_DEALS_DATA"}


class DealsError(Exception):
    pass


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*",
                                               "Referer": "https://www.nseindia.com/"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise DealsError("NSE answered HTTP %d for %s" % (e.code, url))
    except OSError as e:
        raise DealsError("could not reach NSE: %s" % e)


def load(url, offline, name):
    if offline:
        path = os.path.join(offline, name)
        if not os.path.exists(path):
            raise DealsError("offline: no file %s" % path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = get(url)
    try:
        return json.loads(text)
    except ValueError as e:
        raise DealsError("NSE sent something that is not JSON (%s): %s" % (name, e))


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def inr(x):
    """Rupees with lakh / crore grouping, no decimals when whole."""
    s = "%.2f" % x
    i, _, f = s.partition(".")
    neg = i.startswith("-")
    i = i.lstrip("-")
    head, tail = i[:-3], i[-3:]
    if head:
        head = ",".join(reversed([head[max(0, k - 2):k] for k in range(len(head), 0, -2)]))
        tail = head + "," + tail
    return ("-" if neg else "") + "₹" + tail + ("" if f == "00" else "." + f)


def deals_today(doc, kinds=("bulk", "block", "short"), symbols=None, min_qty=0):
    """largedeal JSON -> {"date", "deals": [..]}, biggest quantity first within each kind."""
    if not isinstance(doc, dict):
        raise DealsError("the large-deal answer is not the shape this tool knows")
    want = {s.upper() for s in symbols or []}
    out = []
    for kind in kinds:
        for r in doc.get(KINDS[kind]) or []:
            sym = str(r.get("symbol") or "").upper()
            qty = _num(r.get("qty")) or 0
            if (want and sym not in want) or qty < min_qty:
                continue
            out.append({"kind": kind, "symbol": sym, "name": r.get("name"), "side": (r.get("buySell") or "").upper() or None,
                        "client": r.get("clientName"), "qty": int(qty), "price": _num(r.get("watp")),
                        "date": r.get("date"), "remarks": r.get("remarks")})
    out.sort(key=lambda d: (list(KINDS).index(d["kind"]), -d["qty"]))
    return {"date": doc.get("as_on_date"), "deals": out}


def insiders(doc):
    """corporates-pit JSON -> trades, newest first. Buys and sells in rupees."""
    rows = (doc or {}).get("data") if isinstance(doc, dict) else None
    if rows is None:
        raise DealsError("the insider answer is not the shape this tool knows")
    out = []
    for r in rows:
        buy, sell = _num(r.get("buyValue")) or 0, _num(r.get("sellValue")) or 0
        side = (r.get("tdpTransactionType") or "").title() or ("Buy" if buy else "Sell" if sell else "")
        out.append({"date": str(r.get("date") or "")[:11].strip(), "who": r.get("acqName"), "category": r.get("personCategory"),
                    "side": side, "mode": r.get("acqMode"), "qty": int(_num(r.get("secAcq")) or 0),
                    "value": (buy if side.lower().startswith("buy") else sell) or (_num(r.get("secVal")) or 0),
                    "security": r.get("secType"), "after_pct": _num(r.get("afterAcqSharesPer")), "link": r.get("xbrl")})

    def key(t):
        try:
            return datetime.datetime.strptime(t["date"], "%d-%b-%Y")
        except ValueError:
            return datetime.datetime.min
    return sorted(out, key=key, reverse=True)


def cmd_today(a):
    kinds = [a.kind] if a.kind else list(KINDS)
    res = deals_today(load(LARGE_URL, a.offline, "largedeal.json"), kinds, a.symbols, a.min_qty)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0 if res["deals"] else 1
    print("NSE bulk, block and short deals for %s." % (res["date"] or "the last session"))
    if not res["deals"]:
        print("Nothing matched%s." % (" for " + ", ".join(a.symbols) if a.symbols else ""))
        return 1
    for k in kinds:
        rows = [d for d in res["deals"] if d["kind"] == k]
        if not rows:
            continue
        print("\n%s deals (%d):" % (k.title(), len(rows)))
        for d in rows[:a.show]:
            if k == "short":
                print("  %-12s short %s shares" % (d["symbol"], "{:,}".format(d["qty"])))
            else:
                print("  %-12s %-4s %12s sh @ %-10s %s" % (d["symbol"], d["side"] or "", "{:,}".format(d["qty"]),
                                                          inr(d["price"]) if d["price"] else "-", (d["client"] or "")[:44]))
        if len(rows) > a.show:
            print("  ... %d more (--show N, or --symbols)" % (len(rows) - a.show))
    print("\nA deal is a fact about the past, not a signal. Not financial advice.")
    return 0


def cmd_insider(a):
    sym = a.symbol.upper()
    today = datetime.datetime.now(IST).date()
    frm = (today - datetime.timedelta(days=a.days)).strftime("%d-%m-%Y")
    url = PIT_URL % (urllib.parse.quote(sym, safe=""), frm, today.strftime("%d-%m-%Y"))
    rows = insiders(load(url, a.offline, "pit-%s.json" % sym))
    if a.json:
        print(json.dumps({"symbol": sym, "days": a.days, "trades": rows}, indent=2))
        return 0 if rows else 1
    if not rows:
        print("No insider disclosures for %s in the last %d days." % (sym, a.days))
        return 1
    buys = sum(t["value"] for t in rows if t["side"].lower().startswith("buy"))
    sells = sum(t["value"] for t in rows if t["side"].lower().startswith("sell"))
    print("%s insider disclosures, last %d days: %d filings, bought %s, sold %s." % (sym, a.days, len(rows), inr(buys), inr(sells)))
    for t in rows[:a.show]:
        print("  %-11s %-5s %9s sh %14s  %s (%s), %s" % (t["date"], t["side"], "{:,}".format(t["qty"]), inr(t["value"]),
                                                      t["who"], t["category"], t["mode"]))
    print("\nFilings can be late, and a 'sale' may be a pledge or a transfer between promoters: read the mode. Not financial advice.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="NSE bulk / block deals and insider trades (trader-deals).")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("today", help="the last session's bulk, block and short deals")
    p.add_argument("--symbols", nargs="*")
    p.add_argument("--kind", choices=list(KINDS))
    p.add_argument("--min-qty", type=int, default=0)
    p.add_argument("--show", type=int, default=25, help="rows per kind (default 25)")
    p = sub.add_parser("insider", help="insider (SEBI PIT) trades in one stock")
    p.add_argument("symbol")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--show", type=int, default=25)
    for p in sub.choices.values():
        p.add_argument("--offline", metavar="DIR")
        p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"today": cmd_today, "insider": cmd_insider}[a.cmd](a)
    except DealsError as e:
        print("deals.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
