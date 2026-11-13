"""trader-news tests. nse-RELIANCE.json is NSE's real corporate-announcements answer (2026-11-13), yahoo-RELIANCE.xml
is Yahoo's RSS, chart-RELIANCE.json a real Yahoo chart."""

import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from _load import load, FIX

news = load("trader-news", "news")
IN = os.path.join(FIX, "india")
NOW = "2026-11-13T05:00:00+00:00"       # 10:30 IST


def read(name):
    with open(os.path.join(IN, name), "rb") as fh:
        return fh.read()


class Parse(unittest.TestCase):
    def test_real_nse_announcement(self):
        items = news.parse_nse_announcements(read("nse-RELIANCE.json"), "RELIANCE")
        self.assertGreaterEqual(len(items), 1)
        it = items[0]
        self.assertEqual((it["source"], it["kind"], it["ticker"]), ("NSE", "filing", "RELIANCE"))
        self.assertTrue(it["id"].startswith("nse:"))
        self.assertIn("Reliance Industries Limited", it["title"])
        self.assertTrue(it["link"].startswith("https://nsearchives.nseindia.com/"))
        # 12-Nov-2026 20:23:38 IST is 14:53:38 UTC
        self.assertEqual(it["time"], datetime.datetime(2026, 11, 12, 14, 53, 38, tzinfo=datetime.timezone.utc))

    def test_importance_is_a_keyword_match_on_the_description(self):
        row = {"seq_id": "1", "desc": "Outcome of Board Meeting", "an_dt": "12-Nov-2026 10:00:00",
               "attchmntText": "Board approved the financial results", "sm_name": "X Ltd", "attchmntFile": "u"}
        quiet = dict(row, seq_id="2", desc="Updates", attchmntText="routine")
        items = news.parse_nse_announcements(json.dumps([row, quiet]), "X")
        self.assertEqual([i["important"] for i in items], [True, False])

    def test_bad_answers(self):
        for bad in ("<html>denied</html>", "{}"):
            with self.assertRaises(news.NewsError):
                news.parse_nse_announcements(bad, "X")

    def test_yahoo_symbol(self):
        self.assertEqual(news.yahoo_symbol("INFY"), "INFY.NS")
        self.assertEqual(news.yahoo_symbol("M&M"), "M&M.NS")
        self.assertEqual(news.yahoo_symbol("^NSEI"), "^NSEI")

    def test_headline_feed_asks_for_india(self):
        self.assertIn("region=IN", news.YAHOO)

    def test_no_sec_left(self):
        self.assertFalse(hasattr(news, "parse_sec_atom"))
        with open(news.__file__) as fh:
            self.assertNotIn("sec.gov", fh.read())


class Run(unittest.TestCase):
    def run_main(self, *extra):
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "news.json")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = news.main(["--tickers", "RELIANCE", "--offline", IN, "--now", NOW, "--hours", "96",
                                "--state", state, "--portfolio", os.path.join(d, "x"),
                                "--watchlist", os.path.join(d, "x"), "--plan", os.path.join(d, "x")] + list(extra))
            again = io.StringIO()
            with contextlib.redirect_stdout(again):
                rc2 = news.main(["--tickers", "RELIANCE", "--offline", IN, "--now", NOW, "--hours", "96", "--state", state,
                                 "--portfolio", os.path.join(d, "x"), "--watchlist", os.path.join(d, "x"),
                                 "--plan", os.path.join(d, "x")] + list(extra))
        return rc, out.getvalue(), rc2, again.getvalue()

    def test_shows_nse_items_once_in_ist(self):
        rc, out, rc2, again = self.run_main("--no-moves")
        self.assertEqual(rc, 0)
        self.assertIn("NSE", out)
        self.assertIn("IST", out)
        self.assertIn("2026-11-12 20:23 IST", out)
        self.assertEqual(rc2, 1)                      # seen already
        self.assertIn("Nothing new", again)

    def test_the_move_line(self):
        _, out, _, _ = self.run_main()
        self.assertIn("RELIANCE", out.splitlines()[0])
        self.assertIn("vs yesterday's close", out)

    def test_no_filings_flag(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "o"))
            out = io.StringIO()
            # a folder with no nse file: with --no-filings nothing is looked for, so no note about NSE
            for n in ("yahoo-RELIANCE.xml", "chart-RELIANCE.json"):
                with open(os.path.join(d, "o", n), "wb") as fh:
                    fh.write(read(n))
            with contextlib.redirect_stdout(out):
                news.main(["--tickers", "RELIANCE", "--offline", os.path.join(d, "o"), "--no-filings", "--dry-run",
                           "--now", NOW, "--state", os.path.join(d, "s.json"), "--portfolio", os.path.join(d, "x"),
                           "--watchlist", os.path.join(d, "x"), "--plan", os.path.join(d, "x")])
        self.assertNotIn("NSE announcements", out.getvalue())

    def test_a_missing_nse_file_is_a_note_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                news.main(["--tickers", "RELIANCE", "--offline", d, "--now", NOW, "--dry-run", "--state",
                           os.path.join(d, "s.json"), "--portfolio", os.path.join(d, "x"),
                           "--watchlist", os.path.join(d, "x"), "--plan", os.path.join(d, "x")])
        self.assertIn("NSE announcements for RELIANCE", out.getvalue())


class Fetch(unittest.TestCase):
    def test_nse_calls_carry_a_browser_agent_and_a_referer(self):
        seen = {}

        class Resp:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"[]"

        class Opener:
            def open(self, req, timeout=None):
                seen.update({k.lower(): v for k, v in req.header_items()})
                seen["url"] = req.full_url
                return Resp()
        f = news.Fetcher(pause=0)
        f._opener = Opener()
        f.get("https://www.nseindia.com/api/x", "n", nse=True)
        self.assertEqual(seen["user-agent"], "Mozilla/5.0")
        self.assertEqual(seen["referer"], "https://www.nseindia.com/")

    def test_http_and_socket_errors_become_news_errors(self):
        f = news.Fetcher(pause=0)

        class Opener:
            def __init__(self, exc):
                self.exc = exc

            def open(self, req, timeout=None):
                raise self.exc
        for exc in (urllib.error.HTTPError("u", 403, "no", {}, None), TimeoutError("read timed out")):
            f._opener = Opener(exc)
            with self.assertRaises(news.NewsError):
                f.get("https://www.nseindia.com/api/x", "n", nse=True)


if __name__ == "__main__":
    unittest.main()
