"""Claude Code theme pairing: resolved colors, Lc rows, the recommendation, and the preview lines."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402,F401
from dsterm import claudecode as CC  # noqa: E402
from dsterm import colorlab as cl  # noqa: E402

SLOTS = ["background", "foreground", "bold", "cursor", "selection"] + [
    "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
    "brightBlack", "brightRed", "brightGreen", "brightYellow", "brightBlue", "brightMagenta", "brightCyan",
    "brightWhite"]
DARK_COLORS = ["#0f2a2e", "#f1f2f4", "#f7f8fa", "#e63e78", "#40343d",
               "#03191c", "#ff827f", "#90dca6", "#fce34d", "#8cbdff", "#d194ff", "#9fdcd1", "#d0d7db",
               "#a3a8ad", "#ff6f9a", "#9eeab4", "#fff07a", "#a4ccff", "#e3b8ff", "#bdeee6", "#eaf2f6"]
LIGHT_COLORS = ["#f1f2f4", "#373b40", "#0f2a2e", "#b0235a", "#ffdfe5",
                "#000000", "#ed4e6d", "#418b5a", "#8a5a07", "#5e8edd", "#9e60d1", "#1a979b", "#a0a7ab",
                "#a3a8ad", "#cc2064", "#1d6b3c", "#704a05", "#3e6ebf", "#6a2a98", "#00777b", "#bdc4c8"]


def rec(mode, colors):
    return {"mode": mode, "slots": [{"slot": n, "hex": h} for n, h in zip(SLOTS, colors)]}


def with_slots(base, **changes):
    colors = list(base)
    for name, hexv in changes.items():
        colors[SLOTS.index(name)] = hexv
    return colors


DARK = rec("dark", DARK_COLORS)
LIGHT = rec("light", LIGHT_COLORS)


def fake_span(text, fg=None, bg=None, bold=False):
    return "[%s|%s|%s]" % (text, fg, bg)


class TestResolve(unittest.TestCase):
    def test_ansi_and_standard_elements(self):
        a = CC.resolve(DARK, "ansi")
        self.assertEqual(a["text"], "#eaf2f6")
        self.assertEqual(a["user_bg"], "#a3a8ad")
        self.assertEqual(a["diff_added"], "#90dca6")
        self.assertEqual(a["claude"], "#ff6f9a")
        self.assertEqual(a["bg"], "#0f2a2e")
        s = CC.resolve(DARK, "standard")
        self.assertEqual(s["text"], "#ffffff")
        self.assertEqual(s["diff_added"], "#225c2b")


class TestRows(unittest.TestCase):
    def test_row_count_and_added_line(self):
        rs = CC.rows(DARK, "ansi")
        self.assertEqual(len(rs), len(CC.PAIRS))
        added = [r for r in rs if r["pair"] == "added line"][0]
        self.assertEqual(added["text"], "#eaf2f6")
        self.assertEqual(added["on"], "#90dca6")
        self.assertEqual(added["lc"], round(cl.lc_abs("#eaf2f6", "#90dca6"), 1))

    def test_faint_row(self):
        faint = [r for r in CC.rows(DARK, "ansi") if r["pair"] == "faint text"][0]
        self.assertEqual(faint["text"], cl.faint("#eaf2f6", "#0f2a2e"))


class TestPairing(unittest.TestCase):
    def test_dark_palette_recommends_standard(self):
        p = CC.pairing(DARK)
        self.assertEqual(p["recommend"], "standard")
        self.assertEqual(p["ansi"]["weakest"]["pair"], "added line")
        self.assertLess(p["ansi"]["weakest"]["lc"], 45)
        self.assertGreater(p["standard"]["weakest"]["lc"], p["ansi"]["weakest"]["lc"])
        self.assertIn("below 45", p["reason"])

    def test_readable_ansi_palette_recommends_ansi(self):
        colors = with_slots(DARK_COLORS, green="#225c2b", red="#7a2936", brightBlack="#373737",
                            blue="#264f78")
        self.assertEqual(CC.pairing(rec("dark", colors))["recommend"], "ansi")


class TestMarkdown(unittest.TestCase):
    def test_section_lines(self):
        lines = CC.markdown_lines(CC.pairing(DARK))
        self.assertEqual(lines[0], "### Claude Code")
        data_rows = [ln for ln in lines if ln.startswith("| ") and not ln.startswith("| Pair")]
        self.assertEqual(len(data_rows), len(CC.PAIRS))
        self.assertTrue(lines[-1].startswith("Recommended Claude Code theme: **standard theme"))


class TestPreview(unittest.TestCase):
    def test_ansi_sample(self):
        lines = CC.preview_lines(DARK, "ansi", fake_span)
        self.assertEqual(len(lines), 9)
        self.assertIn("#90dca6", lines[5])
        self.assertIn("#9eeab4", lines[5])


class TestLight(unittest.TestCase):
    def test_light_smoke(self):
        self.assertEqual(CC.resolve(LIGHT, "ansi")["text"], "#000000")
        self.assertEqual(CC.resolve(LIGHT, "ansi")["user_bg"], "#a0a7ab")
        self.assertEqual(CC.pairing(LIGHT)["ansi"]["setting"], "light-ansi")


if __name__ == "__main__":
    unittest.main()
