---
name: trader-budget
description: >-
  Position Sizer for Zerodha intraday. Sizes ONE day trade from the plan to
  your budget and your max loss per trade, using Zerodha's own public MIS
  margin list (what Kite actually blocks, 5x on most stocks), the NSE tick
  (Rs 0.05) and F&O lot sizes. Shows Zerodha's round-trip charges (brokerage,
  STT, exchange fee, SEBI fee, stamp duty, GST) at the stop and at the target,
  and writes one order ticket to trader/orders.json. Refuses when the stop is
  too far for your max loss, the symbol has no MIS, or reward:risk is under
  your minimum. Never places anything. Use when the user says "how many shares
  can I buy", "size this trade", "how much can I risk", "position size", "how
  much margin will this take", "what are the charges", "how many lots", or
  right after /trader-timemachine.
argument-hint: "[--budget N] [--limit PRICE] [--segment equity|futures|options]"
---

# trader-budget

The Position Sizer turns a plan into a quantity. The one number that rules is
your max loss per trade: shares = max loss / risk per share, then trimmed by
the position cap, the max order value and the margin Kite will block. It is
all whole shares (or whole lots in F&O), and it writes a ticket, never an order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                                  # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                          # also write trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit                          # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit 1342.50 --write          # a limit order at 1342.50
python3 "${CLAUDE_SKILL_DIR}/size.py" --segment futures --lot-size 65 --margin-per-lot 180000
python3 "${CLAUDE_SKILL_DIR}/size.py" --segment options --lot-size 65
```

`--budget N` overrides the config, `--margins FILE` reads a saved copy of
Zerodha's list, `--margin-pct 20` overrides it for one symbol, `--tick`,
`--now "2026-11-16 10:15"` (IST), `--json`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-exit |
| `trader/config.json` | your rules (`config.example.json` in this folder), amounts in rupees |
| `trader/prices.json` | a fresh price (under 15 minutes old): a market order is sized at the higher of it and the plan's entry |
| `trader/orders.json` | the proposed ticket, written by `--write` |

## The sizing

`budget` is the margin in your Kite account (Funds), not a target position value.

```
qty = floor of the smallest of
  max loss      max_loss_per_trade_inr / (entry - stop)
  position cap  budget x max_position_pct (of trade VALUE) / entry
  max order     max_order_inr / entry
  margin        (budget - cash buffer) / margin per share
```

- **Equity margin** is entry x `mis_margin`%, from Zerodha's public list
  (`api.kite.trade/margins/equity`: `mis_margin` 20 means 5x). A symbol missing from it has no MIS:
  no order. The list is read live; `--margins FILE` uses a saved copy.
- **A long option** needs the full premium. **A future** needs `--margin-per-lot`, the figure Kite shows in
  its order window: SPAN margins change daily and this tool does not guess them.
- **Lots.** F&O quantities are whole lots (`--lot-size`; Kite's order window shows it).
- **Tick.** Prices are rounded to the tick (0.05) because Kite rejects any other.
- **Charges** use Zerodha's published schedule (zerodha.com/charges): brokerage min(Rs 20, 0.03%) a leg on
  equity and futures, flat Rs 20 on options, STT on the sell side (0.025% equity intraday), exchange fee,
  SEBI Rs 10 per crore, stamp duty on the buy side, 18% GST on brokerage, exchange and SEBI fees. They are
  shown at the stop and at the target and are not in the sizing: the max loss is the gross move, so on a
  small stop the charges are a real share of it. Zerodha's own calculator is the reference.
- **Refusals** (exit 1, no ticket): zero units (the stop is too far for the max loss), no MIS for the symbol,
  reward:risk under `min_reward_risk`, an order under `min_order_inr`, a stop above the entry.

## Steps for Claude

1. Run `size.py --write` (add `--limit` if the user wants a limit order).
2. Read it back: the binding limit, quantity, value, margin Kite should block, max loss, max gain, and the
   charges with the net figures.
3. If it refused, say why in one line and what would change it. Do not loosen the user's rules.
4. Next: `/trader-risk` checks the ticket. Nothing has been placed.

## Example (RELIANCE, live margin list, Fri 2026-11-13)

```
Limits (whole shares; the smallest one wins):
  max loss      ₹500 max loss / 7.95 risk a share                                  62  <- binds
  position cap  500% of ₹1,00,000 = ₹5,00,000 / 1340.00                          373
  max order     ₹5,00,000 / 1340.00                                               373
  margin        budget ₹1,00,000 minus ₹10,000 buffer = ₹90,000 / ₹268 (RELIANCE MIS margin 20%)  335

Size: 62 shares of RELIANCE, value ₹83,080, margin Kite blocks about ₹16,616. Max loss at the stop: 62 x 7.95 = ₹492.90
  at stop    ₹76.55  (brokerage ₹40, STT ₹20.65, exchange ₹5.09, GST ₹8.15, stamp ₹2.49, SEBI ₹0.17)
Net after charges: ₹569.45 lost at the stop, ₹915.04 gained at the target.
```

## What it never does

It never places an order, never talks to Zerodha beyond reading its public margin list, never raises
your limits, never sizes a short, and never invents an F&O margin.

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
