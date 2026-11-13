---
name: trader-timemachine
description: >-
  Time Machine. Before you risk a rupee, replays the rest of the session
  10,000 times from the stock's own recent 5-minute bars, plus every past day
  the same setup fired, and tells you the honest odds: target first, stop
  first, neither, average R, and where the price ends up at your flat-by
  time. Sessions are NSE's 9:15 to 15:30 IST (75 bars); a slot with no trade
  is filled flat, and sessions missing more than three slots are left out.
  Simulation from the stock's own history, not a prediction. Use when the
  user says "what are the odds", "replay this trade", "time machine",
  "backtest this setup", "would this have worked", "simulate it", or right
  after /trader-exit writes a plan and before /trader-budget.
argument-hint: "[--until HH:MM] [--replays N] [--seed N]"
---

# trader-timemachine

The Time Machine asks one question: if today plays out like the stock's own
last 60 sessions, how often does this trade hit its target before its stop?
It is a simulation built from the stock's own recent bars, not a prediction.
Day trading loses most people money, and a good-looking replay does not
change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run                    # the trade in trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --until 15:15      # end each replay at your flat-by time
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --seed 7 --replays 20000 --json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --symbol RELIANCE --date 2026-11-13 --entry 1334.00 \
    --stop 1328.80 --target 1344.40 --entry-time "10:05 AM"
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" chart                  # ASCII fan chart of the replays
```

`--now "2026-11-13 10:15"` (IST) pins the clock, `--offline FILE` reads a
saved chart (`.json` or `.json.gz`), `--write` saves `trader/timemachine.json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-exit |
| `trader/timemachine.json` | the result, written by `--write`, read by `chart` |

## How it works

1. Fetch 60 days of 5-minute bars (Yahoo, `RELIANCE.NS`). Keep only FULL sessions before the plan's date: 75
   bars, 9:15 to 15:30 IST. A session with up to three no-trade slots is kept, with each empty slot filled by a
   flat zero-volume bar at the last close. Holidays, short days and today are left out. At least 20 sessions
   are needed.
2. From the entry bar on, build each simulated session by drawing every bar whole from the same time of day
   (plus or minus `--window` bars) in a random past session, scaled to the current price.
3. Walk the bars. The stop is checked before the target in every bar, so a bar that touches both counts as the
   stop (the conservative call).
4. Outcomes: `target` or `stop` (whichever came first), or `neither` when the trade is still open at `--until`
   (default 15:30). `green` = target first, or above the entry at `--until`.
5. The history line: the same rule (opening range, stop distance, 2R target) on each real past session.

## Steps for Claude

1. `timemachine.py run --until 15:15` (the plan's flat-by). Quote the odds as printed.
2. Say what leans where: if the target has to come first in 33% of resolved replays to break even at 2R and it
   did in 26%, say it leans toward the stop.
3. Name the limits: earnings, news and halts can do what 60 sessions never did. Next: `/trader-news` for the
   stock, then `/trader-budget`.

## Example (live, RELIANCE, Fri 2026-11-13)

```
RELIANCE buy, Friday 2026-11-13: entry 1334.00 at 10:05 AM (bar 9), stop 1328.80, target 1344.40 (2R, risk 5.20 a share).
10,000 replays of the rest of the session, 10:05 AM to 3:15 PM (62 five-minute bars), seed 19.

  target first   24.1 %
  stop first     68.2 %
  neither        7.7 %    still open at 3:15 PM
  green          29.6 %   target first, or above the entry at 3:15 PM
  Average R: -0.166

History: the same rule on each of those 59 real sessions fired 32 times: 8 target, 17 stop, 7 neither. Average R -0.002.
Leans toward the stop: at 2R the target has to come first in 33 % of the replays that hit one side; it did in 26 %.
```

## What it never does

It never predicts, never says go or no-go, never uses information from after the entry bar, and never places
or sizes an order. The same seed gives the same numbers.

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
