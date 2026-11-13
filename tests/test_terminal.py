"""Tests for dsterm.terminal: archive layout, round trip, NSRGB fallback, names."""
import glob
import os
import plistlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import terminal as T  # noqa: E402

VARIANTS = os.path.join(_path.TERMINAL, "variants")
COLORS = ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#0f2a2e", "#c9a27a", "#1e1e2e",
          "#f5e0dc", "#fe01fe", "#e63e78", "#0f2a2e", "#7f7f7f"]


def all_colors(c="#0f2a2e"):
    return dict((k, c) for k in T.COLOR_KEYS)


class TestColorArchive(unittest.TestCase):
    def test_round_trip_exact(self):
        for hx in COLORS:
            r, g, b, a = T.parse_hex(hx)
            blob = T.color_archive((r, g, b, a), icc="none")
            dr, dg, db, da, info = T.decode_color(blob)
            self.assertEqual("#%02x%02x%02x" % tuple(int(round(x * 255)) for x in (dr, dg, db)), hx)
            self.assertEqual(da, 1.0)
            self.assertEqual(info["NSColorSpace"], 1)
            self.assertEqual(info["NSID"], 7)
            self.assertFalse(info["has_icc"])

    def test_layout_matches_appkit(self):
        d = plistlib.loads(T.color_archive((0.1725490196, 0.3882352941, 0.3843137255, 1.0), icc="none"))
        self.assertEqual(d["$archiver"], "NSKeyedArchiver")
        self.assertEqual(d["$version"], 100000)
        root = d["$objects"][1]
        self.assertEqual(root["NSComponents"], b"0.1725490196 0.3882352941 0.3843137255 1")  # no NUL, alpha always
        self.assertTrue(root["NSRGB"].endswith(b"\0"))
        self.assertEqual(root["NSLinearExposure"], b"1")
        self.assertEqual(d["$objects"][-1]["$classname"], "NSColor")

    def test_icc_embedded_when_file_exists(self):
        fake = b"ICCBYTES" * 10
        with mock.patch.object(T, "srgb_icc_bytes", return_value=fake):
            d = plistlib.loads(T.color_archive((1, 0, 0, 1)))
        cs = d["$objects"][2]
        self.assertEqual(cs["NSID"], 7)
        self.assertEqual(d["$objects"][cs["NSICC"].data], fake)

    def test_never_generic_rgb_without_custom_space(self):
        d = plistlib.loads(T.color_archive((0.5, 0.2, 0.9, 1)))
        self.assertIn("NSCustomColorSpace", d["$objects"][1])

    def test_nsrgb_fallback_matches_mac_research(self):
        # the research files were written on the Mac with the real Generic RGB profile
        n = 0
        for f in glob.glob(os.path.join(VARIANTS, "variant_[cd]_*.terminal")):
            with open(f, "rb") as fh:
                prof = plistlib.load(fh)
            for k in T.COLOR_KEYS:
                if k not in prof:
                    continue
                o = plistlib.loads(prof[k])["$objects"][1]
                comps = [float(x) for x in o["NSComponents"].split()[:3]]
                want = [float(x) for x in o["NSRGB"].rstrip(b"\0").split()[:3]]
                got = T.srgb_to_generic(comps)
                for w, g in zip(want, got):
                    self.assertAlmostEqual(w, g, delta=0.03 / 255)
                n += 1
        self.assertGreater(n, 20)

    def test_font(self):
        self.assertEqual(T.decode_font(T.font_archive("SFMonoTerminal-Regular", 13)), ("SFMonoTerminal-Regular", 13.0))


class TestProfile(unittest.TestCase):
    def test_keys(self):
        p = T.build_profile("X", all_colors(), cursor="bar", columns=100, rows=30)
        data = plistlib.loads(T.dumps_profile(p))
        self.assertEqual(data["type"], "Window Settings")
        self.assertEqual(data["ProfileCurrentVersion"], 2.09)
        self.assertEqual(data["CursorType"], 2)
        self.assertFalse(data["UseBrightBold"])
        self.assertNotIn("CursorTextColor", data)
        for k in T.COLOR_KEYS:
            self.assertIn(k, data)
        self.assertEqual(T.decode_font(data["Font"])[1], 13.0)

    def test_missing_and_unknown_keys(self):
        c = all_colors()
        del c["CursorColor"]
        with self.assertRaises(KeyError):
            T.build_profile("X", c)
        c = all_colors()
        c["CursorTextColor"] = "#000000"
        with self.assertRaises(KeyError):
            T.build_profile("X", c)

    def test_names(self):
        self.assertEqual(T.clean_name("a\tb\x01c"), "a b c")
        self.assertEqual(T.safe_filename("A/B:C"), "A-B-C.terminal")
        self.assertLessEqual(len(T.safe_filename("x" * 400).encode("utf-8")), 255)
        p = T.build_profile('Café & <Bar> "Q"', all_colors())
        self.assertEqual(plistlib.loads(T.dumps_profile(p))["name"], 'Café & <Bar> "Q"')


if __name__ == "__main__":
    unittest.main()
