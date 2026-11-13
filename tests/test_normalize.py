"""Tests for dsterm.normalize on every fixture."""
import glob
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import normalize as N  # noqa: E402

ALL = sorted(glob.glob(os.path.join(_path.SAMPLE, "*"))) + sorted(glob.glob(os.path.join(_path.FIXTURES, "pidgin", "*"))) + [_path.OWN, _path.OWN_CSS] + \
    sorted(glob.glob(os.path.join(_path.FORMATS, "*")))


class TestNormalize(unittest.TestCase):
    def test_every_fixture(self):
        self.assertGreaterEqual(len(ALL), 13)
        for f in ALL:
            with self.subTest(f=os.path.basename(f)):
                ir = N.normalize_paths([f])
                self.assertEqual(ir["ir_version"], 1)
                self.assertTrue(ir["modes"])
                for m, v in ir["modes"].items():
                    self.assertGreater(v["count"], 0, m)
                    for t in v["tokens"]:
                        self.assertRegex(t["value_srgb"], r"^#[0-9a-f]{6}$")
                        self.assertTrue(0.0 <= t["alpha"] <= 1.0)

    def test_harbor_aliases(self):
        ir = N.normalize_paths([os.path.join(_path.SAMPLE, "harbor.tokens.json")])
        toks = {t["name"]: t for t in ir["modes"]["default"]["tokens"]}
        self.assertEqual(toks["color-brand"]["value_srgb"], "#e63e78")
        self.assertIn("aliasOf", toks["color-brand"])
        self.assertAlmostEqual(toks["hb-pink-10"]["alpha"], 0.1, places=3)

    def test_harbor_css_breakpoints(self):
        ir = N.normalize_paths([os.path.join(_path.SAMPLE, "harbor.tokens.css")])
        self.assertEqual(sorted(ir["modes"]), ["default", "root-mobile", "root-tablet"])

    def test_pidgin_dark_extension(self):
        ir = N.normalize_paths([os.path.join(_path.FIXTURES, "pidgin", "pidgin-editorial.dtcg.json")])
        self.assertEqual(sorted(ir["modes"]), ["dark", "light"])
        dark = {t["name"]: t["value_srgb"] for t in ir["modes"]["dark"]["tokens"]}
        self.assertEqual(dark["color.background"], "#211a12")

    def test_css_features(self):
        import tempfile
        css = (":root{--brand:oklch(0.62 0.2 30);--bg:#fff;--fg:var(--ink, #111);--mix:color-mix(in oklab, var(--brand) 50%, white);}"
               "@media (prefers-color-scheme: dark){:root{--bg:#000;--fg:#eee}}")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.css")
            with open(p, "w") as f:
                f.write(css)
            ir = N.normalize_paths([p])
        kinds = sorted(v["kind"] for v in ir["modes"].values())
        self.assertEqual(kinds, ["dark", "light"])


if __name__ == "__main__":
    unittest.main()
