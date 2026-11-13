"""character.py - how much of the design system a theme keeps. These are targets, not gates: a gate can cost character, and the report must show the cost."""
import math

from . import colorlab as cl

HUES = ("red", "green", "yellow", "blue", "magenta", "cyan")
HUE_SLOTS = HUES + tuple("bright" + n[0].upper() + n[1:] for n in HUES)
MIN_C = 0.04            # a token with less chroma is a gray: no hue or chroma measure
TARGET_CHROMA_KEPT = 0.70
TARGET_HUE_SHIFT = 12.0
TARGET_BRIGHT_STEP = 0.03
BRAND_HUE = 15.0        # a hue color this near the brand hue, with BRAND_C of its chroma, shows the brand
BRAND_C = 0.6


def _lch(hex_color):
    """Return (L, C, h) in OKLCH for a hex color."""
    return cl.srgb_to_oklch(cl.parse_hex(hex_color))


def _kept_entry(row):
    """Chroma and hue kept for one token-backed hue slot, or None if the token is a gray."""
    token_hex = row["token_hex"].lower()
    hex_color = row["hex"].lower()
    _, c_tok, h_tok = _lch(token_hex)
    if c_tok < MIN_C:
        return None
    _, c_hex, h_hex = _lch(hex_color)
    shift = 0.0 if math.isnan(h_hex) else round(cl.hue_diff(h_hex, h_tok), 1)
    return {
        "slot": row["slot"],
        "token": row["source"][6:],
        "token_hex": token_hex,
        "hex": hex_color,
        "chroma_kept": round(c_hex / c_tok, 2),
        "hue_shift": shift,
    }


def _kept(by):
    """One entry per hue slot whose token has enough chroma to measure."""
    out = []
    for name in HUE_SLOTS:
        row = by.get(name)
        if row is None or not row.get("token_hex"):
            continue
        entry = _kept_entry(row)
        if entry is not None:
            out.append(entry)
    return out


def _brand(rec, by):
    """Brand color coverage: cursor and selection use, and the first hue color showing it."""
    brand_hex = rec.get("brand_hex")
    if not brand_hex:
        return None
    brand_hex = brand_hex.lower()
    _, c_brand, h_brand = _lch(brand_hex)
    # the cursor shows the brand when it is the brand token or a color of the brand hue (a ramp step)
    cursor_tok = by["cursor"].get("token_hex")
    _, c_cur, h_cur = _lch(by["cursor"]["hex"])
    cursor = (bool(cursor_tok) and cursor_tok.lower() == brand_hex) or (
        c_brand >= MIN_C and h_cur == h_cur and cl.hue_diff(h_cur, h_brand) <= BRAND_HUE and c_cur >= BRAND_C * c_brand)
    hue_slot = None
    if c_brand >= MIN_C:
        for name in HUE_SLOTS:
            row = by.get(name)
            if row is None:
                continue
            _, c_slot, h_slot = _lch(row["hex"])
            if cl.hue_diff(h_slot, h_brand) <= BRAND_HUE and c_slot >= BRAND_C * c_brand:
                hue_slot = name
                break
    return {
        "hex": rec["brand_hex"],
        "cursor": cursor,
        "selection": "brand" in by["selection"]["source"],
        "hue_slot": hue_slot,
    }


def _bright_steps(by):
    """Lightness-contrast step (dE) between each normal hue color and its bright partner."""
    steps = []
    for name in HUES:
        bright = "bright" + name[0].upper() + name[1:]
        de = cl.delta_e_ok_rgb(by[name]["hex"], by[bright]["hex"])
        steps.append({"slot": name, "de": round(de, 3)})
    return steps


