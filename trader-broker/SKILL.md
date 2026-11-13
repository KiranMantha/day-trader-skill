---
name: trader-broker
description: >-
  Order Ticket and Trade Log for Zerodha Kite. There is no broker connection:
  you place every order in the Kite app yourself. This renders each risk-passed
  order as the fields of Kite's order window (exchange, product MIS, quantity,
  price, then the stop-loss trigger and target to place once it fills) with
  the max loss and the margin to expect, refuses to call an order ready unless
  trader-risk passed THIS exact order today, and logs what you placed, skipped
  and filled so the daily limits (max trades, max daily loss, duplicates)
  count correctly. Prints the Kite steps to square off before the MIS auto
  square-off. Use when the user says "show me the ticket", "what do I enter in
  Kite", "I placed it", "log the fill", "close my position", "square off",
  "flatten", "get me out", or right after /trader-risk passes.
argument-hint: "[show | placed | skip | fill | flatten | log]"
---

# trader-broker

Zerodha has no paper account and this pack has no API connection to Kite, so
this skill never places anything. It sits around the one moment that matters:
you reading a ticket, then keying it into Kite yourself. It keeps the
paperwork honest: an order is READY only if trader-risk passed that exact
order today, and everything you tell it you placed or filled is logged so
trader-risk can count it.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every order, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show --index 1 --json
python3 "${CLAUDE_SKILL_DIR}/ticket.py" placed --index 1 --kite-id 2611130012345678
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side buy --qty 62 --price 1340.05
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side sell --qty 62 --price 1332.05
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 62
python3 "${CLAUDE_SKILL_DIR}/ticket.py" skip --index 1 --note "gapped away"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`--now "2026-11-16 10:15"` (IST) pins the clock. Dates are IST dates.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the tickets from trader-budget |
| `trader/state/risk.json` | trader-risk's verdicts, matched to each order by fingerprint |
| `trader/state/broker.json` | the log: placed, skipped, filled (append only) |

## The flow

1. `show`: each ticket in Kite's words, with its status. READY means trader-risk passed this exact order today.
   Anything else says why not (not checked, changed since the check, blocked, already logged).
2. The user keys it into Kite: exchange, product MIS, quantity, order type, price, validity DAY.
3. `placed --index N`: logs it (it refuses an order that is not READY). This is what trader-risk counts.
4. Once the entry fills, the user places the stop-loss order (SL, with the ticket's trigger) and a sell limit at
   the target in Kite. Kite has no bracket orders, so these are two orders and the user cancels the one that
   is left when the other fills. `fill` logs each fill and says whether the symbol is flat.
5. `flatten`: prints the Kite steps to exit before the flat-by time (cancel the open stop and target, then
   Positions > Exit), because Zerodha squares MIS off itself a few minutes after 15:15 and charges for it.

There is no yes-word ceremony here: the user placing the order in Kite is the decision. What this skill
insists on is that Claude shows the ticket, and the risk result, before the user does it.

## Steps for Claude

1. `show`. Read the READY ones aloud in the ticket's words, with the max loss and the margin to expect.
2. If not READY, say why and send the user back to `/trader-risk` or `/trader-budget`. Do not work around it.
3. After the user says they placed it, log it with `placed`. After a fill, `fill`. Never log something the user
   did not say happened.
4. Late in the day, remind them of `flatten` before 15:15.

## What it never does

It never places, modifies or cancels an order, never reads the Kite account, never holds keys, and never
marks an order READY that trader-risk did not pass. Not connecting Zerodha is deliberate; there is nothing
here to configure.

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
