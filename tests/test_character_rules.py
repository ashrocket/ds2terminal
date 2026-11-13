"""The character rules of the mapper: a theme must look like its design system, inside the gates."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import colorlab as cl  # noqa: E402
from dsterm import mapper as M  # noqa: E402
from dsterm import normalize as N  # noqa: E402
from dsterm import report as RP  # noqa: E402
from dsterm import roles as R  # noqa: E402
from dsterm import theme as TH  # noqa: E402

HARBOR = os.path.join(_path.SAMPLE, "harbor.tokens.json")
BRAND = "#e63e78"


def _max_chroma(L, h):
    """Largest OKLCH chroma that is inside sRGB at this lightness and hue."""
    lo, hi = 0.0, 0.4
    for _ in range(30):
        mid = (lo + hi) / 2.0
        if cl.in_srgb_gamut(cl.oklch_to_srgb((L, mid, h))):
            lo = mid
        else:
            hi = mid
    return lo


class TestHarborCharacter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pals, _ = R.extract(N.normalize_paths([HARBOR]))
        cls.dark = TH.build(pals["light"], "dark", derived=True)
        cls.light = TH.build(pals["light"], "light")
        cls.rec = {m: RP.theme_record("Harbor " + m, "x.terminal", th)
                   for m, th in (("dark", cls.dark), ("light", cls.light))}

    def test_both_pass(self):
        self.assertTrue(self.dark["check"]["pass"], self.dark["check"]["failures"])
        self.assertTrue(self.light["check"]["pass"], self.light["check"]["failures"])

    def test_dark_brand_is_bright_pink(self):
        s = self.dark["slots"]
        self.assertEqual(s[9].source, "token:color-brand")
        self.assertEqual(s[9].origin, "brand")
        bg = s["background"].hex
        self.assertGreaterEqual(cl.lc_abs(s[9].hex, bg), 60.0)
        L, C, h = cl.srgb_to_oklch(cl.parse_hex(s[9].hex))
        bL, bC, bh = cl.srgb_to_oklch(cl.parse_hex(BRAND))
        self.assertLessEqual(cl.hue_diff(h, bh), M.BRAND_HUE_TURN + 2.0)     # still the brand hue
        # still a strong pink: the lifted pink is lighter, and the sRGB gamut caps chroma there (Harbor's brand
        # at 0.20 chroma cannot keep 70% at this lightness), so it must keep nearly all the chroma the gamut allows
        self.assertGreaterEqual(C, 0.9 * _max_chroma(L, h))
        self.assertGreaterEqual(C, 0.1)
        # the loss is real and the report must show it: a pink at this lightness cannot keep its chroma in
        # sRGB, so brightRed keeps well under 70% of the brand chroma, and the record lists it as a miss
        ch = self.rec["dark"]["character"]
        kept = [e for e in ch["kept"] if e["slot"] == "brightRed"][0]
        self.assertLess(kept["chroma_kept"], 0.70)
        self.assertTrue(any(m.startswith("brightRed keeps ") for m in ch["misses"]), ch["misses"])
        rL, rC, rh = cl.srgb_to_oklch(cl.parse_hex(s[1].hex))
        self.assertLessEqual(cl.hue_diff(h, rh), cl.GATES["bright_relation"]["gate"]["max_hue_diff"])
        self.assertEqual(self.rec["dark"]["character"]["brand"]["hue_slot"], "brightRed")

    def test_exact_brand_cursor_when_it_passes_wcag_4_5(self):
        # the exact rule, on the project's own design system: the brand token (signal-red) passes WCAG 4.5 on
        # the light background, so the cursor is that token's exact color. Harbor's brand is too weak for this.
        pals, _ = R.extract(N.normalize_paths([_path.OWN]))
        th = TH.build(pals["light"], "light")
        brand = pals["light"].brand
        self.assertEqual(brand.name, "signal-red")
        c = th["slots"]["cursor"]
        self.assertEqual((c.hex, c.source, c.origin), (brand.hex, "token:signal-red", "brand"))
        self.assertGreaterEqual(cl.contrast_ratio(c.hex, th["slots"]["background"].hex), 4.5)

    def test_light_brand_when_no_hue_slot_shows_it(self):
        # Harbor's danger red is hue 23 and the brand pink is hue 5, more than BRAND_CARRIED_HUE apart, so no
        # light hue slot shows the brand when the slots are chosen: the brand becomes the bright step of red,
        # as in the dark theme. (The red repair for color-blind readers later turns the normal red toward
        # the brand, which is why the record also names "red" as a hue slot.)
        self.assertEqual(self.light["slots"][9].source, "token:color-brand")
        self.assertEqual(self.light["slots"][9].origin, "brand")
        self.assertEqual(self.rec["light"]["character"]["brand"]["hue_slot"], "red")

    def test_light_brand_is_already_shown(self):
        # the same palette with a danger red within BRAND_CARRIED_HUE of the brand hue: a hue slot already
        # shows the brand, so the light theme does not add a second brand color
        with open(HARBOR, encoding="utf-8") as fh:
            ds = json.load(fh)
        for t in ds["color"]["tokens"]:
            if t["name"] == "hb-danger":
                t["value"] = "#d62f55"
            elif t["name"] == "hb-danger-fg":
                t["value"] = "#a81a3e"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "near-brand-danger.tokens.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(ds, fh)
            pals, _ = R.extract(N.normalize_paths([p]))
        light = TH.build(pals["light"], "light")
        self.assertTrue(light["check"]["pass"], light["check"]["failures"])
        self.assertNotEqual(light["slots"][9].source, "token:color-brand")
        rec = RP.theme_record("Harbor near", "x.terminal", light)
        self.assertEqual(rec["character"]["brand"]["hue_slot"], "red")

    def test_dark_colors_keep_their_chroma(self):
        # before the measured faint model, the faint floor made the dark red a pale pink (chroma 0.05)
        s = self.dark["slots"]
        self.assertGreaterEqual(cl.srgb_to_oklch(cl.parse_hex(s[1].hex))[1], 0.12)
        self.assertLessEqual(cl.lc_abs(s[1].hex, s["background"].hex), 60.0)
        self.assertGreaterEqual(self.rec["dark"]["character"]["chroma_kept_mean"], 0.7)

    def test_dark_red_and_green_have_a_lightness_gap(self):
        s = self.dark["slots"]
        bg = s["background"].hex
        self.assertGreaterEqual(cl.lc_abs(s[2].hex, bg) - cl.lc_abs(s[1].hex, bg), 12.0)
        self.assertFalse([r for r in self.dark["repairs"] if "cvd" in r], self.dark["repairs"])

    def test_bold(self):
        # light: the heading text token. dark: the text color, a step brighter, below the halation gate
        lb = self.light["slots"]["bold"]
        self.assertEqual(lb.source, "token:text-heading")
        self.assertEqual(lb.hex, "#0f2a2e")
        d = self.dark["slots"]
        bg = d["background"].hex
        self.assertGreater(cl.lc_abs(d["bold"].hex, bg), cl.lc_abs(d["foreground"].hex, bg))
        self.assertLessEqual(cl.lc_abs(d["bold"].hex, bg), cl.GATES["halation"]["gate"]["max_lc"])

    def test_light_text_aims_at_the_faint_target(self):
        s = self.light["slots"]
        bg = s["background"].hex
        v = cl.lc_abs(cl.faint(s["foreground"].hex, bg), bg)
        self.assertGreaterEqual(v, cl.GATES["faint_text"]["target"]["fg_min_lc"])
        self.assertEqual(s["foreground"].source, "token:text-body")

    def test_light_background_is_the_text_surface(self):
        # the Harbor app draws text on white cards; the page color #f1f2f4 is behind the cards
        bg = self.light["slots"]["background"]
        self.assertEqual((bg.hex, bg.source), ("#ffffff", "token:surface-card"))
        self.assertIn("surface-page", bg.note)
        # the derived dark theme does not use the card
        self.assertEqual(self.dark["slots"]["background"].hex, "#0f2a2e")

    def test_prefer_token_keeps_the_page(self):
        pals, _ = R.extract(N.normalize_paths([HARBOR]))
        page = [t for t in pals["light"].tokens if t.name == "surface-page"][0]
        th = TH.build(pals["light"], "light", prefer={"bg": page})
        self.assertEqual(th["slots"]["background"].hex, "#f1f2f4")

    def test_light_cursor_is_a_brand_ramp_token(self):
        # the brand pink #e63e78 is WCAG 3.9 on white: the action pink of the ramp is the cursor
        self.assertLess(cl.contrast_ratio(BRAND, "#ffffff"), 4.5)
        c = self.light["slots"]["cursor"]
        self.assertEqual(c.hex, "#b0235a")
        self.assertEqual(c.source, "token:color-brand-action")
        self.assertEqual(c.origin, "brand")
        self.assertTrue(self.rec["light"]["character"]["brand"]["cursor"])
        # dark: the brand is too dim on the deep teal-black background (WCAG 3.5), so the cursor is the brand
        # hue lifted to WCAG 4.5; it stays the brand hue and is still the brand token
        dc = self.dark["slots"]["cursor"]
        bg = self.dark["slots"]["background"].hex
        self.assertEqual((dc.source, dc.origin), ("token:color-brand", "brand"))
        self.assertGreaterEqual(cl.contrast_ratio(dc.hex, bg), 4.5)
        self.assertLessEqual(cl.hue_diff(cl.srgb_to_oklch(cl.parse_hex(dc.hex))[2],
                                         cl.srgb_to_oklch(cl.parse_hex(BRAND))[2]), M.BRAND_HUE_TURN + 2.0)

    def test_hue_colors_pass_wcag_3_before_repair(self):
        self.assertNotIn("ansi_normal", self.light["before"]["failed_gate_ids"])
        self.assertNotIn("ansi_normal", self.dark["before"]["failed_gate_ids"])


if __name__ == "__main__":
    unittest.main()
