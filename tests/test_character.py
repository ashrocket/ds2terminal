"""character.py: token coverage, chroma kept, hue shift, brand coverage, bright steps."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402,F401
from dsterm import character as CH  # noqa: E402
from dsterm import colorlab as cl  # noqa: E402

DARK_ROWS = [
    ("background", "#0f2a2e", "token:text-heading", "#0f2a2e"),
    ("foreground", "#f1f2f4", "token:hb-page", "#f1f2f4"),
    ("bold", "#f7f8fa", "derived:foreground", None),
    ("cursor", "#e63e78", "token:color-brand", "#e63e78"),
    ("selection", "#40343d", "mix:background+brand", None),
    ("black", "#03191c", "derived:background", None),
    ("red", "#ff827f", "token:hb-danger", "#cf2f3a"),
    ("green", "#90dca6", "token:hb-success-fg", "#1d6b3c"),
    ("yellow", "#fce34d", "token:hb-yellow-mark", "#fce34d"),
    ("blue", "#8cbdff", "synthesized", None),
    ("magenta", "#d194ff", "token:hb-info-fg", "#6a2a98"),
    ("cyan", "#9fdcd1", "token:hb-light-teal", "#a6e0d6"),
    ("white", "#d0d7db", "synthesized", None),
    ("brightBlack", "#a3a8ad", "token:text-faint", "#a3a8ad"),
    ("brightRed", "#ff6f9a", "token:color-brand", "#e63e78"),
    ("brightGreen", "#9eeab4", "derived:green", None),
    ("brightYellow", "#fff07a", "derived:yellow", None),
    ("brightBlue", "#a4ccff", "derived:blue", None),
    ("brightMagenta", "#e3b8ff", "derived:magenta", None),
    ("brightCyan", "#bdeee6", "derived:cyan", None),
    ("brightWhite", "#eaf2f6", "synthesized", None),
]


def _dark_record():
    """Hand-built dark theme record matching the report.theme_record() shape."""
    rows = [{"slot": s, "hex": h, "source": src, "token_hex": t} for s, h, src, t in DARK_ROWS]
    return {"mode": "dark", "brand_hex": "#e63e78", "slots": rows}


def _set_row(rec, slot, **fields):
    """Return a copy of rec with one slot's fields replaced."""
    out = copy.deepcopy(rec)
    for row in out["slots"]:
        if row["slot"] == slot:
            row.update(fields)
    return out


class CharacterTests(unittest.TestCase):
    def setUp(self):
        self.dark = _dark_record()
        self.c = CH.character(self.dark)

    def test_token_counts(self):
        self.assertEqual(self.c["tokens_used"], 10)
        self.assertEqual(self.c["tokens_exact"], 5)
        self.assertEqual(self.c["slots"], 21)

    def test_brand(self):
        self.assertEqual(self.c["brand"], {
            "hex": "#e63e78", "cursor": True, "selection": True, "hue_slot": "brightRed"})

    def test_kept(self):
        names = [e["slot"] for e in self.c["kept"]]
        self.assertEqual(names, ["red", "green", "yellow", "magenta", "cyan", "brightRed"])
        yellow = next(e for e in self.c["kept"] if e["slot"] == "yellow")
        self.assertEqual(yellow["chroma_kept"], 1.0)
        self.assertEqual(yellow["hue_shift"], 0.0)
        for e in self.c["kept"]:
            _, c_tok, _ = cl.srgb_to_oklch(cl.parse_hex(e["token_hex"]))
            _, c_hex, _ = cl.srgb_to_oklch(cl.parse_hex(e["hex"]))
            self.assertEqual(e["chroma_kept"], round(c_hex / c_tok, 2))

    def test_bright_step_min(self):
        des = [cl.delta_e_ok_rgb(
                   next(r["hex"] for r in self.dark["slots"] if r["slot"] == n),
                   next(r["hex"] for r in self.dark["slots"] if r["slot"] == "bright" + n[0].upper() + n[1:]))
               for n in CH.HUES]
        self.assertEqual(self.c["bright_step_min"]["de"], round(min(des), 3))

    def test_brand_missing_hue_slot(self):
        rec = _set_row(self.dark, "brightRed", hex="#ffb1c4", source="derived:red", token_hex=None)
        c = CH.character(rec)
        self.assertIsNone(c["brand"]["hue_slot"])
        self.assertIn("no hue color shows the brand color #e63e78", c["misses"])

    def test_chroma_miss(self):
        rec = _set_row(self.dark, "red", hex="#ffd6ce")
        c = CH.character(rec)
        self.assertTrue(any(m.startswith("red keeps ") for m in c["misses"]), c["misses"])

    def test_no_brand(self):
        rec = copy.deepcopy(self.dark)
        rec["brand_hex"] = None
        c = CH.character(rec)
        self.assertIsNone(c["brand"])
        self.assertFalse(any("brand" in m for m in c["misses"]))
        self.assertIn("| Brand color | none |  |", CH.markdown_lines(c))

    def test_markdown(self):
        lines = CH.markdown_lines(self.c)
        self.assertEqual(lines[0], "### Character")
        self.assertTrue(any(l.startswith(
            "| Brand color | cursor: yes, selection: yes, hue color: brightRed |") for l in lines))
        measure_rows = [l for l in lines if l.startswith("| ")][1:]
        self.assertEqual(len(measure_rows), 5)


if __name__ == "__main__":
    unittest.main()
