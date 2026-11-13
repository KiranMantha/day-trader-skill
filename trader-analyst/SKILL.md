---
name: trader-analyst
description: >-
  Earnings Analyst. Reads a company's last five reported quarters from NSE
  and lays out what changed: revenue, net profit, net margin, EPS, and growth
  against the same quarter a year earlier and the quarter before, in rupees
  crore. Flags the data STALE when the newest quarter NSE returns is more than
  four months old. Standalone figures, not consolidated: the tool says so.
  Banks and finance companies are shown without revenue. Numbers only, never
  a view on the stock. Use when the user says "how did RELIANCE do last
  quarter", "earnings for INFY", "quarterly results", "is profit growing",
  "revenue growth", "what changed in the results", "EPS trend", or before
  trading a stock that is about to report.
argument-hint: "[symbols]"
---

# trader-analyst

The Earnings Analyst reads what a company reported and lays it out as a table.
It does not say whether a stock is a buy. For a day trader the useful part is
small: did the company just report, and was it a surprise in either direction
for the same quarter a year ago? Open the filing before relying on a number.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE
python3 "${CLAUDE_SKILL_DIR}/facts.py" INFY TCS --quarters 5
python3 "${CLAUDE_SKILL_DIR}/facts.py" INFY --json
python3 "${CLAUDE_SKILL_DIR}/facts.py" INFY SBIN --metrics trader/metrics.json
```

`--offline DIR` reads `results-<SYMBOL>.json`; `--today YYYY-MM-DD` pins the
date used for the staleness flag.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/metrics.json` | with `--metrics`: one row per symbol (latest quarter, TTM revenue and profit, EPS, margin, growth), merged in |

## What the data is, honestly

- Source: `nseindia.com/api/results-comparision?symbol=INFY`, free and unofficial. It returns up to five
  quarters as NSE's results filing has them.
- **Standalone, not consolidated.** For a group like Reliance or Infosys the consolidated numbers are much
  bigger. The tool prints "standalone" on every table.
- **It can be old.** When checked on 2026-11-13 the endpoint's newest quarter for INFY, SBIN and others was the
  quarter ended 2024-12-31. A company reports within about 45 days of the quarter's end, so a quarter more
  than 120 days old is printed as STALE. Check `/trader-news` for the latest results announcement, and the
  company's filing, before trusting any figure.
- Amounts are rupees crore (NSE reports lakh; 100 lakh = 1 crore).
- Banks and finance companies file a different layout: revenue and margin are blank, profit and EPS stay.
- Net margin is net profit over revenue. Operating margin is not shown: NSE's layout does not give it
  cleanly across companies.

## Steps for Claude

1. `facts.py SYMBOL`. Quote the table as printed.
2. Lead with the STALE line if there is one.
3. Say what changed in plain words (revenue and profit growth year on year, margin direction), without a
   verdict. Say it is standalone.
4. For a result due today or this week, pair it with `/trader-news`: a day trade is out before an evening
   result, but the next morning's gap is not its business.

## Example (live, Fri 2026-11-13)

```
INFY: NSE standalone quarterly results, rupees crore.
STALE: the newest quarter NSE returned ended 2024-12-31, 682 days ago. Check trader-news for newer results.
  quarter end    revenue       yoy       qoq net profit       yoy       qoq  margin      EPS
  2024-09-30      34,257         -     +2.9%      6,813         -    +18.1%   19.9%    16.38
  2024-12-31      34,915     +7.5%     +1.9%      6,358     -3.0%     -6.7%   18.2%    15.29
```

## What it never does

It never recommends a stock, never forecasts, never compares to estimates (it has none), and never places
or sizes an order. It does not read consolidated results, segment data or the filing PDFs.

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
