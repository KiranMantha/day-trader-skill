# The Day Trader skill, India edition

11 Claude skills for day trading on the NSE with Zerodha: scan the charts, track announcements and deals, time every entry and exit, size to Zerodha's MIS margin and charges, and replay every outcome before you risk a rupee.

This is an India port of the US day-trader-skill pack (Jake Schincariol, MIT).
Free, no signup, no API key. The tools are plain Python that read free public
data: Yahoo Finance charts, NSE's symbol list, announcements and deals, and
Zerodha's public margin list.

There is no broker connection. You trade in the Kite app; nothing in this
pack can place an order. The pack tells you what to key in, checks it
against your own limits, and taps you on the shoulder while the trade is open.

## Install

Clone the repo and copy the skill folders into Claude Code's skills folder:

```bash
git clone <this repo> day-trader-skill
cp -r day-trader-skill/trader-* ~/.claude/skills/
```

Project-local instead of global: copy the same folders into your repo's
`.claude/skills/`. Claude Code can also load the repo as a plugin from a local
path (`.claude-plugin/` is included). No Claude Code at all? Paste any single
`SKILL.md` at the top of a chat and it runs as a mode; you lose the Python
tools, but the method works.

The tools need Python 3.8 or newer. Nothing to pip install, and nothing to
sign up for.

## What changed from the US pack

| | US pack | India edition |
| --- | --- | --- |
| Market | NYSE and Nasdaq, 9:30 to 16:00 New York | NSE, 9:15 to 15:30 IST (no daylight saving, no early closes) |
| Symbols | AAPL | RELIANCE (read as `RELIANCE.NS`; `.BO` and `^NSEI` pass through) |
| Universe | Nasdaq Trader lists | NSE EQ-series stocks that Zerodha allows on MIS (1,474 of 2,635 listed on 2026-11-13) |
| Money | dollars | rupees, shown with lakh and crore grouping |
| Prices | cents | the exchange tick, Rs 0.05: Kite rejects any other price |
| Cash | your cash balance | the margin Zerodha blocks: `mis_margin` from Zerodha's public list (5x on most stocks) |
| Costs | none | Zerodha's brokerage, STT, exchange fee, SEBI fee, stamp duty and GST, shown at the stop and at the target |
| F&O | none | futures and long options, in whole lots |
| Broker | Alpaca MCP, paper first | none: you place orders in Kite. Zerodha has no paper account |
| Filings | SEC EDGAR 8-Ks | NSE corporate announcements |
| Congress trades | the Pelosi tracker | NSE bulk and block deals and SEBI insider (PIT) disclosures |
| Earnings | SEC XBRL | NSE quarterly results (standalone, and sometimes old: the tool flags it) |
| Pattern day trader rule | optional guard | not applicable, removed |
| Holidays | NYSE 2026 and 2027 | NSE 2026 (refresh the list each year) |

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/trader-scanner` | Chart Scanner | Scans NSE charts for setups: opening-range breakouts, flags, oversold bounces. |
| `/trader-news` | News Monitor | Tracks headlines and NSE announcements on every stock you watch. |
| `/trader-entry` | Entry Timer | Watches a setup bar by bar and tells you the moment to get in. |
| `/trader-exit` | Exit Planner | Sets your stop and your target before you enter, on the 0.05 tick. |
| `/trader-timemachine` | Time Machine | Replays 10,000 simulated sessions plus every past time the setup fired, before you risk a rupee. |
| `/trader-risk` | Risk Manager | Checks every ticket against your limits and your Kite margin, and stops anything over them. |
| `/trader-budget` | Budget Manager | Sizes the trade to your max loss and Zerodha's MIS margin, and shows the round-trip charges. |
| `/trader-broker` | Order Ticket | Shows each ticket as Kite's order window, and logs what you placed and filled. No connection to Zerodha. |
| `/trader-alerts` | Price Alerts | Watches your stop, target and square-off time and sends a desktop notification. |
| `/trader-analyst` | Earnings Analyst | Reads NSE's reported quarters and sums up what changed. |
| `/trader-deals` | Deals Tracker | NSE bulk and block deals and insider trades. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, square off before the auto square-off                   (while it is open)
news / analyst / deals                                                        (on a schedule)
```

A trade, step by step (the numbers are from real runs on 2026-11-13):

1. **`/trader-scanner`** after 9:35 AM IST: stocks that closed above their 15-minute opening range
   (9:15 to 9:30). RELIANCE's range was 1,324.30 to 1,333.40.
2. **`/trader-news RELIANCE`**: new announcements and headlines. A day trade is out before the close, but a
   result or a board outcome can move the stock at the open.
3. **`/trader-entry RELIANCE`** says waiting, then triggered: the first 5-minute close above the range high
   (the 10:00 bar, closing 10:05 AM at 1,334.00).
4. **`/trader-exit`** sets the plan before the entry: stop at the range midpoint, target 2R, flat by 15:15, all
   on the 0.05 tick.
