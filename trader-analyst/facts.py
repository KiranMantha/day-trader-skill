#!/usr/bin/env python3
"""Earnings reader for trader-analyst. Standard library only.

Pulls a company's reported quarters from NSE's results endpoint and lays out
what changed, quarter by quarter: revenue, net profit, net margin, EPS, and
growth against the same quarter a year earlier and the quarter before.

    python3 facts.py RELIANCE
    python3 facts.py INFY TCS --quarters 5
    python3 facts.py INFY --json
    python3 facts.py INFY SBIN --metrics trader/metrics.json

Source (free, NSE, unofficial; it wants a browser-like User-Agent and a Referer):
  https://www.nseindia.com/api/results-comparision?symbol=INFY

What you get, and what you do not:
  - NSE returns the company's last five reported quarters as the NSE results
    filing has them: STANDALONE figures for most companies (a group's
    consolidated profit can be very different: Reliance and Infosys are far
    bigger consolidated). Check the filing before leaning on a number.
  - Amounts are in rupees crore (NSE reports rupees lakh; 100 lakh = 1 crore).
  - Banks and finance companies file a different layout (NSE flags them
    "bank"): revenue and margins are left blank for them, profit and EPS stay.
  - The newest quarter can be old. A quarter ended more than 4 months ago is
    flagged STALE, because a company reports within about 45 days of the
    quarter's end; check the company's latest results announcement
    (trader-news) before trusting these.
  - Numbers only: this tool never says whether a stock is a buy.

--metrics FILE merges one row per symbol into a JSON file (latest quarter,
TTM revenue and profit, growth, margins). --offline DIR reads DIR/results-<SYMBOL>.json.
"""

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

RESULTS_URL = "https://www.nseindia.com/api/results-comparision?symbol=%s"
LAKH_PER_CRORE = 100.0
STALE_DAYS = 120


class FactsError(Exception):
    pass


def fetch(sym):
    req = urllib.request.Request(RESULTS_URL % urllib.parse.quote(sym, safe=""), headers={
        "User-Agent": "Mozilla/5.0", "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise FactsError("NSE answered HTTP %d for %s" % (e.code, sym))
    except OSError as e:
        raise FactsError("could not reach NSE: %s" % e)


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _date(s):
    try:
        return _dt.datetime.strptime(str(s).title(), "%d-%b-%Y").date()
    except ValueError:
        return None


def parse_results(text, sym):
    """NSE results-comparision JSON -> (quarters oldest first, is_bank). Amounts in rupees crore."""
    try:
        doc = json.loads(text)
        rows = doc["resCmpData"]
    except (ValueError, KeyError, TypeError):
        raise FactsError("NSE sent something unexpected for %s (not its results JSON)" % sym)
    bank = str(doc.get("bankNonBnking") or "N").upper() == "Y"
    out = []
    for r in rows:
        end, start = _date(r.get("re_to_dt")), _date(r.get("re_from_dt"))
        if not end or not start or not 60 <= (end - start).days <= 110:   # quarters only
            continue
        crore = lambda k: (_num(r.get(k)) / LAKH_PER_CRORE) if _num(r.get(k)) is not None else None
        out.append({"end": end.isoformat(), "revenue": None if bank else crore("re_net_sale"),
                    "net_profit": crore("re_net_profit") if crore("re_net_profit") is not None else crore("re_proloss_ord_act"),
                    "eps_diluted": _num(r.get("re_dilut_eps_for_cont_dic_opr")),
                    "eps_basic": _num(r.get("re_basic_eps_for_cont_dic_opr")),
                    "filed": r.get("re_create_dt"), "audited": r.get("re_res_type")})
    if not out:
        raise FactsError("no quarterly results for %s in NSE's answer (wrong symbol, or a new listing)" % sym)
    if all(q["revenue"] is None for q in out) or bank:       # banks file no "net sale" line
        bank = True
        for q in out:
            q["revenue"] = None
    seen = {}
    for q in out:                      # the same quarter can be listed twice: keep the first
        seen.setdefault(q["end"], q)
    return sorted(seen.values(), key=lambda q: q["end"]), bank


def pct(a, b):
    return None if a is None or not b else round(100.0 * (a - b) / abs(b), 1)


def analyse(quarters, today=None):
    today = today or _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=5, minutes=30))).date()
    for i, q in enumerate(quarters):
        q["net_margin"] = None if not q["revenue"] or q["net_profit"] is None else round(100.0 * q["net_profit"] / q["revenue"], 1)
        yoy = quarters[i - 4] if i >= 4 else None
        qoq = quarters[i - 1] if i >= 1 else None
        q["revenue_yoy"] = pct(q["revenue"], yoy["revenue"]) if yoy else None
        q["profit_yoy"] = pct(q["net_profit"], yoy["net_profit"]) if yoy else None
        q["revenue_qoq"] = pct(q["revenue"], qoq["revenue"]) if qoq else None
        q["profit_qoq"] = pct(q["net_profit"], qoq["net_profit"]) if qoq else None
    last = quarters[-1]
    age = (today - _dt.date.fromisoformat(last["end"])).days
    ttm = quarters[-4:] if len(quarters) >= 4 else []
    return {"quarters": quarters, "latest": last["end"], "age_days": age, "stale": age > STALE_DAYS,
            "ttm_revenue": round(sum(q["revenue"] for q in ttm), 1) if ttm and all(q["revenue"] is not None for q in ttm) else None,
            "ttm_net_profit": round(sum(q["net_profit"] for q in ttm), 1) if ttm and all(q["net_profit"] is not None for q in ttm) else None,
            "ttm_eps": round(sum(q["eps_diluted"] for q in ttm), 2) if ttm and all(q["eps_diluted"] is not None for q in ttm) else None}


