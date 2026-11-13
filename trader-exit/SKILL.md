---
name: trader-exit
description: >-
  Exit Planner. Sets the stop and the target BEFORE you enter, so you know
  when to get out. Stop from the opening-range midpoint, the range low, your
  price, a percent, or a multiple of the ATR; rounded down to the NSE tick
  (Rs 0.05, which Kite enforces). Target at 2R (or 1R, or your price). Refuses
  a stop at or above the entry, a target at or below it, a stop too tight to
  survive the spread, and any short. Sets a flat-by time (15:15 IST by
  default, ahead of Zerodha's MIS auto square-off) and writes trader/plan.json
  for the Time Machine, the sizer, the risk check and the alerts. Use when the
  user says "where is my stop", "set a stop and target", "what is my exit",
  "plan the exit", "2R target", "how much am I risking", or right after
  /trader-entry triggers.
argument-hint: "[--stop or-mid|price:X|pct:X|atr:K] [--target 2R]"
---

# trader-exit

The Exit Planner decides where you are wrong and where you are done before
you buy, when you still think clearly. It writes the plan; it does not place
anything. A stop is a plan, not a guarantee: a gap or a fast market can fill
past it.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                                   # from trader/entry.json: or-mid stop, 2R target
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --write                           # also write trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol RELIANCE --entry 1342.50 --or-high 1340 --or-low 1328.55
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop atr:1.5 --offline RELIANCE.NS.json
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol INFY --entry 1650.25 --setup level --stop pct:1
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                                   # the current trader/plan.json
```

Other flags: `--tick 0.05`, `--flat-by 15:15`, `--json`, `--now "2026-11-13 10:15"`
(IST), `--target 1R|1.5R|price:X`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | the trigger from trader-entry (or give `--symbol` and `--entry`) |
| `trader/config.json` | `flat_by` (15:15), `min_reward_risk` (1.0: a note here, trader-risk enforces it), `tick` (0.05) |
| `trader/plan.json` | the plan, written by `--write` |

## The rules

| stop | meaning |
| --- | --- |
| `or-mid` (orb default) | the opening-range midpoint |
| `or-low` | the opening-range low: wider, so fewer shares for the same max loss |
| `price:X` | your price |
| `pct:X` | X percent under the entry |
| `atr:K` | K times the 14-bar ATR under the entry |

- **Tick.** Kite rejects a price that is not a multiple of the tick: Rs 0.05 for NSE stocks. The stop
  rounds AWAY from the entry to the tick (down, for a long), the target rounds half up to it. A
  few instruments tick at 0.01 or 0.10: pass `--tick`.
- **Refused, with the reason:** a stop at or above the entry, a target at or below it, a risk under 0.05% of
  the price (too tight to survive the spread), an `entry.json` that has not triggered, any short.
- **Flat by.** 15:15 by default. Out by then, win or lose, no overnight hold. Zerodha squares MIS off
  itself a few minutes later and charges for it, so the plan is to beat it.
- **R.** Risk = entry minus stop. The target is entry plus R times that risk.

## Steps for Claude

1. `exit.py plan` after a trigger, or with the user's own numbers.
2. Read the plan back: entry, stop and why, target, risk a share and as a percent, reward:risk, flat-by.
3. Say the stop is set before the entry and is never moved further away.
4. Next: `/trader-timemachine` replays it, then `/trader-budget` sizes it. Nothing was placed.

## Example (RELIANCE, Fri 2026-11-13)

```
Exit plan: RELIANCE long, Fri 2026-11-13, opening-range breakout on 5-minute bars
  Entry         ₹1,342.50 at 10:15 AM
  Stop          ₹1,334.25  opening-range midpoint: (₹1,340.00 + ₹1,328.55) / 2 = ₹1334.275, rounded down
  Target        ₹1,359.00  2R (two times the risk)
  Risk a share  ₹8.25 (0.61% of the entry)
  Reward:risk   2.0
  Flat by       15:15 IST, win or lose: no overnight hold
```

Sizing that: a Rs 500 max loss buys floor(500 / 8.25) = 60 shares.

## What it never does

It never places an order, never moves a stop for you, never picks a stock,
and never promises the target. It plans longs only.

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
