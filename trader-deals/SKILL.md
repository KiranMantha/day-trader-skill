---
name: trader-deals
description: >-
  Deals and Insider Tracker. Reads what NSE publishes about big money: the
  last session's bulk deals (a client trading 0.5% or more of a company in a
  day), block deals (large trades in the special window, at least Rs 10
  crore) and short deals, and the insider disclosures promoters, directors
  and designated persons file under SEBI's PIT rules for one stock. Replaces
  the US Congress tracker. Free NSE endpoints, filterable by symbol and size.
  A deal is a fact about the past, not a signal. Use when the user says "any
  bulk deals", "block deals today", "who bought RELIANCE", "did promoters
  buy", "insider buying in INFY", "big money in this stock", "check deals on
  my watchlist", or before trading a stock that jumped on no news.
argument-hint: "[today | insider SYMBOL]"
---

# trader-deals

Deals and Insider Tracker answers: who with real size traded this stock, and
did the people running it buy or sell? It reads two public NSE feeds and
prints them. A bulk deal's other side is often another fund, a promoter's
"sale" can be a pledge, and filings can be late: it is context for a chart,
never a reason to buy.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/deals.py" today                          # last session's bulk, block and short deals
python3 "${CLAUDE_SKILL_DIR}/deals.py" today --symbols RELIANCE INFY  # only these
python3 "${CLAUDE_SKILL_DIR}/deals.py" today --kind block --min-qty 100000
python3 "${CLAUDE_SKILL_DIR}/deals.py" insider RELIANCE               # insider trades, last 90 days
python3 "${CLAUDE_SKILL_DIR}/deals.py" insider SBIN --days 30 --json
```

`--offline DIR` reads `largedeal.json` and `pit-<SYMBOL>.json`; `--show N` sets
rows per kind. Exit 0 when something printed, 1 when nothing did.

## What it reads

NSE's `snapshot-capital-market-largedeal` (the last session's deals) and
`corporates-pit` (insider disclosures for a symbol and a date range). NSE
refuses calls without a browser-like User-Agent and a Referer; the tool sends both.

| word | meaning |
| --- | --- |
| bulk deal | one client traded 0.5% or more of a company's shares in a day |
| block deal | a large trade in the block window, at least Rs 10 crore |
| short deal | short sales reported by brokers: symbol and quantity only |
| insider | a promoter, director or designated person bought or sold; the row comes from their own filing |

`today` is the last published session, not live: it shows yesterday's deals until NSE posts today's after the
close. Insider rows show date, side, quantity, value, who, their category and the mode. Read the mode: an
"Off Market" or "Others" row is often a gift or a transfer between relatives, not a market bet.

## Steps for Claude

1. For a chart the user picked: `deals.py today --symbols SYMBOL`, then `insider SYMBOL --days 90`.
2. Report what is there, with dates and sizes. Say how fresh `today` is.
3. Say what it does not tell them: who was on the other side, why, and whether it was already priced in.
4. Never say "smart money" or "bullish". Never suggest a trade from a deal.

## Example (live, Fri 2026-11-13, data for the 12th)

```
Block deals (2):
  GALLANTT     BUY     4,000,000 sh @ ₹503       SANTOSH KUMAR AGRAWAL
  GALLANTT     SELL    4,000,000 sh @ ₹503       DINESH R AGARWAL
```

One client buying and another selling the same size at the same price: that is one trade, not two.

## What it never does

It never says what a deal means for the price, never follows a person or a fund, never reads a filing's PDF,
and never places or sizes an order.

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
