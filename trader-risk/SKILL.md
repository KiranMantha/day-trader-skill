---
name: trader-risk
description: >-
  Pre-Trade Risk Check. Checks every proposed order against your day-trading
  rules before it goes near Kite and says PASS or BLOCK with the reasons.
  Format (whole lots, MIS only, prices on the 0.05 tick), asset (NSE equity,
  NFO), a stop on the right side, max loss per trade, reward:risk, max daily
  loss, max trades and orders a day, the margin it needs against your funds,
  no entries outside your window (09:30 to 15:00 IST), NSE holidays, no
  duplicates. Exits always get through. Records the verdict against the exact
  order so trader-broker only shows it as ready if THIS order passed today.
  Use when the user says "check this order", "is this trade okay", "run the
  risk check", "can I place this", "am I within my limits", or right after
  /trader-budget writes a ticket.
argument-hint: "[--orders PATH] [--now \"YYYY-MM-DD HH:MM\"]"
---

# trader-risk

The Pre-Trade Risk Check is the gate before Kite. It reads the ticket from
`/trader-budget` and your rules, and answers PASS or BLOCK for each order with
every reason. It checks in file order as if each PASS had filled, so orders
that are fine one by one but break a limit together are caught. It never
places or changes an order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                          # trader/ files, writes trader/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-11-16 10:15" # pin the clock (IST)
python3 "${CLAUDE_SKILL_DIR}/check.py" --orders trader/orders.json --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write               # check without recording the verdicts
```

Exit 0 when every order passes, 1 when any is blocked.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the tickets from trader-budget |
| `trader/config.json` | your rules, in rupees |
| `trader/portfolio.json` | your funds (`cash`) and positions; without it, a fresh account funded with the budget |
| `trader/prices.json` | fresh prices (under 15 minutes old) so a stale plan cannot understate the risk |
| `trader/state/broker.json` | what trader-broker logged as placed today |
| `trader/state/risk.json` | the verdicts, with a fingerprint of each order |

## What blocks

Every order: **format** (missing symbol or side, qty not whole or not a whole number of lots, product other
than MIS, price off the tick, limit without a price), **asset** (not NSE or NFO, F&O when `allow_fno` is
false), **short** (selling more than you hold unless `allow_short`).

An entry, on top: **blocked** list; **size** (trade value under `min_order_inr` or over `max_order_inr`);
**position** (value over `max_position_pct` of the budget: it is above 100 because MIS leverage lets the
value exceed your funds); **margin** (`margin_required` more than your funds less the buffer); **duplicate**
(same symbol and side twice, or already placed today); **daily limit** (`max_orders_per_day`); **stop**
(none while `require_stop`, or on the wrong side); **loss** (qty x (entry - stop) over
`max_loss_per_trade_inr`); **reward:risk** under `min_reward_risk`; **daily loss** (the max losses at the
stops of today's entries plus this one over `max_daily_loss_inr`); **trades** (`max_trades_per_day`);
**window** (before `no_entries_before`, after `no_entries_after`, weekend, NSE holiday, outside 9:15 to 15:30).

There is no pattern-day-trader rule in India and none is checked. Exits are only checked for format, asset
and short sales; every other rule becomes a warning for an exit, because getting out must always be possible.

## Steps for Claude

1. `check.py` after every `size.py --write`. Show each PASS or BLOCK with its reasons.
2. On a BLOCK, say which rule and what would fix it. Never edit the user's config or the ticket to make it pass.
3. On a PASS, say the next step: key it into Kite, then `ticket.py placed`.

## Example (live, 10:00 IST and 15:20 IST)

```
PASS  #1 buy RELIANCE 62 shares, entry
          entry 1340.00 (the plan's entry), stop 1332.05, target 1356.00: risk 7.95 a share
          max loss ₹492.90 (limit ₹500), reward:risk 2.01 (min 1)
1 passed, 0 blocked at 2026-11-13 10:00 IST. Funds after the margin of the passed orders: ₹83,384.

BLOCK #1 buy RELIANCE 62 shares, entry
        - window: no new entries after 15:00 IST (it is 15:20)
```

## What it never does

It never places an order, never loosens a rule, and never says a trade is a good idea: a PASS means the
trade is inside the user's own limits, nothing more. The NSE holiday list covers 2026 only; outside it the
check warns instead of guessing.

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
