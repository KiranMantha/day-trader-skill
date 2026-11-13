"""A synthetic Yahoo v8 chart for one NSE session (not market data), for tests that need exact bars."""

import datetime
import json

EPOCH = datetime.datetime(1970, 1, 1)


def open_ts(day):
    """Unix seconds of 09:15 IST on `day` (a date)."""
    utc = datetime.datetime.combine(day, datetime.time(9, 15)) - datetime.timedelta(hours=5, minutes=30)
    return int((utc - EPOCH).total_seconds())


def chart(day, bars, symbol="DEMO.NS", step=300, live_tick=None):
    """bars: [(o, h, l, c, v)] from 09:15 IST, one per `step` seconds. None in place of a tuple = a null bar.
    live_tick: (offset_seconds, close) appended like Yahoo's still-forming last point."""
    t0 = open_ts(day)
    ts, o, h, l, c, v = [], [], [], [], [], []
    for i, b in enumerate(bars):
        ts.append(t0 + i * step)
        for arr, x in zip((o, h, l, c, v), b if b else (None,) * 5):
            arr.append(x)
    if live_tick:
        ts.append(t0 + live_tick[0])
        for arr, x in zip((o, h, l, c, v), (live_tick[1],) * 4 + (0,)):
            arr.append(x)
    meta = {"symbol": symbol, "currency": "INR", "timezone": "IST", "gmtoffset": 19800, "previousClose": bars[0][0] if bars and bars[0] else None,
            "regularMarketTime": ts[-1]}
    return json.dumps({"chart": {"result": [{"meta": meta, "timestamp": ts, "indicators": {"quote": [
        {"open": o, "high": h, "low": l, "close": c, "volume": v}]}}], "error": None}})
