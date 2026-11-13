---
name: trader-alerts
description: >-
  Price Alerts and the NSE clock. Watches your trade while you sit in the Kite
  app and notifies you when it matters: the stop, the target, "square off
  MIS" at your flat-by time (15:15 IST, ahead of Zerodha's auto square-off),
  above / below levels, percent moves from the previous close, any time of day
  and the 9:15 opening bell, each ringing once so you are not spammed. `watch`
  stays on until the 15:30 close and raises a desktop notification when a rule
  hits. Knows NSE hours and the 2026 trading holidays, works in IST, fetches
  free delayed quotes from Yahoo one symbol at a time, and writes
  trader/prices.json for sizing and the risk check. Use when the user says
  "alert me when", "tell me if RELIANCE hits", "watch my stop", "watch my
  trade", "ping me before square-off", "remind me to close by 3:15", "is the
  market open", "when does the market open", "get me a price", or right after
  /trader-exit writes a plan.
argument-hint: "[symbol] [price]"
---

# trader-alerts

Price Alerts watches the numbers so the user does not have to stare at a
chart. An alert is information, never an order: when a stop alert rings,
nothing is sold by this skill. The user's stop-loss order sits in Kite and
does the work; the alert says what happened and that it is time to look. Free
quotes are delayed by up to a minute or two, so an alert is never the price
an order will fill at.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # NSE open or closed, next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, square-off time from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 1332.05
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --target 1356.00
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:15 --label "square off MIS"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol SBIN --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" watch                          # stays on to the close, notifies on a hit
python3 "${CLAUDE_SKILL_DIR}/alerts.py" watch --every 20 --no-notify   # poll every 20 s, print only
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # one pass; exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE --write         # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # portfolio + plan symbols
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset reliance-plan-stop
```

`--now "2026-11-16 15:15"` pins the clock (IST); `--offline DIR` reads saved
`yahoo-<SYMBOL>.json` files instead of the network.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-exit, for `add --from-plan` |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder) |
| `trader/state/alerts.json` | which rules rang and when, so each rings once (shared by `check` and `watch`) |
| `trader/prices.json` | the latest quotes, merged in, for trader-budget and trader-risk |
| `trader/portfolio.json` | the symbols held, for `quote --holdings` |

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` / `target` | the price is at or above `price` | never, until `reset` (or `rearm`) |
| `below` / `stop` | the price is at or below `price` | never, until `reset` (or `rearm`) |
| `pct_move` | the price moved `pct` percent from the previous close | once a day |
| `opening_bell` | the NSE opened today (9:15) | once per trading day |
| `time` | the IST clock passed `at` on a trading day | once per trading day |

A rule with a `date` is watched on that IST date only; rules from a plan are for the plan's day.

## `watch`

`watch` is `check` on a loop: each pass reads the quotes, rings what hit, writes the same state file, and
raises a desktop notification (macOS `osascript`, Linux `notify-send`, otherwise the terminal bell). It stops
by itself at the 15:30 close and on Ctrl-C. `--every` is seconds between passes (30, minimum 5): one Yahoo
request per symbol per pass, half a second apart. With `--now` or `--offline` it makes one pass, so it can be
replayed.

## Steps for Claude

1. After `/trader-exit`: `add --from-plan`. The three rules are the stop, the target and the square-off time.
2. If the user wants to be told while they trade in Kite: run `watch` (it needs to stay running; say so).
   Otherwise `check` on request.
3. When something rings, say what it is and that it is information, not an order: the user looks at Kite and
   acts. After they act, `/trader-broker` logs it.
4. The holiday list covers 2026. On another year, say the clock cannot know the holidays.

## What it never does

It never places, cancels or modifies an order, never exits a position, and never treats a delayed quote as a
fill. It does not know about the Diwali Muhurat evening session.

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
