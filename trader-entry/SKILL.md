---
name: trader-entry
description: >-
  Entry Timer. Watches a setup bar by bar and tells you the moment to get in.
  Opening-range breakout on NSE 5-minute (or 1-minute) bars: the range is the
  first 15 minutes from the 9:15 open, and it triggers on the first completed
  bar that CLOSES above the range high, never on a wick. Also a level setup
  (first close above a price, such as a 20-day high from trader-scanner), an
  optional volume check, and a watch mode that wakes just after each bar
  closes. Says "waiting", "triggered", "expired" or "no data" with the
  reason, in IST. Use when the user says "has RELIANCE broken out", "did it
  break the opening range", "entry for INFY", "when do I get in", "watch it
  for me", "is it a buy yet", or right after /trader-news on a scanner hit.
argument-hint: "[symbol] [--setup orb|level]"
---

# trader-entry

The Entry Timer answers one question: has the setup triggered yet, and if
so at what time and price. It reads free Yahoo bars, counts only bars that
have closed, and never places an order. A late entry is a different trade, so
it also says how long ago the trigger was.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE                  # 15-minute opening range, 5-minute bars
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --write          # also save trader/entry.json
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --setup level --level 1345.00
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --interval 1m --min-volume-x 1.5
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch RELIANCE --until 15:00    # one line per closed bar, stops on the trigger
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                       # every hit in trader/watchlist.json
```

`--offline FILE` reads a saved Yahoo chart JSON, `--now "2026-11-13 10:15"`
(IST) replays a day. Exit 0 = triggered, 1 = anything else.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json` | the symbols for `watchlist` |
| `trader/entry.json` | the trigger, written by `--write` or a `watch` that triggers; read by trader-exit |
| `trader/config.json` | `no_entries_before` (09:30) and `no_entries_after` (15:00), IST. Optional |

## The rules

- **Opening range.** The high and low of the first `--or-minutes` (default 15): the
  9:15, 9:20 and 9:25 five-minute bars, or fifteen 1-minute bars.
- **Trigger.** The first COMPLETED bar after the range whose CLOSE is above the range high. A wick above
  the high is not a trigger. A bar counts only once it has closed (now >= start + interval).
- **The time** is that bar's close time (the 10:00 bar closes at 10:05 AM). The price is its close.
- **Volume.** `--min-volume-x X` also needs the trigger bar's volume at X times the range bars' average.
  The 9:15 bar carries the opening auction, so 1.0 is already a high bar.
- **Time limits.** No entries before 9:30 or after 15:00 (config). NSE has no early closes
  (the Diwali Muhurat evening hour is not modelled).
- **Statuses.** `triggered`, `waiting` (not open, range forming, or no close above yet), `expired` (no
  trigger by the cutoff) or `no-data` (a holiday or no bars). Weekends and NSE trading holidays: closed.
- **Symbols.** `RELIANCE` is read as `RELIANCE.NS`. Yahoo's NSE bars can lag and a slot with no trade
  can be missing: the tool says so instead of filling it.

## Steps for Claude

1. `entry.py check SYMBOL` (add `--write` when it triggers).
2. If waiting: say what it is waiting for. Offer `watch` and run it only if asked.
3. If triggered: give the time, the price, how many minutes ago, and say the next step is `/trader-exit`
   (set the stop and target BEFORE buying).
4. If the trigger was long ago, say the late entry is a different trade.

## Example (live, Fri 2026-11-13, checked at 14:58 IST)

```
RELIANCE.NS  Fri 2026-11-13 14:58 IST  opening-range breakout (15-minute range) on 5-minute bars (Yahoo, free, can lag)
Opening range 9:15-9:30: high ₹1333.40, low ₹1324.30 (3 of 3 bars).
TRIGGERED 10:05 AM at ₹1334.00: the 10:00 bar (bar 9) closed above the range high ₹1333.40 (+0.04%).
That was 293 minutes ago; the last close is ₹1335.20 (14:50 bar). A late entry is a different trade.
Nothing was placed.
```

## What it never does

It never places an order, sizes a position, sets the stop (that is
`/trader-exit`), moves the level after the fact, or counts a bar that has not
closed. A background `watch` has nobody to say yes, so it never goes further
than printing.

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
