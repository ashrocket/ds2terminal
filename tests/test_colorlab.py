"""Unit tests for dsterm.colorlab against published reference values."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402,F401
from dsterm import colorlab as cl  # noqa: E402
from ciede2000_sharma_data import SHARMA_2005  # noqa: E402


class TestSRGB(unittest.TestCase):
    def test_roundtrip_linear(self):
        for v in (0.0, 0.01, 0.04045, 0.2, 0.5, 0.99, 1.0, -0.3, 1.2):
            # 1e-7: the IEC curve has a known ~3e-8 discontinuity at the 0.04045/0.0031308 knee
            self.assertAlmostEqual(cl.linear_to_srgb_channel(cl.srgb_to_linear_channel(v)), v, delta=1e-7)

    def test_known_linear(self):
        # sRGB 0.5 -> 0.21404114048223255 (IEC 61966-2-1 curve)
        self.assertAlmostEqual(cl.srgb_to_linear_channel(0.5), 0.21404114048223255, places=12)
        self.assertAlmostEqual(cl.srgb_to_linear_channel(0.04045), 0.04045 / 12.92, places=15)

    def test_hex(self):
        self.assertEqual(cl.to_hex(cl.parse_hex("#1E1e2e")), "#1e1e2e")
        self.assertEqual(cl.to_hex(cl.parse_hex("#abc")), "#aabbcc")


class TestOKLab(unittest.TestCase):
    # Ottosson's table, https://bottosson.github.io/posts/oklab/ (3 decimals)
    OTTOSSON = [
        ((0.950, 1.000, 1.089), (1.000, 0.000, 0.000)),
        ((1.000, 0.000, 0.000), (0.450, 1.236, -0.019)),
        ((0.000, 1.000, 0.000), (0.922, -0.671, 0.263)),
        ((0.000, 0.000, 1.000), (0.153, -1.415, -0.449)),
    ]

    def test_ottosson_xyz_table(self):
        for xyz, lab in self.OTTOSSON:
            got = cl.xyz_to_oklab(xyz)
            for g, e in zip(got, lab):
                self.assertAlmostEqual(g, e, delta=0.0011, msg="%r -> %r vs %r" % (xyz, got, lab))

    def test_white_black(self):
        L, a, b = cl.srgb_to_oklab("#ffffff")
        self.assertAlmostEqual(L, 1.0, places=6)
        self.assertLess(abs(a), 1e-4)
        self.assertLess(abs(b), 1e-4)
        self.assertEqual(cl.srgb_to_oklab("#000000"), (0.0, 0.0, 0.0))

    def test_css_color4_examples(self):
        # CSS Color 4 Overview.bs examples (rgb percentages rounded to 0.01%)
        cases = [
            ((0.4906, 0.1387, 0.1590), (0.40101, 0.1147, 0.0453)),
            ((0.7761, 0.3634, 0.0245), (0.59686, 0.1009, 0.1192)),
            ((0.6165, 0.5751, 0.0928), (0.65125, -0.0320, 0.1274)),
            ((0.4073, 0.6512, 0.2235), (0.66016, -0.1084, 0.1114)),
            ((0.3829, 0.6727, 0.9385), (0.72322, -0.0465, -0.1150)),
        ]
        for rgb, lab in cases:
            got = cl.srgb_to_oklab(rgb)
            for g, e in zip(got, lab):
                self.assertAlmostEqual(g, e, delta=0.0006, msg="%r -> %r vs %r" % (rgb, got, lab))
        L, C, h = cl.srgb_to_oklch((0.4906, 0.1387, 0.1590))
        self.assertAlmostEqual(L, 0.40101, delta=0.0005)
        self.assertAlmostEqual(C, 0.12332, delta=0.0005)
        self.assertAlmostEqual(h, 21.555, delta=0.3)

    def test_srgb_red_oklch(self):
        # color.js / CSS: #f00 = oklch(62.796% 0.25768 29.2339)
        L, C, h = cl.srgb_to_oklch("#ff0000")
        self.assertAlmostEqual(L, 0.62796, delta=0.0002)
        self.assertAlmostEqual(C, 0.25768, delta=0.0002)
        self.assertAlmostEqual(h, 29.2339, delta=0.02)

    def test_roundtrip(self):
        for hx in ("#1e1e2e", "#f38ba8", "#00ff00", "#0000ff", "#808080", "#fdf6e3"):
            rgb = cl.parse_hex(hx)
            back = cl.oklch_to_srgb(cl.srgb_to_oklch(rgb))
            for a, b in zip(rgb, back):
                self.assertAlmostEqual(a, b, places=9)

    def test_gray_hue_nan(self):
        L, C, h = cl.srgb_to_oklch("#777777")
        self.assertTrue(math.isnan(h))


class TestCIELab(unittest.TestCase):
    def test_css_lab_example(self):
        # CSS Color 4: rgb(49.06% 13.87% 15.9%) = lab(29.2345% 39.3825 20.0664)
        L, a, b = cl.srgb_to_cielab_d50((0.4906, 0.1387, 0.1590))
        self.assertAlmostEqual(L, 29.2345, delta=0.02)
        self.assertAlmostEqual(a, 39.3825, delta=0.05)
        self.assertAlmostEqual(b, 20.0664, delta=0.05)

    def test_ciede2000_sharma(self):
        for row in SHARMA_2005:
            got = cl.ciede2000(row[0:3], row[3:6])
            self.assertAlmostEqual(got, row[6], delta=0.00005, msg="row %r got %r" % (row, got))
            # symmetric
            self.assertAlmostEqual(cl.ciede2000(row[3:6], row[0:3]), row[6], delta=0.00005)


class TestWCAG(unittest.TestCase):
    def test_extremes(self):
        self.assertAlmostEqual(cl.contrast_ratio("#000", "#fff"), 21.0, places=9)
        self.assertAlmostEqual(cl.contrast_ratio("#fff", "#fff"), 1.0, places=9)

    def test_threshold_pair(self):
        # #777 on white fails AA (4.48), #767676 passes (4.54)
        self.assertAlmostEqual(cl.contrast_ratio("#777777", "#ffffff"), 4.4776, delta=0.001)
        self.assertAlmostEqual(cl.contrast_ratio("#767676", "#ffffff"), 4.5422, delta=0.001)
        self.assertLess(cl.contrast_ratio("#777777", "#ffffff"), 4.5)
        self.assertGreater(cl.contrast_ratio("#767676", "#ffffff"), 4.5)

    def test_symmetric(self):
        self.assertEqual(cl.contrast_ratio("#123456", "#abcdef"), cl.contrast_ratio("#abcdef", "#123456"))


class TestAPCA(unittest.TestCase):
    # apca-w3 0.0.98G-4g reference values (SAPC-APCA known values; README -68.541)
    def test_reference_pairs(self):
        self.assertAlmostEqual(cl.apca_lc("#888888", "#ffffff"), 63.056, delta=0.01)
        self.assertAlmostEqual(cl.apca_lc("#ffffff", "#888888"), -68.541, delta=0.01)
        self.assertAlmostEqual(cl.apca_lc("#000000", "#aaaaaa"), 58.146, delta=0.01)
        self.assertAlmostEqual(cl.apca_lc("#aaaaaa", "#000000"), -56.24, delta=0.01)

    def test_extremes(self):
        self.assertAlmostEqual(cl.apca_lc("#000000", "#ffffff"), 106.04, delta=0.01)
        self.assertAlmostEqual(cl.apca_lc("#ffffff", "#000000"), -107.88, delta=0.01)
        self.assertEqual(cl.apca_lc("#777777", "#777777"), 0.0)

    def test_order_matters(self):
        self.assertGreater(cl.apca_lc("#222222", "#eeeeee"), 0)
        self.assertLess(cl.apca_lc("#eeeeee", "#222222"), 0)

    def test_y_uses_simple_exponent(self):
        k = 0.2126729 + 0.7151522 + 0.0721750  # = 1.0000001 in apca-w3
        self.assertAlmostEqual(cl.apca_y("#808080"), k * (128 / 255.0) ** 2.4, places=12)


class TestGamutMap(unittest.TestCase):
    def test_in_gamut_untouched(self):
        rgb = cl.parse_hex("#3366cc")
        out = cl.gamut_map_oklch(cl.srgb_to_oklch(rgb))
        for a, b in zip(rgb, out):
            self.assertAlmostEqual(a, b, places=9)

    def test_out_of_gamut(self):
        for lch in ((0.7, 0.4, 145.0), (0.6, 0.35, 29.0), (0.5, 0.3, 264.0), (0.9, 0.3, 100.0),
                    (0.3, 0.25, 320.0)):
            self.assertFalse(cl.in_srgb_gamut(cl.oklch_to_srgb(lch)))
            out = cl.gamut_map_oklch(lch)
            self.assertTrue(cl.in_srgb_gamut(out, eps=0.0))
            L, C, h = cl.srgb_to_oklch(out)
            # lightness roughly preserved; chroma reduced; hue roughly kept
            self.assertLess(abs(L - lch[0]), 0.03, msg=repr((lch, (L, C, h))))
            self.assertLess(C, lch[1])
            self.assertLess(cl.hue_diff(h, lch[2]), 6.0, msg=repr((lch, (L, C, h))))

    def test_extremes(self):
        self.assertEqual(cl.gamut_map_oklch((1.2, 0.1, 30.0)), (1.0, 1.0, 1.0))
        self.assertEqual(cl.gamut_map_oklch((0.0, 0.1, 30.0)), (0.0, 0.0, 0.0))


class TestCVD(unittest.TestCase):
    def test_rows_sum_to_one(self):
        for kind, M in cl.MACHADO_2009.items():
            for row in M:
                self.assertAlmostEqual(sum(row), 1.0, delta=0.0011, msg=kind)

    def test_gray_invariant(self):
        for kind in cl.MACHADO_2009:
            for hx in ("#000000", "#777777", "#ffffff"):
                out = cl.simulate_cvd(hx, kind)
                rgb = cl.parse_hex(hx)
                for a, b in zip(rgb, out):
                    self.assertAlmostEqual(a, b, delta=0.002)

    def test_colorspacious_gold_deut50(self):
        # colorspacious gold_values.CVD_deut50_to_sRGB1_silver, Machado deuteranomaly severity 50
        deut50 = ((0.547494, 0.607765, -0.155259),
                  (0.181692, 0.781742, 0.036566),
                  (-0.010410, 0.027275, 0.983136))
        cases = [((0.1, 0.2, 0.3), (0.12440528, 0.19103024, 0.29911687)),
                 ((0.9, 0.5, 0.3), (0.76726301, 0.59528358, 0.29263454))]
        for src, exp in cases:
            got = cl.simulate_cvd(src, "deutan", matrix=deut50)
            for g, e in zip(got, exp):
                self.assertAlmostEqual(g, e, delta=1e-6)

    def test_red_green_collapse(self):
        # Under deuteranopia pure red and green move much closer together
        d0 = cl.delta_e_ok_rgb("#cc3333", "#33aa33")
        d1 = cl.delta_e_ok_rgb(cl.simulate_cvd("#cc3333", "deutan"), cl.simulate_cvd("#33aa33", "deutan"))
        self.assertLess(d1, d0 * 0.6)


class TestHelpers(unittest.TestCase):
    def test_hue_diff(self):
        self.assertAlmostEqual(cl.hue_diff(350, 10), 20)
        self.assertAlmostEqual(cl.hue_diff(10, 350), 20)
        self.assertAlmostEqual(cl.hue_diff(0, 180), 180)


class TestGates(unittest.TestCase):
    SYNTH_DARK = {"background": "#1b1f29", "foreground": "#e3e7f1", "bold": "#e3e7f1", "cursor": "#a1d4ff",
                  "selection_background": "#2a3c52",
                  "ansi": ["#2c303b", "#ff909b", "#bcee88", "#fcd276", "#79beff", "#fba0f3", "#71dedd", "#d1d4dc",
                           "#9499a6", "#ffa7ae", "#c9fb95", "#ffe287", "#93ccff", "#ffb3ff", "#7febea", "#edeff5"]}
    SOLARIZED_DARK = {"background": "#002b36", "foreground": "#839496", "cursor": "#839496",
                      "selection_background": "#073642",
                      "ansi": ["#073642", "#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198", "#eee8d5",
                               "#002b36", "#cb4b16", "#586e75", "#657b83", "#839496", "#6c71c4", "#93a1a1", "#fdf6e3"]}

    def test_synthetic_passes(self):
        r = cl.check_theme(self.SYNTH_DARK)
        self.assertEqual(r["mode"], "dark")
        # the research theme was built before the faint_text gate (C11). With the measured blend its
        # hue colors pass; its text #e3e7f1 is 0.04 Lc below the faint text gate. Every other gate passes.
        self.assertEqual(r["failed_gate_ids"], ["faint_text"], r["failures"])
        self.assertEqual(len(r["failures"]), 1, r["failures"])
        self.assertTrue(r["failures"][0]["detail"].startswith("faint foreground"))

    def test_solarized_fails_expected(self):
        r = cl.check_theme(self.SOLARIZED_DARK)
        self.assertFalse(r["pass"])
        for gid in ("fg_contrast", "ansi_normal", "dim_brightBlack", "bright_relation", "selection"):
            self.assertIn(gid, r["failed_gate_ids"])
        self.assertEqual(r["metrics"]["brightBlack_lc"], 0.0)

    def test_selection_equal_fg_fails(self):
        t = dict(self.SYNTH_DARK)
        t["selection_background"] = t["foreground"]
        r = cl.check_theme(t)
        self.assertIn("selection", r["failed_gate_ids"])


if __name__ == "__main__":
    unittest.main()
