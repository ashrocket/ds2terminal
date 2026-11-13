"""Tests for dsterm.roles: mode detection by lightness, alias preference, unrelated tokens."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import normalize as N  # noqa: E402
from dsterm import roles as R  # noqa: E402

SAMPLE = _path.SAMPLE
PIDGIN = os.path.join(_path.FIXTURES, "pidgin")
INGEST = _path.FORMATS


def palettes(path):
    pals, _notes = R.extract(N.normalize_paths([path]))
    return pals


class TestHarbor(unittest.TestCase):
    def test_json_light_only_with_semantic_roles(self):
        p = palettes(os.path.join(SAMPLE, "harbor.tokens.json"))
        self.assertEqual(sorted(p), ["light"])
        lp = p["light"]
        self.assertEqual(lp.bg.name, "surface-page")
        self.assertEqual(lp.fg.name, "text-body")
        self.assertEqual(lp.brand.name, "color-brand")
        self.assertEqual(lp.brand.hex, "#e63e78")

    def test_unrelated_client_colors_left_out(self):
        lp = palettes(os.path.join(SAMPLE, "harbor.tokens.json"))["light"]
        kept = {t.name for t in lp.tokens}
        ignored = {t.name for t in lp.ignored}
        self.assertFalse(any(n.startswith("northwind-") for n in kept))
        self.assertIn("northwind-blue", ignored)
        self.assertIn("primary-brand-blue", ignored)
        for n in ("hb-danger-fg", "hb-success-fg", "hb-warning-fg", "hb-info-fg", "color-brand"):
            self.assertIn(n, kept)

    def test_breakpoint_themes_are_not_modes(self):
        p = palettes(os.path.join(SAMPLE, "harbor.tokens.css"))
        self.assertEqual(sorted(p), ["light"])
        self.assertTrue(any("breakpoints" in n for n in p["light"].notes))

    def test_keep_all_tokens(self):
        pals, _ = R.extract(N.normalize_paths([os.path.join(SAMPLE, "harbor.tokens.json")]), keep_all=True)
        self.assertIn("northwind-blue", {t.name for t in pals["light"].tokens})


class TestModes(unittest.TestCase):
    def test_pidgin_extensions_dark_mode(self):
        p = palettes(os.path.join(PIDGIN, "pidgin-editorial.dtcg.json"))
        self.assertEqual(sorted(p), ["dark", "light"])
        self.assertEqual(p["dark"].bg.hex, "#211a12")
        self.assertEqual(p["light"].bg.hex, "#f6eedf")

    def test_own_design_system_light(self):
        # the project's own tokens: light only, a strongly colored page ground
        for f in (_path.OWN, _path.OWN_CSS):
            p = palettes(f)
            self.assertEqual(sorted(p), ["light"], f)
            self.assertEqual(p["light"].bg.hex, "#fef49c", f)
            self.assertEqual(p["light"].brand.hex, "#b3261e", f)

    def test_style_dictionary_nested_groups_and_alias(self):
        # nested groups with {"value": ...} leaves; one leaf is an alias in the {group.leaf.value} form
        path = os.path.join(INGEST, "style-dictionary.json")
        ir = N.normalize_paths([path])
        toks = {t["name"]: t for t in ir["modes"]["default"]["tokens"]}
        self.assertEqual(toks["color.accent.main"]["value_srgb"], "#3a5bd9")
        self.assertEqual(toks["color.accent.main"]["aliasOf"], "color.brand.primary.value")
        p = palettes(path)
        self.assertEqual(sorted(p), ["light"])
        self.assertEqual(p["light"].brand.hex, "#3a5bd9")
        self.assertEqual(p["light"].bg.name, "color.surface.page")

    def test_ingest_fixtures_both_modes(self):
        for f in ("claude-multitheme.tokens.json", "dtcg-modes.tokens.json", "edge.css", "figma-rest.json",
                  "tokens-studio.json"):
            p = palettes(os.path.join(INGEST, f))
            self.assertEqual(sorted(p), ["dark", "light"], f)
            self.assertLess(p["dark"].bg.L, 0.5, f)
            self.assertGreater(p["light"].bg.L, 0.5, f)

    def test_kind_from_lightness_not_name(self):
        # a mode called "dark" whose background is white is a light mode
        ir = {"modes": {"dark": {"kind": "dark", "tokens": [
            {"name": "bg", "value_srgb": "#ffffff", "alpha": 1.0},
            {"name": "text", "value_srgb": "#111111", "alpha": 1.0}]}}}
        pals, _ = R.extract(ir)
        self.assertEqual(sorted(pals), ["light"])
        self.assertTrue(any("background is light" in n for n in pals["light"].notes))


class TestClassify(unittest.TestCase):
    def test_roles(self):
        cases = {"surface-page": "surface", "text-body": "fg", "hb-danger-fg": "chromatic",
                 "hb-danger-bg": "container", "border-default": "border", "color.base.white": "neutral",
                 "text-on-brand": "on-color", "color-brand": "chromatic"}
        for name, role in cases.items():
            self.assertEqual(R.classify(R.split_words(name))[0], role, name)


if __name__ == "__main__":
    unittest.main()
