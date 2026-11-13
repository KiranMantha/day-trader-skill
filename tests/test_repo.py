import json
import os
import re
import unittest

from _load import ROOT

# the eleven folders of the India edition (trader-pelosi became trader-deals)
SKILLS = ["trader-scanner", "trader-news", "trader-entry", "trader-exit", "trader-timemachine",
          "trader-risk", "trader-budget", "trader-broker", "trader-alerts", "trader-analyst",
          "trader-deals"]
ABOUT = ("11 Claude skills for day trading on the NSE with Zerodha: scan the charts, track announcements and "
         "deals, time every entry and exit, size to Zerodha's MIS margin and charges, and replay every outcome "
         "before you risk a rupee.")
# skills on the way to an order carry the safety block
ORDER_PATH = ["trader-scanner", "trader-entry", "trader-exit", "trader-timemachine", "trader-budget",
              "trader-deals", "trader-risk", "trader-broker", "trader-alerts"]
V1_ONLY = ["trader-copycat", "trader-screener", "trader-tax", "trader-rebalance"]
# words that mean the code or the docs still describe the US pack
US_WORDS = ["alpaca", "place_stock_order", "nasdaqtrader", "edgar", "sec_user_agent", "new york", "nyse",
            "america/new_york", "pelosi", "pdt_guard", "stooq", "tsla", "13f"]


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_eleven_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_root_layout(self):
        root = sorted(d for d in os.listdir(ROOT) if not d.startswith(".git") and d != "__pycache__")
        self.assertEqual(root, sorted([".claude-plugin", "LICENSE", "README.md", "tests"] + SKILLS))

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertRegex(fm, r"description: ", s)
            self.assertGreater(len(fm), 200, "%s description is too thin" % s)
            self.assertGreater(len(text.splitlines()), 60, s)

    def test_order_path_skills_carry_the_safety_rule(self):
        for s in ORDER_PATH:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("not financial advice", low, s)
            self.assertIn("nothing in this pack places an order", low, s)
            self.assertIn("kite", low, s)

    def test_plugin_manifest_points_at_the_root_skills(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            plugin = json.load(fh)
        self.assertEqual(plugin["name"], "day-trader-skill")
        self.assertEqual(plugin["skills"], "./")
        self.assertEqual(plugin["description"], ABOUT)
        for k in ("nse", "zerodha"):
            self.assertIn(k, plugin["keywords"])
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            market = json.load(fh)
        self.assertEqual(market["plugins"][0]["name"], "day-trader-skill")

    def test_readme(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = " ".join(fh.read().split())
        self.assertTrue(readme.startswith("# The Day Trader skill, India edition"))
        self.assertIn(ABOUT, readme)
        self.assertIn("## Fine print", readme)
        for s in SKILLS:
            self.assertIn("/" + s, readme, s)

    def test_no_us_pack_left_in_the_code_or_the_docs(self):
        for path in every_text_file():
            rel = os.path.relpath(path, ROOT)
            if rel.startswith("tests" + os.sep) or rel == "README.md":
                continue   # tests name the old words to assert they are gone; the README has a before/after table
            with open(path, encoding="utf-8", errors="replace") as fh:
                low = fh.read().lower()
            for w in US_WORDS:
                self.assertNotIn(w, low, "%s still says %r" % (rel, w))

    def test_no_dollar_amounts_or_new_york_times_in_the_tools(self):
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in os.listdir(folder):
                if f.endswith((".py", ".md", ".json")):
                    with open(os.path.join(folder, f), encoding="utf-8") as fh:
                        text = fh.read()
                    self.assertNotRegex(text, r"\$\d|\$ ?%[sd.]|\$\{?[A-Z]*\}?\s*(shares|per)", "%s/%s" % (s, f))
                    self.assertNotRegex(text, r"(\d|AM|PM)\s+ET\b|\(ET\)|%s ET\b", "%s/%s" % (s, f))

    def test_no_em_dashes_and_no_personal_email(self):
        for path in every_text_file():
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            rel = os.path.relpath(path, ROOT)
            if not rel.startswith(os.path.join("tests", "fixtures")):
                self.assertNotIn(chr(0x2014), text, rel)
            self.assertNotIn("jakeschincariol" + "@" + "gmail.com", text, rel)

    def test_no_v1_only_skill_is_left_behind(self):
        for path in every_text_file():
            rel = os.path.relpath(path, ROOT)
            if rel.startswith("tests" + os.sep) or rel == "README.md":
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for old in V1_ONLY:
                self.assertNotIn(old, text, rel)

    def test_every_tool_runs_on_python_3_8(self):
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in os.listdir(folder):
                if not f.endswith(".py"):
                    continue
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    src = fh.read()
                for bad in ("import zoneinfo", "from zoneinfo", ".removeprefix(", ".removesuffix(", "match ",
                            "list[", "dict[", "tuple["):
                    if bad == "match ":
                        self.assertNotRegex(src, r"(?m)^\s+match \w+.*:$", "%s/%s" % (s, f))
                    elif bad.endswith("["):
                        self.assertNotRegex(src, r"(?<![\w.])%s" % re.escape(bad), "%s/%s" % (s, f))
                    else:
                        self.assertNotIn(bad, src, "%s/%s" % (s, f))

    def test_tools_never_call_a_broker(self):
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in os.listdir(folder):
                if f.endswith(".py"):
                    with open(os.path.join(folder, f), encoding="utf-8") as fh:
                        src = fh.read()
                    for host in ("kite.zerodha.com", "api.kite.trade/orders", "/orders/regular", "kiteconnect"):
                        self.assertNotIn(host, src, "%s/%s" % (s, f))


class Config(unittest.TestCase):
    def cfg(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            return json.load(fh)

    def test_day_trading_limits_ship_in_the_example_config_in_rupees(self):
        cfg = self.cfg()
        for k in ("max_loss_per_trade_inr", "max_daily_loss_inr", "max_trades_per_day", "min_reward_risk",
                  "require_stop", "no_entries_after", "flat_by", "tick", "product"):
            self.assertIn(k, cfg, k)
        self.assertFalse([k for k in cfg if k.endswith("_usd")])
        self.assertIs(cfg["require_stop"], True)
        self.assertIs(cfg["allow_short"], False)
        self.assertEqual((cfg["broker"], cfg["product"], cfg["tick"]), ("zerodha", "MIS", 0.05))

    def test_the_default_hours_are_nse_hours(self):
        cfg = self.cfg()
        self.assertEqual((cfg["no_entries_before"], cfg["no_entries_after"], cfg["flat_by"]), ("09:30", "15:00", "15:15"))

    def test_no_paper_or_pdt_keys(self):
        for k in ("paper", "pdt_guard", "allow_margin", "fractional", "sec_user_agent"):
            self.assertNotIn(k, self.cfg())

    def test_the_tools_agree_on_the_defaults(self):
        from _load import load
        size, check = load("trader-budget", "size"), load("trader-risk", "check")
        for k, v in self.cfg().items():
            if k == "budget":
                continue
            self.assertEqual(size.DEFAULTS.get(k), v, "size.py %s" % k)
            if k in check.DEFAULTS:
                self.assertEqual(check.DEFAULTS[k], v, "check.py %s" % k)

    def test_example_alerts_load(self):
        with open(os.path.join(ROOT, "trader-alerts", "alerts.example.json")) as fh:
            rules = json.load(fh)["rules"]
        from _load import load
        alerts = load("trader-alerts", "alerts")
        for r in rules:
            alerts.validate(r)


class Calendar(unittest.TestCase):
    def test_every_tool_has_the_same_nse_calendar(self):
        from _load import load
        mods = [load("trader-entry", "entry"), load("trader-exit", "exit"), load("trader-risk", "check"),
                load("trader-scanner", "scan"), load("trader-alerts", "alerts")]
        base = mods[0].NSE_HOLIDAYS
        self.assertEqual(len(base), 20)
        for m in mods:
            self.assertEqual(m.NSE_HOLIDAYS, base, m.__name__)
            self.assertEqual(str(m.OPEN), "09:15:00")
            self.assertEqual(str(m.CLOSE), "15:30:00")
        self.assertEqual(sorted(base)[0], "2026-01-15")
        self.assertTrue(all(k.startswith("2026-") for k in base))


if __name__ == "__main__":
    unittest.main()