def _misses(c, brand_hex_value):
    """Describe each target the theme misses, in report order."""
    misses = []
    worst = c["chroma_kept_min"]
    if worst is not None and worst["chroma_kept"] < TARGET_CHROMA_KEPT:
        misses.append("%s keeps %d%% of the chroma of %s" % (
            worst["slot"], round(100 * worst["chroma_kept"]), worst["token"]))
    shifted = c["hue_shift_max"]
    if shifted is not None and shifted["hue_shift"] > TARGET_HUE_SHIFT:
        misses.append("%s is %.0f degrees from the hue of %s" % (
            shifted["slot"], shifted["hue_shift"], shifted["token"]))
    brand = c["brand"]
    if brand is not None and _lch(brand["hex"])[1] >= MIN_C and brand["hue_slot"] is None:
        misses.append("no hue color shows the brand color %s" % brand_hex_value)
    step = c["bright_step_min"]
    if step["de"] < TARGET_BRIGHT_STEP:
        misses.append("%s and its bright color are almost the same (dE %.3f)" % (
            step["slot"], step["de"]))
    return misses


def character(rec):
    """Measure how much of the design system a theme keeps, as a dict of values and misses."""
    by = {row["slot"]: row for row in rec["slots"]}
    token_rows = [row for row in rec["slots"] if row["source"].startswith("token:")]
    tokens_exact = sum(1 for row in token_rows
                       if row["hex"].lower() == (row.get("token_hex") or "").lower())
    kept = _kept(by)
    chroma_min = min(kept, key=lambda e: e["chroma_kept"]) if kept else None
    chroma_mean = round(sum(e["chroma_kept"] for e in kept) / len(kept), 2) if kept else None
    shift_max = max(kept, key=lambda e: e["hue_shift"]) if kept else None
    steps = _bright_steps(by)
    c = {
        "tokens_used": len(token_rows),
        "tokens_exact": tokens_exact,
        "slots": 21,
        "kept": kept,
        "chroma_kept_min": chroma_min,
        "chroma_kept_mean": chroma_mean,
        "hue_shift_max": shift_max,
        "bright_step_min": min(steps, key=lambda s: s["de"]),
        "brand": _brand(rec, by),
    }
    c["misses"] = _misses(c, rec.get("brand_hex"))
    return c


def _yes(flag):
    """Word for a boolean in the markdown table."""
    return "yes" if flag else "no"


def _table_rows(c):
    """Measure rows of the character table, with a none row where a value is absent."""
    rows = ["| Colors from tokens | %d of 21 (%d exact) |  |" % (c["tokens_used"], c["tokens_exact"])]
    step = c["bright_step_min"]
    brand = c["brand"]
    if brand is None:
        rows.append("| Brand color | none |  |")
    else:
        hue = brand["hue_slot"] or "none"
        rows.append("| Brand color | cursor: %s, selection: %s, hue color: %s | a hue color shows the brand |"
                    % (_yes(brand["cursor"]), _yes(brand["selection"]), hue))
    if c["kept"]:
        worst, shift = c["chroma_kept_min"], c["hue_shift_max"]
        rows.append("| Chroma kept (hue colors from tokens) | lowest %d%% (%s), mean %d%% | 70%% or more |"
                    % (round(100 * worst["chroma_kept"]), worst["slot"],
                       round(100 * c["chroma_kept_mean"])))
        rows.append("| Largest hue change | %.1f degrees (%s) | 12 degrees or less |"
                    % (shift["hue_shift"], shift["slot"]))
    else:
        rows.append("| Chroma kept (hue colors from tokens) | none |  |")
        rows.append("| Largest hue change | none |  |")
    rows.append("| Smallest normal to bright step | dE %.3f (%s) | 0.030 or more |" % (step["de"], step["slot"]))
    return rows


def markdown_lines(c):
    """Markdown lines for the Character section of the report, without a trailing blank line."""
    lines = [
        "### Character",
        "",
        "How much of the design system the theme keeps. These are targets. A gate can cost character; this table shows the cost.",
        "",
        "| Measure | Value | Target |",
        "|---|---|---|",
    ]
    lines.extend(_table_rows(c))
    if c["misses"]:
        lines.append("")
        lines.append("Targets missed: %s." % "; ".join(c["misses"]))
    return lines
