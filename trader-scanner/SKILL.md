---
name: trader-scanner
description: >-
  Chart Scanner. Scans thousands of NSE charts for setups: opening-range
  breakouts, flags, oversold bounces. Builds the list of NSE EQ-series stocks
  that Zerodha lets you trade intraday (MIS) from NSE's EQUITY_L.csv and
  Zerodha's public margin list, runs a pre-market scan of daily closes
  (20-day closing-high breakout, bull flag, reclaimed the 20-day average,
  oversold, oversold bounce) and an intraday opening-range breakout scan on
  5-minute bars from the 9:15 open, then writes trader/watchlist.json for
  trader-news and trader-entry. Free Yahoo data, bar by bar. Use when the
  user says "scan the market", "find me setups", "what is breaking out",
  "opening range breakouts", "scan for bull flags", "oversold stocks",
  "pre-market scan", "build my watchlist", "what should I look at today",
  "nifty stocks breaking out", or at the start of a trading day before
  /trader-news.
argument-hint: "[universe | daily | orb] [--at HH:MM]"
---

# trader-scanner

The Chart Scanner is the first step of a day trade. It reads thousands of
free charts and lists the ones that match a rule. That is all it does. A scan
is a list of charts that match a rule, not a list of stocks to buy, and a
setup on a chart is not a prediction. Most people who day trade lose money;
the scanner does not change that. It only saves you from flipping through
1,500 charts by hand.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                       # -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                          # before the open -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE,INFY,SBIN   # or --watchlist FILE, --limit 200
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                            # after 9:35 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:15                 # cut the clock at 10:15 AM IST
```

`--now "2026-11-13 10:15"` (IST) pins the clock, `--offline PATH` reads saved
files instead of the network, `--min-price` and `--min-volume` set the
liquidity floors (defaults: Rs 50 and 500,000 shares for `daily`), `--limit N`
scans the first N symbols, `--no-write` leaves the watchlist alone.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | one `SYMBOL|Name` a line, written by `universe` |
| `trader/watchlist.json` | the hits, written by `daily` and `orb`, read by trader-news and trader-entry |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 15:00) |

## The universe

`universe` downloads NSE's `EQUITY_L.csv` (archives.nseindia.com) and
Zerodha's public margin list (api.kite.trade/margins/equity) and keeps a
symbol when, in this order:

1. Its series is `EQ`. `BE` and `BZ` are trade-for-trade (no intraday), `SM` and `ST` are SME.
2. Its symbol is plain: letters, digits, `&` or `-` (M&M, BAJAJ-AUTO, 360ONE).
3. Zerodha has a `mis_margin` above 0 for it. No MIS at Zerodha means no intraday trade
   there, so it is not worth scanning. On 2026-11-13 that left 1,474 of 2,635 rows.

A symbol you type is mapped to Yahoo's NSE suffix (`RELIANCE` becomes
`RELIANCE.NS`; `.BO` for BSE and `^NSEI` pass through).

## Daily scan (before the 9:15 open)

Yahoo spark, 20 symbols a request, three months of daily closes. Liquidity
from the spark meta: price at least `--min-price`, volume at least
`--min-volume`. Setups, from closes only: `breakout_20d`, `bull_flag` (up
over 10% in the 10 sessions before the last 5, then a 5% range),
`reclaim_ma20`, `oversold` (RSI 14 under 30), `oversold_bounce`. Today's bar
is left out until the 15:30 close.

## Opening-range breakout scan (after 9:35 AM IST)

The opening range is the first `--or-minutes` (15) of the session: the 9:15,
9:20 and 9:25 five-minute bars. A hit is the first completed 5-minute bar
after it that closes above the range high, listed at that bar's close time.
Stage 1 uses closes for every symbol, stage 2 confirms each candidate with
real highs and lows (at most `--max-confirm`, most traded first, and it says
so when it stops short).

A chart is usable only when every 5-minute bar from 9:15 to the cutoff is
there. NSE stocks often have a 5-minute slot with no trade, so illiquid
names drop out here: on a live run, 27 of the first 60 symbols were usable.
That is the scan being strict, not broken.

## Steps for Claude

1. If `trader/universe.txt` is missing or older than a week: `scan.py universe`.
2. Before the open: `scan.py daily`. After 9:35 AM IST (10:15 is the classic): `scan.py orb`.
3. Show the list as printed. Say how many charts were usable and why the rest were not.
4. Hand one symbol on: `/trader-news RELIANCE`, then `/trader-entry RELIANCE`.

## Example (live, Fri 2026-11-13, 2:58 PM IST, first 60 symbols)

```
Opening-range breakout scan, Fri 2026-11-13 2:58 PM IST: 15-minute range (9:15 to 9:30 AM), 5-minute bars, Yahoo.
Fetched 60 of 60 charts; 27 usable; 19 candidates, 19 confirmed with real highs and lows.
16 of 27 charts closed above their opening-range high by 2:58 PM:
   9:35 AM  ABREL   ₹1,190.00  range 1,162.20 to 1,185.80  +0.35% over
   9:35 AM  AEGISVOPAK    ₹279.28  range 267.83 to 276.00  +1.19% over
```

Late in the day this list is mostly stale: a breakout from 9:35 is not a trade at 14:58.

## What it never does

It never places, sizes or checks an order, never says which stock to buy,
never calls data real time, and never promises that a setup works. A scan on
a trading holiday or after the close says so and writes nothing.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Nothing in this pack places an order. Zerodha has no paper account and this pack has no broker
  connection: the user keys every order into the Kite app themselves, and only after trader-risk
  passed that exact ticket today and the user said an explicit yes in the chat.
- Intraday only (Zerodha product MIS) and long only. The pack does not carry positions overnight
  and does not short unless the config allows it and the user confirms.
- Zerodha is the benchmark: its public MIS margin list, its charges page and its auto square-off
  apply. This pack reads them and never overrides them.
- The data is free, delayed and unofficial (Yahoo Finance, NSE). Never time an order from it
  alone: look at Kite.
