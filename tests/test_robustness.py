"""Regression tests for the C9 adversarial review (input safety, names, new gate rules)."""
import os
import plistlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import colorlab as cl  # noqa: E402
from dsterm import fetch as F  # noqa: E402
from dsterm import gates as G  # noqa: E402
from dsterm import normalize as N  # noqa: E402
from dsterm import report as RP  # noqa: E402
from dsterm import roles as R  # noqa: E402
from dsterm import terminal as T  # noqa: E402
from dsterm import theme as TH  # noqa: E402


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class TestPathologicalInput(unittest.TestCase):
    def test_regex_inputs_are_fast(self):
        cases = {
            "a.css": ":root{--bg:#ffffff;--fg:#111111;/*" + " " * 8000 + "}",
            "b.css": ":root{--bg:#fff;--a:" + "-" * 40000 + "}",
            "c.html": "<html><style>" + "<style" * 100000 + "</html>",
            "d.json": "[" * 10000,
        }
        with tempfile.TemporaryDirectory() as d:
            for name, text in cases.items():
                p = write(d, name, text)
                t0 = time.time()
                N.normalize_paths([p])
                self.assertLess(time.time() - t0, 5.0, name)

    def test_css_description_still_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "t.css", ":root{--brand:#e63e78; /* Brand orange */ --bg:#fff;}")
            toks = N.normalize_paths([p])["modes"]["default"]["tokens"]
        self.assertEqual(toks[0].get("description"), "Brand orange")

    def test_fetch_refuses_non_http_and_private_hosts(self):
        f = F.Fetcher(timeout=2)
        for u in ("file:///etc/hostname", "http://127.0.0.1:1/x", "http://localhost/x", "http://10.0.0.1/x"):
            st, _h, body, _u, err = f.get(u)
            self.assertEqual((st, body), (0, b""), u)
            self.assertIn("refused", err)

    def test_safe_name(self):
        a, b = F.safe_name("a b.json"), F.safe_name("a_b.json")
        self.assertNotEqual(a, b)
        for p in ("..", ".", "../../x"):
            self.assertNotIn("/", F.safe_name(p))
            self.assertFalse(F.safe_name(p).startswith("."))


class TestNames(unittest.TestCase):
    def test_xml_illegal_characters(self):
        n = T.clean_name("T￾￿\ud800<i>")
        data = T.dumps_profile(T.build_profile(n, dict((k, "#123456") for k in T.COLOR_KEYS)))
        self.assertEqual(plistlib.loads(data)["name"], "T <i>")

    def test_long_name_keeps_mode_suffix(self):
        base = T.cap_name("x" * 300)
        light, dark = T.safe_filename(base + " Light"), T.safe_filename(base + " Dark")
        self.assertNotEqual(light, dark)
        self.assertEqual(light[:-len(".terminal")], base + " Light")

    def test_markdown_escape(self):
        self.assertEqual(RP._md_escape("<b>a|b`c</b>\r"), "&lt;b&gt;a\\|b'c&lt;/b&gt; ")


class TestExtraGateRules(unittest.TestCase):
    def test_selection_visible_on_black(self):
        pal = R.ModePalette("dark", "t", R.tokens_from_hex_list(
            [("bg", "#000000"), ("text", "#ffffff"), ("accent", "#39ff14"), ("brand", "#ff00ff")]), [], [], "t")
        th = TH.build(pal, "dark")
        self.assertTrue(th["check"]["pass"])
        self.assertGreaterEqual(cl.contrast_ratio(th["slots"]["selection"].hex, "#000000"), 1.10)

    def test_hue_vs_text_rule(self):
        pal = R.ModePalette("light", "t", R.tokens_from_hex_list(
            [("background", "#fffaf5"), ("text", "#6b6b6b"), ("info", "#bae1ff"), ("accent", "#e0bbff")]), [], [], "t")
        th = TH.build(pal, "dark", derived=True)
        self.assertTrue(th["check"]["pass"])
        fg = th["slots"]["foreground"].hex
        for i in list(range(1, 7)) + list(range(9, 15)):
            self.assertGreaterEqual(cl.delta_e_ok_rgb(th["slots"][i].hex, fg), G.HUE_VS_TEXT_MIN_DE)

    def test_mid_tone_background_is_kept_or_noted(self):
        pal_toks = R.tokens_from_hex_list([("background", "#0047ab"), ("text", "#ffffff"), ("accent", "#ffcc00")])
        pals, _ = R.extract({"modes": {"d": {"tokens": [{"name": t.name, "value_srgb": t.hex, "alpha": 1.0}
                                                         for t in pal_toks]}}})
        th = TH.build(pals["dark"], "dark")
        self.assertTrue(th["check"]["pass"])
        # since C11 the faint floors (Lc 77-82 on cobalt) leave too little room below white (Lc 93):
        # the background may be replaced, but then the repair log must say so
        if th["slots"]["background"].hex != "#0047ab":
            self.assertTrue(any(r.startswith("background #0047ab ->") for r in th["repairs"]), th["repairs"])


if __name__ == "__main__":
    unittest.main()