5. **`/trader-timemachine`** replays the rest of the day 10,000 times from RELIANCE's own last 59 sessions. For
   that entry it said: target first 24.1%, stop first 68.2%, and the same rule on the 59 real sessions went
   8 target, 17 stop, 7 neither. A plan that leans toward the stop is information.
6. **`/trader-budget`** with Rs 1,00,000 of margin and a Rs 500 max loss: 500 / 7.95 = 62 shares (value
   Rs 83,080, Kite blocks about Rs 16,616 at 5x). Zerodha's charges for the round trip: about Rs 77, which is
   15% of the max loss. That is why small stops are expensive.
7. **`/trader-risk`** checks the ticket against your limits and your funds. PASS or BLOCK, with the reason.
8. **`/trader-broker show`** prints the ticket as Kite's order window. You key it in. `placed` and `fill` log
   it so the daily limits count.
9. **`/trader-alerts watch`** notifies you on the stop, the target and at 15:15 to square off.

## The tools

All standard-library Python. The data tools read public endpoints and are polite about it.

```bash
python3 trader-scanner/scan.py universe                                # NSE EQ stocks with MIS at Zerodha
python3 trader-scanner/scan.py daily                                   # pre-market setups, whole universe
python3 trader-scanner/scan.py orb --at 10:15                          # opening-range breakouts so far
python3 trader-news/news.py --tickers RELIANCE --hours 12              # headlines, NSE announcements, today's move
python3 trader-entry/entry.py check RELIANCE --setup orb               # waiting / triggered / expired
python3 trader-entry/entry.py watch RELIANCE --every 30                # bar by bar until it triggers
python3 trader-exit/exit.py plan --stop or-mid --target 2R --write     # -> trader/plan.json
python3 trader-timemachine/timemachine.py run --write                  # 10,000 replays + the history
python3 trader-budget/size.py --write                                  # -> trader/orders.json
python3 trader-risk/check.py                                           # PASS / BLOCK per order
python3 trader-broker/ticket.py show                                   # the tickets, READY or not
python3 trader-alerts/alerts.py add --from-plan                        # stop, target, square off
python3 trader-alerts/alerts.py watch                                  # notifies until the close
python3 trader-analyst/facts.py RELIANCE                               # NSE quarters, growth, EPS
python3 trader-deals/deals.py today --symbols RELIANCE                 # bulk and block deals
```

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline on fixtures. The live commands need a network.

## Fine print

**Not financial advice.** This is software that reads public data and does
arithmetic. It does not know your situation and it cannot see the future.
Most people who day trade lose money, and in India SEBI's own studies found
the large majority of individual intraday traders lose. You can lose money.
Decide for yourself, and talk to a SEBI-registered adviser if you need advice.

**Nothing places an order for you.** There is no broker connection. You key
every order into the Kite app, after `/trader-risk` passed that exact ticket.
Zerodha has no paper account, so every ticket is real money.

**Intraday only.** The pack trades MIS, long only, and expects you flat by
15:15 IST. Zerodha squares MIS positions off itself a few minutes later and
charges for it; check Zerodha's support page for the exact times and fee.
Carrying a position overnight is outside this pack.

**Zerodha is the benchmark, and it changes.** Margins, charges and the MIS
list are Zerodha's, read live (margins) or copied from zerodha.com/charges on
2026-11-13 (charges). Check Zerodha's own calculator before relying on a
number: SEBI and the exchanges change fees, and Zerodha changes margins daily.
F&O margins are not guessed: for futures you give the figure Kite shows.

**The Time Machine is a simulation, not a prediction.** It is built from the
stock's own last 60 days of 5-minute bars. The future can do things those 60
days never did: results, a circuit limit, a halt, a headline.

**A stop is a plan, not a guarantee.** In a fast market, across a gap or at a
circuit limit, a stop order can fill well past its price, or not at all. The
max loss shown is the loss at the stop price, before charges.

**The data is free and unofficial.** Yahoo Finance's chart endpoint and NSE's
website APIs are not official APIs: they can lag, change or refuse you. NSE's
quarterly results endpoint returned results only up to December 2024 when
checked, so `/trader-analyst` flags what it finds as stale. Illiquid NSE
stocks often have 5-minute slots with no trade: the scanner skips charts with
gaps. Check anything that matters in Kite before you act on it.

**Taxes.** Intraday equity profits are speculative business income in India
and F&O is non-speculative business income; losses carry forward under
different rules. Nothing here is tax advice.

## Files

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-risk/        SKILL.md, check.py
trader-budget/      SKILL.md, size.py, config.example.json
trader-broker/      SKILL.md, ticket.py
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
trader-analyst/     SKILL.md, facts.py
trader-deals/       SKILL.md, deals.py
tests/              unittest suite + offline fixtures
```

MIT. Original pack by [Jake Schincariol](https://opusjake.ai); India edition on the `india-markets` branch.
