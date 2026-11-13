"""C11: faint (SGR 2) text gate. The faint color is the measured Terminal blend (colorlab.faint)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import colorlab as cl  # noqa: E402
from dsterm import mapper as M  # noqa: E402
from dsterm import preview as PV  # noqa: E402
from dsterm import report as RP  # noqa: E402
from dsterm import roles as R  # noqa: E402
from dsterm import normalize as N  # noqa: E402
from dsterm import theme as TH  # noqa: E402

HARBOR = os.path.join(_path.SAMPLE, "harbor.tokens.json")


# (text color, background, faint color): drawn by Terminal 2.15 and read from a window capture
# (a drive-and-capture probe, 2026-11-12)
MEASURED = (("#ffffff", "#000000", "#7a7a7a"), ("#000000", "#ffffff", "#a9a9a9"),
            ("#eff0eb", "#2a2f3a", "#858789"), ("#808080", "#2a2f3a", "#505359"),
            ("#000000", "#e0dbc4", "#92907f"), ("#ffffff", "#e0dbc4", "#ebeadb"),
            # chromatic samples: ANSI red, ANSI green and xterm 196 on a dark profile; red on a light one
            ("#ff8174", "#2a2f3a", "#8c5251"), ("#62ff95", "#2a2f3a", "#428c62"), ("#ff0000", "#2a2f3a", "#8c2226"),
            ("#b32c12", "#e0dbc4", "#cf9c87"))


class TestFaintModel(unittest.TestCase):
    def test_blend(self):
        self.assertEqual((cl.DIM_BLEND, cl.DIM_POWER), (0.60, 1.26))
        self.assertEqual(cl.faint("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(cl.faint("#000000", "#ffffff", 1.0), "#ffffff")

    def test_model_agrees_with_terminal(self):
        for color, bg, seen in MEASURED:
            got = cl.parse_hex(cl.faint(color, bg))
            want = cl.parse_hex(seen)
            worst = max(abs(got[i] - want[i]) for i in range(3)) * 255.0
            self.assertLessEqual(worst, 5.0, (color, bg, seen, cl.faint(color, bg)))

    def test_chromatic_faint_moves_toward_the_background(self):
        # the measured rows above are gray and near-gray; no chromatic color is measured in this public suite,
        # so check the model's shape on the Harbor brand pink: every channel moves toward the background
        # and the pair loses contrast
        pink = "#e63e78"
        for bg in ("#ffffff", "#000000", "#0f2a2e"):
            f = cl.faint(pink, bg)
            for i in range(3):
                c, b, g = cl.parse_hex(pink)[i], cl.parse_hex(bg)[i], cl.parse_hex(f)[i]
                self.assertLessEqual(abs(g - b), abs(c - b) + 1e-9, (bg, i))
            self.assertLess(cl.lc_abs(f, bg), cl.lc_abs(pink, bg), bg)

    def test_gate_values(self):
        g = cl.GATES["faint_text"]["gate"]
        self.assertEqual((g["fg_min_lc"], g["fg_min_lc_dark"], g["ansi_min_lc"]), (30.0, 30.0, 15.0))
        t = cl.GATES["faint_text"]["target"]
        self.assertEqual((t["fg_min_lc"], t["fg_min_lc_dark"], t["ansi_min_lc"]), (38.0, 33.0, 20.0))

    def test_old_limits_are_not_reachable(self):
        # the reason for the limits: real faint text is weak
        grays = [cl.to_hex((v / 255.0,) * 3) for v in range(0, 128)]
        best = max(cl.lc_abs(cl.faint("#ffffff", g), g) for g in grays)
        self.assertLess(best, 40.0)                       # dark: faint white never reaches the old 45
        self.assertGreater(best, cl.GATES["faint_text"]["gate"]["fg_min_lc_dark"])
        self.assertLess(cl.lc_abs(cl.faint("#000000", "#ffffff"), "#ffffff"), 47.0)   # light: the best case
        # dark: a faint hue color stays below the old 30, also when it is almost white
        self.assertLess(cl.lc_abs(cl.faint("#ffd5d0", "#0f2a2e"), "#0f2a2e"), 30.0)

    def test_check_theme_fails_dim_colors(self):
        th = {"background": "#1e1e2e", "foreground": "#e0e0e0", "bold": "#e0e0e0", "cursor": "#e0e0e0",
              "selection_background": "#45475a",
              "ansi": ["#45475a", "#e06c75", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
                       "#7f849c", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#a6adc8"]}
        r = cl.check_theme(th)
        faint = [f["detail"] for f in r["failures"] if f["id"] == "faint_text"]
        self.assertTrue(any(d.startswith("faint red") for d in faint), faint)
        self.assertTrue(any(d.startswith("faint foreground") for d in faint), faint)
        self.assertIn("faint_fg_lc", r["metrics"])

    def test_floor_matches_gate(self):
        gate = cl.GATES["faint_text"]["gate"]["ansi_min_lc"]
        for bg, mode in (("#ffffff", "light"), ("#1e1e2e", "dark")):
            v = M.faint_floor(bg, mode)
            hx = M.at_lc(bg, 30.0, 0.12, v, mode == "dark")
            self.assertGreaterEqual(cl.lc_abs(cl.faint(hx, bg), bg), gate)


class TestFaintOutput(unittest.TestCase):
    def test_report_and_preview(self):
        pals, _ = R.extract(N.normalize_paths([HARBOR]))
        th = TH.build(pals["light"], "light")
        rec = RP.theme_record("Harbor Light", "Harbor Light.terminal", th)
        row = [g for g in rec["gates"] if g["gate"] == "faint_text"][0]
        self.assertTrue(row["pass"])
        html = PV.render({"name": "Harbor", "themes": [rec]})
        self.assertIn("faint (SGR 2)", html)
        self.assertIn("Claude Code", html)
        self.assertIn(cl.faint(th["slots"]["foreground"].hex, th["slots"]["background"].hex), html)
        md = RP.to_markdown({"name": "Harbor", "version": "t", "sources": [], "themes": [rec],
                             "font": {"postscript": "x", "size": 13, "note": ""}})
        self.assertIn("### Character", md)
        self.assertIn("### Claude Code", md)
        self.assertIn(rec["claude_code"]["recommend"], ("ansi", "standard"))


if __name__ == "__main__":
    unittest.main()