def _c(v):
    return "-" if v is None else "{:,.0f}".format(v)


def _g(v):
    return "-" if v is None else "%+.1f%%" % v


def render(sym, res, bank):
    last = res["quarters"][-1]
    lines = ["%s: NSE standalone quarterly results, rupees crore%s." % (sym, " (bank / finance layout: no revenue)" if bank else "")]
    if res["stale"]:
        lines.append("STALE: the newest quarter NSE returned ended %s, %d days ago. Check trader-news for newer results." % (
            res["latest"], res["age_days"]))
    lines.append("  %-11s %10s %9s %9s %10s %9s %9s %7s %8s" % ("quarter end", "revenue", "yoy", "qoq", "net profit", "yoy", "qoq", "margin", "EPS"))
    for q in res["quarters"]:
        lines.append("  %-11s %10s %9s %9s %10s %9s %9s %7s %8s" % (
            q["end"], _c(q["revenue"]), _g(q["revenue_yoy"]), _g(q["revenue_qoq"]), _c(q["net_profit"]), _g(q["profit_yoy"]),
            _g(q["profit_qoq"]), "-" if q["net_margin"] is None else "%.1f%%" % q["net_margin"],
            "-" if q["eps_diluted"] is None else "%.2f" % q["eps_diluted"]))
    if res["ttm_net_profit"] is not None:
        lines.append("  Last four quarters: revenue %s, net profit %s, EPS %s." % (
            _c(res["ttm_revenue"]), _c(res["ttm_net_profit"]), "-" if res["ttm_eps"] is None else "%.2f" % res["ttm_eps"]))
    lines.append("Numbers only, not a view on the stock. Standalone, not consolidated: open the filing before relying on them.")
    return "\n".join(lines)


def metrics_row(sym, res):
    last = res["quarters"][-1]
    return {"symbol": sym, "latest_quarter": res["latest"], "stale": res["stale"], "ttm_revenue_cr": res["ttm_revenue"],
            "ttm_net_profit_cr": res["ttm_net_profit"], "ttm_eps": res["ttm_eps"], "net_margin_pct": last["net_margin"],
            "revenue_yoy_pct": last["revenue_yoy"], "profit_yoy_pct": last["profit_yoy"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read a company's reported quarters from NSE (trader-analyst).")
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--quarters", type=int, default=5, help="quarters to show (NSE returns at most 5)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--metrics", metavar="FILE", help="merge one row per symbol into this JSON file")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--today", help="YYYY-MM-DD, for reproducible staleness")
    a = ap.parse_args(argv)
    today = _dt.date.fromisoformat(a.today) if a.today else None
    out, rows, rc = [], {}, 0
    for sym in [s.upper() for s in a.symbols]:
        try:
            if a.offline:
                with open(os.path.join(a.offline, "results-%s.json" % sym), encoding="utf-8") as fh:
                    text = fh.read()
            else:
                text = fetch(sym)
            quarters, bank = parse_results(text, sym)
            res = analyse(quarters, today)
            res["quarters"] = res["quarters"][-a.quarters:]
            out.append((sym, res, bank))
            rows[sym] = metrics_row(sym, res)
        except (FactsError, OSError) as e:
            print("facts.py: %s: %s" % (sym, e), file=sys.stderr)
            rc = 1
    if a.json:
        print(json.dumps({s: dict(r, bank=b) for s, r, b in out}, indent=2))
    else:
        print("\n\n".join(render(s, r, b) for s, r, b in out))
    if a.metrics and rows:
        doc = {}
        if os.path.exists(a.metrics):
            with open(a.metrics, encoding="utf-8") as fh:
                doc = json.load(fh)
        doc.update(rows)
        d = os.path.dirname(a.metrics)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.metrics, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
