"""C10: opaque by default; --translucent ALPHA is gated over a black and a white desktop."""
import json
import os
import plistlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import colorlab as cl  # noqa: E402
from dsterm import gates as G  # noqa: E402
from dsterm import normalize as N  # noqa: E402
from dsterm import roles as R  # noqa: E402
from dsterm import terminal as T  # noqa: E402
from dsterm import theme as TH  # noqa: E402
from test_cli import HARBOR, read, run  # noqa: E402

TRANSLUCENT_FIXTURES = [HARBOR, _path.OWN,
                        os.path.join(_path.FIXTURES, "pidgin", "pidgin-editorial.dtcg.json")]


class TestCompositeGate(unittest.TestCase):
    THEME = {"background": "#fafafa", "foreground": "#24292f", "bold": "#24292f", "cursor": "#0969da",
             "selection_background": "#ddf4ff",
             "ansi": ["#24292f", "#cf222e", "#116329", "#4d2d00", "#0969da", "#8250df", "#1b7c83", "#6e7781",
                      "#57606a", "#a40e26", "#1a7f37", "#633c01", "#218bff", "#a475f9", "#3192aa", "#8c959f"]}

    def test_composites(self):
        self.assertEqual(cl.translucent_backgrounds("#ffffff", 1.0), [])
        self.assertEqual(cl.translucent_backgrounds("#ffffff", 0.5), [("#000000", "#808080"), ("#ffffff", "#ffffff")])

    def test_low_alpha_fails_over_black_desktop(self):
        th = dict(self.THEME, background_alpha=0.5)
        r = cl.check_theme(th)
        self.assertIn("fg_contrast", r["failed_gate_ids"])
        over_black = [f for f in r["failures"] if f.get("desktop") == "#000000"]
        self.assertTrue(over_black)
        self.assertFalse([f for f in r["failures"] if not f.get("desktop") and f["id"] == "fg_contrast"])
        rows = r["metrics"]["translucency"]["desktops"]
        self.assertEqual([x["desktop"] for x in rows], ["#000000", "#ffffff"])

    def test_alpha_zero_is_not_opaque(self):
        r = cl.check_theme(dict(self.THEME, background_alpha=0.0))
        self.assertFalse(r["pass"])


class TestTranslucentBuild(unittest.TestCase):
    def test_fixtures_pass_at_095(self):
        for f in TRANSLUCENT_FIXTURES:
            pals, _ = R.extract(N.normalize_paths([f]))
            for mode in ("light", "dark"):
                pal = pals.get(mode) or next(iter(pals.values()))
                with self.subTest(fixture=os.path.basename(f), mode=mode):
                    th = TH.build(pal, mode, mode not in pals, alpha=0.95)
                    self.assertTrue(th["check"]["pass"], th["check"]["failures"])
                    td = G.theme_dict(th["slots"], mode)
                    self.assertEqual(td["background_alpha"], 0.95)
                    self.assertEqual(cl.check_theme(td)["failures"], [])

    def test_set_fg_survives_background_rebuild(self):
        # review B1: the rebuild on a standard background dropped --set fg
        pals, _ = R.extract(N.normalize_paths([HARBOR]))
        # the gray page color cannot carry the theme at this alpha (the white card surface can)
        page = [t for t in pals["light"].tokens if t.name == "surface-page"][0]
        th = TH.build(pals["light"], "light", prefer={"bg": page}, sets=[("fg", "#222222")], alpha=0.90)
        self.assertTrue(any("every slot was mapped again" in r for r in th["repairs"]))
        self.assertEqual(th["slots"]["foreground"].hex, "#222222")
        self.assertEqual(th["slots"]["foreground"].origin, "override")

    def test_light_090_band_closes(self):
        # faint colors must be dark enough over the black desktop and light enough for black text on them
        self.assertEqual(TH.min_alpha("#fafafa", "light"), 0.88)
        self.assertFalse(TH.bg_feasible("#fafafa", "light", 0.85))
        self.assertTrue(TH.bg_feasible("#fafafa", "light", 0.95))

    def test_too_low_alpha_fails_with_advice(self):
        pals, _ = R.extract(N.normalize_paths([HARBOR]))
        th = TH.build(pals["light"], "light", alpha=0.4)
        self.assertFalse(th["check"]["pass"])
        self.assertTrue(any("passes (checked" in n for n in th["notes"]), th["notes"])


class TestCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _profile(self, out, mode="Light"):
        with open(os.path.join(out, "Harbor %s.terminal" % mode), "rb") as fh:
            return plistlib.load(fh)

    def test_opaque_default(self):
        out = os.path.join(self.tmp, "opaque")
        rc, _o, err = run(HARBOR, "--name", "Harbor", "--out", out, "--quiet", "--no-preview")
        self.assertEqual(rc, 0, err)
        for mode in ("Light", "Dark"):
            prof = self._profile(out, mode)
            self.assertEqual(prof["BackgroundBlur"], 0.0)
            self.assertEqual(T.decode_color(prof["BackgroundColor"])[3], 1.0)
        self.assertIn("| translucency | pass | opaque (alpha 1, blur 0)", read(os.path.join(out, "report.md")))

    def test_translucent_flag(self):
        out = os.path.join(self.tmp, "t90")
        rc, _o, err = run(HARBOR, "--name", "Harbor", "--out", out, "--quiet", "--no-preview", "--translucent", "0.95")
        self.assertEqual(rc, 0, err)
        prof = self._profile(out)
        self.assertEqual(T.decode_color(prof["BackgroundColor"])[3], 0.95)
        self.assertEqual(T.decode_color(prof["TextColor"])[3], 1.0)
        md = read(os.path.join(out, "report.md"))
        self.assertIn("alpha 0.95, blur 0; worst case over #000000", md)
        rep = json.loads(read(os.path.join(out, "report.json")))
        self.assertEqual(rep["themes"][0]["background_alpha"], 0.95)

    def test_too_low_alpha_exit_1(self):
        out = os.path.join(self.tmp, "t30")
        rc, _o, err = run(HARBOR, "--name", "Harbor", "--out", out, "--quiet", "--no-preview", "--translucent", "0.3")
        self.assertEqual(rc, 1, err)
        self.assertIn("SOME GATES FAIL", read(os.path.join(out, "report.md")))

    def test_bad_alpha(self):
        for v in ("0", "1.5", "nan"):
            rc, _o, _e = run(HARBOR, "--out", os.path.join(self.tmp, "bad"), "--quiet", "--translucent", v)
            self.assertEqual(rc, 2, v)


if __name__ == "__main__":
    unittest.main()
