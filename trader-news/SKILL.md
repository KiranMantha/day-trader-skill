---
name: trader-news
description: >-
  News Monitor. Watches headlines and NSE corporate announcements for the
  stocks you watch or hold and prints only what is new since the last check,
  newest first, with how far each stock has moved today and a flag on
  results, board outcomes, acquisitions, resignations, rating and SEBI
  items. Reads Yahoo Finance headlines and the exchange filings NSE
  publishes (the company's own words to the exchange), free, one request per
  symbol. Use when the user says "any news on RELIANCE", "what is moving
  INFY", "check the news", "did the company announce anything", "results
  today", "why is it up", or right after /trader-scanner picks a chart and
  before /trader-entry.
argument-hint: "[symbols]"
---

# trader-news

The News Monitor answers one question before you trade a chart: did something
happen that the chart does not show? Results, a board outcome, a rating
action, an acquisition, a resignation, a regulatory notice. It prints what is
new since the last check and nothing else. Headlines are leads, not facts:
open the source before acting.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                                # watchlist + plan + portfolio symbols
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE INFY SBIN
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE --all --hours 72
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-filings                   # headlines only
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-moves --dry-run --json
```

Exit 0 when something new was shown, 1 when nothing was. `--dry-run` leaves
the seen-state alone.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json`, `trader/plan.json`, `trader/portfolio.json` | the symbols, when `--tickers` is not given |
| `trader/state/news.json` | what you have already seen (30 days), so an item shows once |

## Sources

- Yahoo Finance headline RSS (`RELIANCE.NS`, region IN).
- NSE corporate announcements, the last 7 days:
  `nseindia.com/api/corporate-announcements?index=equities&symbol=RELIANCE&from_date=..&to_date=..`.
  NSE refuses a call with no browser-like User-Agent and no Referer; the tool sends both. These are the
  company's own filings: financial results, outcome of board meetings, acquisitions, resignations,
  trading-window closures, credit ratings, penalties. Each has a link to the PDF.
- The move: Yahoo's chart, last price against yesterday's close. A symbol 3% or more off it is flagged.

A `!` marks an item that looks important (results, board outcome, acquisition, resignation, rating,
penalty, delisting, buyback, dividend...). That is a keyword match, not a judgement.

## Steps for Claude

1. Run `news.py --tickers SYMBOL` for the chart the user picked.
2. Lead with anything flagged and anything from NSE (it is the company's own words). Quote the title and
   give the link; do not paraphrase a PDF you have not opened.
3. If a stock is up or down more than 3% with no news, say so: the move is unexplained.
4. If NSE answers with an error, say so and fall back to headlines. Do not guess.

## Example (live, Fri 2026-11-13)

```
INFY   1,139.00 -1.06% vs yesterday's close 1,151.20 at 15:05 IST
RELIANCE 1,340.10 +0.03% vs yesterday's close 1,339.70 at 15:05 IST

  2026-11-12 20:23 IST  RELIANCE    NSE   Reliance Industries Limited: Analysts/Institutional Investor Meet/Con. Call Updates
! 2026-11-12 11:19 IST  INFY        NSE   Infosys Limited: Updates
```

## What it never does

It never reads a filing for you, never says what news means for the price,
never calls an announcement good or bad, and never places or sizes an order.
Outside what NSE publishes (BSE-only announcements, press interviews, social
media) it sees nothing.

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
