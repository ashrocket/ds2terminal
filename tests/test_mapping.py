"""Tests for mapper + gates: every fixture theme passes every hard gate after repair."""
import glob
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import colorlab as cl  # noqa: E402
from dsterm import gates as G  # noqa: E402
from dsterm import normalize as N  # noqa: E402
from dsterm import roles as R  # noqa: E402
from dsterm import theme as TH  # noqa: E402

FIXTURES = sorted(glob.glob(os.path.join(_path.SAMPLE, "*"))) + [_path.OWN, _path.OWN_CSS] + \
    [os.path.join(_path.FIXTURES, "pidgin", "pidgin-editorial.dtcg.json")] + \
    sorted(glob.glob(os.path.join(_path.FORMATS, "*")))


def themes_for(path, **kw):
    pals, _ = R.extract(N.normalize_paths([path]))
    out = {}
    for mode in ("light", "dark"):
        derived = mode not in pals
        pal = pals.get(mode) or next(iter(pals.values()))
        out[mode] = TH.build(pal, mode, derived, **kw)
    return out


def palette(pairs, mode="light"):
    toks = R.tokens_from_hex_list(pairs)
    kind, _ = R.detect_kind(toks)
    return R.ModePalette(kind or mode, "test", toks, [], [], "test")


class TestFixturesPassGates(unittest.TestCase):
    def test_every_fixture_both_modes(self):
        for f in FIXTURES:
            for mode, th in themes_for(f).items():
                with self.subTest(fixture=os.path.basename(f), mode=mode):
                    self.assertTrue(th["check"]["pass"], th["check"]["failures"])
                    # independent re-check with colorlab directly
                    r = cl.check_theme(G.theme_dict(th["slots"], mode))
                    self.assertEqual(r["failures"], [])


class TestHarborMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.th = themes_for(os.path.join(_path.SAMPLE, "harbor.tokens.json"))

    def test_semantic_slots(self):
        a = self.th["light"]["assignment"]
        self.assertIn(a["red"], ("hb-danger", "hb-danger-fg"))
        self.assertEqual(a["green"], "hb-success-fg")
        self.assertEqual(a["yellow"], "hb-warning-fg")
        # info is purple (hue ~315): hue wins over the name, so it goes to magenta, not blue
        self.assertEqual(a["magenta"], "hb-info-fg")
        self.assertNotEqual(a["blue"], "hb-info-fg")

    def test_no_client_colors(self):
        for mode in ("light", "dark"):
            for k, s in self.th[mode]["slots"].items():
                self.assertNotIn("northwind", s.source, (mode, k))
                self.assertNotIn("primary-brand", s.source, (mode, k))

    def test_dark_is_derived_on_the_heading_ink(self):
        d = self.th["dark"]
        self.assertTrue(d["derived"])
        self.assertEqual(d["slots"]["background"].hex, "#0f2a2e")
        self.assertLessEqual(cl.lc_abs(d["slots"]["foreground"].hex, "#0f2a2e"), 104.0)

    def test_brand_cursor(self):
        # the brand pink is too dim on the dark ground (WCAG 3.5), so the dark cursor is the brand hue lifted
        dc = self.th["dark"]["slots"]["cursor"]
        self.assertEqual(dc.source, "token:color-brand")
        self.assertGreaterEqual(cl.contrast_ratio(dc.hex, "#0f2a2e"), 4.5)
        self.assertIn("color-brand", self.th["light"]["slots"]["cursor"].source)


class TestStressPalettes(unittest.TestCase):
    CASES = {
        "monochrome": [("bg", "#ffffff"), ("text", "#222222"), ("gray-500", "#888888"), ("gray-200", "#dddddd")],
        "two-color": [("primary", "#ff0066"), ("bg", "#101010")],
        "neon": [("bg", "#000000"), ("text", "#ffffff"), ("accent", "#39ff14"), ("danger", "#ff073a"),
                 ("warning", "#ffff00"), ("info", "#00ffff"), ("brand", "#ff00ff")],
        "pastel": [("background", "#fffaf5"), ("text", "#6b6b6b"), ("error", "#ffb3ba"), ("success", "#baffc9"),
                   ("warning", "#ffffba"), ("info", "#bae1ff"), ("accent", "#e0bbff")],
        "very-dark-brand": [("brand", "#0b0b1a"), ("bg", "#f7f7f7"), ("ink", "#0b0b1a")],
        "mid-gray-bg": [("bg", "#808080"), ("text", "#000000"), ("accent", "#0055ff")],
        "same-hue": [("bg", "#fff"), ("text", "#111"), ("red-1", "#ff0000"), ("red-2", "#ee1111"), ("red-3", "#dd2222"),
                     ("red-4", "#cc3333"), ("red-5", "#bb4444"), ("red-6", "#aa5555")],
    }

    def test_all_pass(self):
        for name, pairs in self.CASES.items():
            pal = palette(pairs)
            for mode in ("light", "dark"):
                with self.subTest(case=name, mode=mode):
                    th = TH.build(pal, mode, derived=(pal.kind != mode))
                    self.assertTrue(th["check"]["pass"], th["check"]["failures"])


class TestOverrides(unittest.TestCase):
    def test_set_and_prefer(self):
        path = os.path.join(_path.SAMPLE, "harbor.tokens.json")
        pals, _ = R.extract(N.normalize_paths([path]))
        pal = pals["light"]
        prefer = TH.resolve_prefer(pal, [("fg", "text-heading")], pal.tokens)
        th = TH.build(pal, "light", prefer=prefer, sets=[("blue", "#0000ee"), ("cursor", "#e63e78")])
        self.assertTrue(th["check"]["pass"])
        self.assertIn("text-heading", th["slots"]["foreground"].source)
        self.assertEqual(th["slots"][4].origin, "override")

    def test_bad_role(self):
        with self.assertRaises(TH.OverrideError):
            TH.slot_key("purple")
        with self.assertRaises(TH.OverrideError):
            TH.parse_hex("#12")

    def test_slot_names(self):
        self.assertEqual(TH.slot_key("brightRed"), 9)
        self.assertEqual(TH.slot_key("bright-red"), 9)
        self.assertEqual(TH.slot_key("fg"), "foreground")
        self.assertEqual(TH.slot_key("15"), 15)


if __name__ == "__main__":
    unittest.main()
