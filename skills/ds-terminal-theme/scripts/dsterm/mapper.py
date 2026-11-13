"""mapper.py - map a design-system palette onto the 16 ANSI colors and the Terminal.app roles.

Algorithm "H", written for the APCA targets of colorlab.GATES:

1. Background and text come from the role tokens (roles.py). A missing mode is derived:
   the light text/ink token becomes the dark background, the light paper becomes the dark text.
2. Tokens go to the six hue slots by a minimum-cost assignment (Hungarian): OKLCH hue
   distance to an anchor, token-name signals (danger -> red, success -> green, ...), a
   low-chroma penalty and a lightness-change penalty. A slot can stay empty ("synthesized").
3. Each slot's lightness is moved (hue and chroma kept) into the APCA band of the mode.
   A token that is already in the band stays exact.
4. Empty slots are synthesized at the CVD-friendly hues of the readability research, at the
   brand's median chroma, with a small hue turn toward the brand.
5. Brights, grays, cursor, selection and bold follow. gates.repair() then makes every
   hard gate pass.

Each slot records its source (token name, "synthesized", "derived:...", "override").
"""
import functools
import math
from typing import Dict, List, Optional, Tuple

from . import colorlab as cl
from .roles import (EXCLUDED_FROM_HUES, MIN_CHROMA_CHROMATIC, ModePalette, Token, circ_mean, hue_dist,
                    pick_bg, pick_brand, pick_fg)

SLOTS6 = ("red", "green", "yellow", "blue", "magenta", "cyan")
ANSI_INDEX = {"red": 1, "green": 2, "yellow": 3, "blue": 4, "magenta": 5, "cyan": 6}
ANSI_NAMES = cl.ANSI_NAMES

# Assignment anchors (OKLCH hue, half window), measured from VS Code, xterm, Primer and
# One Dark (mapping report section 2). Light yellow is amber: olive collides with green.
ANCHORS = {
    "dark": {"red": (25.0, 25.0), "green": (145.0, 25.0), "yellow": (92.0, 25.0),
             "blue": (255.0, 25.0), "magenta": (318.0, 28.0), "cyan": (207.0, 22.0)},
    "light": {"red": (25.0, 25.0), "green": (145.0, 25.0), "yellow": (78.0, 22.0),
              "blue": (255.0, 25.0), "magenta": (318.0, 28.0), "cyan": (207.0, 22.0)},
}
NAME_FORCED_WINDOW = 45.0   # a semantically named token may sit this far from its anchor
SYNTH_COST = 1.0

# Synthesis hues: CVD-friendly (crimson red, yellow-green green), from synth_demo.py and
# cvd_search.py (readability report section 5). Both demo themes pass every gate.
SYNTH_HUES = {"red": 18.0, "green": 132.0, "yellow": 85.0, "blue": 252.0, "magenta": 330.0, "cyan": 198.0}
SYNTH_C_MAX = {"red": 0.16, "green": 0.14, "yellow": 0.12, "blue": 0.13, "magenta": 0.15, "cyan": 0.10}
SYNTH_C_FLOOR = {"red": 0.11, "green": 0.09, "yellow": 0.10, "blue": 0.09, "magenta": 0.09, "cyan": 0.08}
HARMONIZE_MAX = 8.0
# Character (brand) rules. A theme must look like its design system, inside the gates.
BRAND_CARRIED_HUE = 15.0      # a hue slot this near the brand hue (with BRAND_CARRIED_C of its chroma) shows the brand
BRAND_CARRIED_C = 0.6
BRAND_BRIGHT_MAX_DIFF = 26.0  # the brand can be the bright step of a hue this near (bright_relation gate: 30)
HEADING_W = {"heading", "headings", "title", "display", "strong", "emphasis"}
# Light mode: when the design system has a page color and a lighter card color, text is on the cards.
TEXT_SURFACE_W = {"card", "paper", "sheet", "panel", "content", "raised", "elevated"}
TEXT_SURFACE_MIN_DL = 0.01
BRAND_RAMP_HUE = 10.0         # a token this near the brand hue is a step of the brand ramp
BRAND_HUE_TURN = 8.0          # a lifted brand color can turn this far to keep chroma that the gamut cuts
BRAND_BRIGHT_STEP = 6.0       # the brand as a bright color is this much Lc above its normal color
BOLD_STEP_DARK = 4.0          # dark mode: bold text is up to this much Lc above the text, below the halation gate
BOLD_STEP_MIN = 2.0
HARMONIZE_MAX_DIFF = 120.0
# dark mode chroma floor for token colors (open decision 4; C9: pastel blues read as plain text)
PASTEL_FLOOR = {"red": 0.10, "green": 0.09, "yellow": 0.08, "blue": 0.07, "magenta": 0.07, "cyan": 0.06}

# |APCA Lc| targets on the background. Synthesized slots use these values; token slots stay
# exact inside KEEP and move to the nearest KEEP edge otherwise.
TARGETS = {
    "dark": {
        "fg": 90.0, "fg_keep": (85.0, 100.0),
        "normal": {"red": 58, "green": 85, "yellow": 80, "blue": 62, "magenta": 66, "cyan": 74},
        "normal_keep": (55.0, 96.0),
        # Low edge of the keep band for each slot. Red is the most saturated near Lc 50 (lighter reds
        # are pink). Green is 20 above red: the lightness gap keeps red and green apart for color-blind
        # readers (cvd gate: red Lc 53 needs green Lc 70). The faint_text floor can raise these.
        "normal_lo": {"red": 50.0, "green": 72.0, "yellow": 62.0, "blue": 55.0, "magenta": 55.0, "cyan": 60.0},
        "bright_step": 8.0, "bright_keep": (64.0, 100.0), "bright_max": 100.0,
        "n8": 45.0, "n7": 78.0, "n15": 92.0,
        "cursor_wcag": 4.5,
    },
    "light": {
        "fg": 95.0, "fg_keep": (85.0, 108.0),
        "normal": {"red": 55, "green": 66, "yellow": 64, "blue": 60, "magenta": 57, "cyan": 62},
        "normal_keep": (52.0, 68.0),
        "bright": {"red": 70, "green": 80, "yellow": 78, "blue": 74, "magenta": 72, "cyan": 76},
        "bright_step": 10.0, "bright_keep": (66.0, 95.0), "bright_max": 98.0,
        "n0": 100.0, "n8": 55.0, "n7": 48.0, "n15": 32.0,
        "cursor_wcag": 4.5,
    },
}

ROLE_KEYS = ("background", "foreground", "bold", "cursor", "selection")
PRIORITY = {"override": 5, "brand": 4, "token-named": 3, "token": 2, "derived": 1, "synth": 0, "alias": 1}


class Slot(object):
    def __init__(self, hexcol: str, source: str, note: str = "", origin: str = "synth",
                 h: Optional[float] = None, C: Optional[float] = None):
        self.hex = cl.to_hex(cl.parse_hex(hexcol))
        self.source = source
        self.note = note
        self.origin = origin
        L, c, hh = cl.srgb_to_oklch(cl.parse_hex(self.hex))
        self.h = h if h is not None else (hh if hh == hh else 0.0)
        self.C = C if C is not None else c
        self.original = self.hex
        self.alpha = 1.0   # used by the background only (--translucent)

    def copy(self) -> "Slot":
        s = Slot(self.hex, self.source, self.note, self.origin, self.h, self.C)
        s.original = self.original
        s.alpha = self.alpha
        return s

    def as_dict(self) -> dict:
        return {"hex": self.hex, "source": self.source, "origin": self.origin, "note": self.note}


# ---------------------------------------------------------------- color helpers

def lc(a: str, bg: str) -> float:
    return cl.lc_abs(a, bg)


def L_of(hx: str) -> float:
    return cl.srgb_to_oklab(cl.parse_hex(hx))[0]


def oklch_hex(L: float, C: float, h: float) -> str:
    return cl.to_hex(cl.gamut_map_oklch((max(0.0, min(1.0, L)), max(0.0, C), h % 360.0)))


def at_lc(bg: str, h: float, C: float, target: float, lighter: bool) -> str:
    """Color of hue h and chroma C (reduced if out of gamut) whose |Lc| on bg is at least
    target after 8-bit rounding. If the target cannot be reached, the farthest color."""
    r = cl.solve_lightness_for_lc(bg, h, C, target, lighter)
    if r is None:
        return oklch_hex(1.0 if lighter else 0.0, C, h)
    L, rgb = r
    hx = cl.to_hex(rgb)
    n = 0
    while lc(hx, bg) < target and n < 60:
        L = L + 0.002 if lighter else L - 0.002
        if L < 0.0 or L > 1.0:
            break
        hx = oklch_hex(L, C, h)
        n += 1
    return hx


MIN_WCAG_HUE = cl.GATES["ansi_normal"]["gate"]["min_wcag"] + 0.05   # a little above the gate, for 8-bit rounding
FAINT_MARGIN = 1.0  # aim a little above the faint_text gate, so 8-bit rounding and hue do not fail it


@functools.lru_cache(maxsize=4096)
def faint_floor(bg: str, mode: str, alpha: float = 1.0, h: float = 0.0, C: float = 0.0,
                aim: Optional[float] = None) -> float:
    """Lowest |Lc| on bg that a color of hue h and chroma C needs so that its faint (SGR 2) form
    reaches aim (default: the faint_text gate for hue colors), on bg and on every desktop
    composite of a translucent bg. 8-bit rounding and hue move the result by up to about 1.5 Lc,
    so callers pass the real hue and chroma (hue_floor)."""
    if aim is None:
        aim = cl.GATES["faint_text"]["gate"]["ansi_min_lc"] + FAINT_MARGIN
    bgs = [bg] + [c for _d, c in cl.translucent_backgrounds(bg, alpha)]
    for v in range(30, 106):
        hx = at_lc(bg, h, C, float(v), mode == "dark")
        if all(lc(cl.faint(hx, b), b) >= aim for b in bgs):
            return float(v)
    return 106.0


def hue_floor(bg: str, mode: str, alpha: float, h: float, C: float) -> float:
    """faint_floor for one hue color (rounded, so the cache works)."""
    return faint_floor(bg, mode, alpha, float(round(h % 360.0)), round(max(0.0, C), 2))


def fg_floor(bg: str, mode: str, alpha: float = 1.0) -> float:
    """Lowest |Lc| of a gray text color whose faint form passes the faint_text gate."""
    G = cl.GATES["faint_text"]
    aim = G["gate"]["fg_min_lc_dark" if mode == "dark" else "fg_min_lc"] + FAINT_MARGIN
    if mode == "light":
        # Dark text loses the most when it is faint. Aim at the target when the background lets pure
        # black reach it; the gate stays the hard limit.
        reach = lc(cl.faint("#000000", bg), bg)
        aim = max(aim, min(G["target"]["fg_min_lc"], reach - 2.0))
    return faint_floor(bg, mode, alpha, aim=aim)


def fit_lc(hx: str, bg: str, lo: float, hi: float, lighter: bool) -> Tuple[str, str]:
    """Keep hx when its |Lc| is inside [lo, hi] and it sits on the text side of bg;
    else move only its lightness to the nearest edge."""
    v = lc(hx, bg)
    on_side = (L_of(hx) > L_of(bg)) == lighter
    if on_side and lo <= v <= hi:
        return hx, "exact (Lc %.1f)" % v
    L, C, h = cl.srgb_to_oklch(cl.parse_hex(hx))
    h = h if h == h else 0.0
    tgt = lo if (not on_side or v < lo) else hi
    if on_side and v > hi:
        # move toward the background to reduce contrast: search the hi edge from the bg side
        nh = _at_lc_from_bg(bg, h, C, hi, lighter)
    else:
        nh = at_lc(bg, h, C, tgt, lighter)
    return nh, "L %.3f->%.3f, Lc %.1f->%.1f" % (L, L_of(nh), v if on_side else -v, lc(nh, bg))


def _at_lc_from_bg(bg: str, h: float, C: float, target: float, lighter: bool) -> str:
    """The color closest to bg (on the text side) whose |Lc| is at least target."""
    return at_lc(bg, h, C, target, lighter)


def mix_oklab(a: str, b: str, t: float) -> str:
    la = cl.srgb_to_oklab(cl.parse_hex(a))
    lb = cl.srgb_to_oklab(cl.parse_hex(b))
    m = tuple(la[i] + (lb[i] - la[i]) * t for i in range(3))
    return cl.to_hex(cl.clip_srgb(cl.oklab_to_srgb(m)))


def hue_dir(frm: float, to: float) -> float:
    d = (to - frm) % 360.0
    return 1.0 if d <= 180.0 else -1.0


def wcag(a: str, b: str) -> float:
    return cl.contrast_ratio(a, b)


def at_wcag(bg: str, h: float, C: float, ratio: float, lighter: bool, start_lc: float = 30.0) -> str:
    v = start_lc
    hx = at_lc(bg, h, C, v, lighter)
    while wcag(hx, bg) < ratio and v < 108:
        v += 2.0
        hx = at_lc(bg, h, C, v, lighter)
    return hx


# ---------------------------------------------------------------- Hungarian assignment

def hungarian(cost: List[List[float]]) -> List[int]:
    """Minimum-cost assignment, rows <= cols. Returns the column for each row."""
    n, m = len(cost), len(cost[0])
    INF = float("inf")
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    p, way = [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    res = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            res[p[j] - 1] = j - 1
    return res


# ---------------------------------------------------------------- background and text

def neutral_tint(tokens: List[Token], brand: Optional[Token]) -> Tuple[float, float]:
    """Hue and chroma for synthesized neutrals: from the neutral tokens, else the brand."""
    neu = [t for t in tokens if t.role in ("fg", "bg", "surface", "muted", "faint", "neutral", "border") and t.C < 0.12]
    tinted = [t for t in neu if t.C >= 0.006]
    if tinted:
        h = circ_mean([t.h for t in tinted], [t.C for t in tinted])
        cs = sorted(t.C for t in tinted)
        return h, max(0.004, min(0.03, cs[len(cs) // 2]))
    if brand is not None:
        return brand.h, 0.008
    return 250.0, 0.0


def choose_bg_fg(mode: str, pal: ModePalette, derived: bool, tint: Tuple[float, float],
                 prefer: Dict[str, Token], force: Optional[Dict[str, Slot]] = None) -> Tuple[Slot, Slot, List[str]]:
    notes = []
    force = force or {}
    hN, cN = tint
    T = TARGETS[mode]
    lighter = mode == "dark"
    toks = pal.tokens
    # ---- background
    bt = prefer.get("bg")
    if bt is None and not derived:
        bt = pal.bg
    if bt is not None and not derived or (bt is not None and "bg" in prefer):
        bg = Slot(bt.hex, "token:%s" % bt.name, "exact", "token")
        if mode == "light" and not derived and "bg" not in prefer:
            # A terminal is a text surface. A lighter surface also gives faint text more contrast.
            cards = [t for t in toks if t.role in ("bg", "surface") and not t.state and not t.soft
                     and set(t.words) & TEXT_SURFACE_W and t.C <= 0.02 and t.L >= bt.L + TEXT_SURFACE_MIN_DL]
            if cards:
                cards.sort(key=lambda t: (0 if t.semantic else 1, -t.L, t.order))
                c = cards[0]
                bg = Slot(c.hex, "token:%s" % c.name,
                          "exact; the surface that carries text (%s %s is the color behind the cards)" % (bt.name, bt.hex),
                          "token")
    elif derived and mode == "dark":
        # light-only system: the ink/text token becomes the dark background
        inks = [t for t in toks if t.role in ("fg", "muted") and t.L <= 0.45 and not t.state]
        inks.sort(key=lambda t: (0 if 0.14 <= t.L <= 0.32 and t.C <= 0.06 else 1,
                                 0 if set(t.words) & {"heading", "title", "ink", "strong"} else 1, t.L))
        if not inks:
            inks = sorted([t for t in toks if t.L <= 0.40 and t.C <= 0.10 and t.role not in ("on-color",)],
                          key=lambda t: t.L)
        if inks:
            t = inks[0]
            if 0.14 <= t.L <= 0.32 and t.C <= 0.06:
                bg = Slot(t.hex, "token:%s" % t.name, "exact; light-mode text token as dark background", "token")
            else:
                nL, nC = max(0.16, min(0.26, t.L)), min(t.C, 0.05)
                bg = Slot(oklch_hex(nL, nC, t.h), "token:%s" % t.name,
                          "light-mode text token as dark background; L %.3f->%.3f C %.3f->%.3f" % (t.L, nL, t.C, nC),
                          "derived")
        else:
            bg = Slot(oklch_hex(0.22, min(cN, 0.02), hN), "synthesized", "L 0.22, neutral tint", "synth")
    elif derived and mode == "light":
        papers = sorted([t for t in toks if t.L >= 0.85 and t.C < 0.05 and not t.state],
                        key=lambda t: (0 if t.role == "fg" else 1 if t.role in ("bg", "surface") else 2, -t.L))
        if papers and papers[0].L >= 0.93:
            t = papers[0]
            bg = Slot(t.hex, "token:%s" % t.name, "exact; dark-mode text token as light background", "token")
        else:
            bg = Slot(oklch_hex(0.975, min(cN, 0.012), hN), "synthesized", "L 0.975, neutral tint", "synth")
    else:
        L = 0.975 if mode == "light" else 0.22
        bg = Slot(oklch_hex(L, min(cN, 0.015), hN), "synthesized", "L %.3f, neutral tint" % L, "synth")
    if isinstance(force.get("background"), Slot):
        bg = force["background"]
    elif not derived and pal.bg is None and "bg" not in prefer:
        rej = [t for t in toks if t.role in ("bg", "surface") and not t.state]
        if rej:
            notes.append("no %s background token fits (for example %s %s, L %.2f); synthesized one"
                         % (mode, rej[0].name, rej[0].hex, rej[0].L))
    if "background" not in force and (mode == "dark" and L_of(bg.hex) >= 0.5 or mode == "light" and L_of(bg.hex) < 0.5):
        L = 0.975 if mode == "light" else 0.22
        notes.append("background %s does not suit a %s theme; synthesized one" % (bg.hex, mode))
        bg = Slot(oklch_hex(L, min(cN, 0.015), hN), "synthesized", "L %.3f, neutral tint" % L, "synth")
    # ---- text
    if "foreground" in force:
        return bg, force["foreground"], notes
    ft = prefer.get("fg")
    if ft is None and not derived:
        ft = pick_fg(toks, mode, None) if pal.fg is None else pal.fg
    if ft is None and derived:
        if mode == "dark":
            c = sorted([t for t in toks if t.L >= 0.85 and t.C < 0.05 and t.role in ("bg", "surface", "fg", "neutral", "unknown")],
                       key=lambda t: (0 if t.role == "bg" else 1 if t.role == "surface" else 2, -t.C, t.order))
        else:
            c = sorted([t for t in toks if t.L <= 0.35 and t.C < 0.08 and t.role in ("bg", "surface", "fg", "neutral", "unknown")],
                       key=lambda t: (0 if t.role == "bg" else 1, t.L))
        ft = c[0] if c else None
    lo, hi = T["fg_keep"]
    if ft is not None:
        hx, note = fit_lc(ft.hex, bg.hex, lo, hi, lighter)
        if wcag(hx, bg.hex) < 7.0:
            hx = at_wcag(bg.hex, ft.h, ft.C, 7.0, lighter, start_lc=lc(hx, bg.hex))
            note += "; darker/lighter for WCAG 7"
        if derived:
            note += "; %s" % ("light-mode paper as dark text" if mode == "dark" else "dark-mode background as light text")
        fg = Slot(hx, "token:%s" % ft.name, note, "token")
    else:
        fg = Slot(at_lc(bg.hex, hN, min(cN, 0.02), T["fg"], lighter), "synthesized",
                  "neutral tint, Lc %.0f" % T["fg"], "synth")
    return bg, fg, notes


# ---------------------------------------------------------------- the mapper

def _synth_hue(s: str, brand: Optional[Token], win: float) -> Tuple[float, str]:
    h = SYNTH_HUES[s]
    note = "hue %.0f" % h
    if brand is not None and brand.C >= MIN_CHROMA_CHROMATIC:
        diff = hue_dist(h, brand.h)
        if diff <= HARMONIZE_MAX_DIFF:
            rot = min(0.5 * diff, HARMONIZE_MAX, 0.4 * win) * hue_dir(h, brand.h)
            h = (h + rot) % 360.0
            note += " turned %+.1f toward the brand" % rot
    return h, note


def map_mode(pal: ModePalette, mode: str, derived: bool = False, prefer: Optional[Dict[str, Token]] = None,
             chroma_floor: bool = True, force: Optional[Dict[str, Slot]] = None) -> dict:
    """Return {'slots': {key: Slot}, 'mode', 'derived', 'brand', 'notes', 'assignment'}."""
    prefer = prefer or {}
    T = TARGETS[mode]
    lighter = mode == "dark"
    toks = pal.tokens
    brand = prefer.get("brand") or pal.brand
    if brand is not None:
        # steps of the brand ramp (for example an accessible or action orange): for the cursor
        brand.ramp = [t for t in toks if t is not brand and not t.state and not t.soft and t.hex != brand.hex
                      and t.C >= BRAND_CARRIED_C * brand.C and hue_dist(t.h, brand.h) <= BRAND_RAMP_HUE]
    tint = neutral_tint(toks, brand)
    notes = []
    bg, fg, n = choose_bg_fg(mode, pal, derived, tint, prefer, force)
    ffl = fg_floor(bg.hex, mode)
    if fg.origin != "override" and lc(fg.hex, bg.hex) < ffl:
        # faint (SGR 2) text needs a stronger text color (faint_text gate)
        nfg = Slot(at_lc(bg.hex, fg.h, fg.C, ffl, lighter), fg.source,
                   (fg.note + "; " if fg.note else "") + "lightness moved to Lc %.0f for faint text" % ffl, fg.origin, fg.h, fg.C)
        nfg.original = fg.original
        fg = nfg
    notes += n
    used = set()
    for s in (bg, fg):
        if s.source.startswith("token:"):
            used.add(s.source[6:])

    # ---- hue slots: candidates and costs
    cands = [t for t in toks if t.C >= MIN_CHROMA_CHROMATIC and t.name not in used
             and t.role not in EXCLUDED_FROM_HUES and not t.state and not (t.soft and t.L > 0.85)]
    # one candidate for each hex: the semantic alias wins
    by_hex = {}
    for t in sorted(cands, key=lambda t: (0 if t.semantic else 1, 0 if t.strong else 1, t.order)):
        by_hex.setdefault(t.hex, t)
    cands = [t for t in cands if by_hex[t.hex] is t]
    cs = sorted(t.C for t in cands)
    brand_C = (cs[(len(cs) - 1) // 2] + cs[len(cs) // 2]) / 2 if cs else 0.12
    keep_lo, keep_hi = T["normal_keep"]
    base_lo = keep_lo

    slot_lo = T.get("normal_lo", {})

    def lo_for(h: float, C: float, s: Optional[str] = None) -> float:
        lo = slot_lo.get(s, min(slot_lo.values()) if slot_lo else base_lo)
        return max(lo, hue_floor(bg.hex, mode, 1.0, h, C))
    forced = {s: prefer[s] for s in SLOTS6 if s in prefer}
    for t in forced.values():
        if t in cands:
            cands.remove(t)
    lchange_w = 1.0 if derived else 2.0

    def named_slot(t: Token) -> Optional[str]:
        # a name signal counts only when the hue is near the named slot
        if t.strong and hue_dist(t.h, ANCHORS[mode][t.strong][0]) <= NAME_FORCED_WINDOW:
            return t.strong
        return None

    def adjusted_dL(t: Token) -> float:
        hx, _ = fit_lc(t.hex, bg.hex, lo_for(t.h, t.C), keep_hi, lighter)
        return abs(L_of(hx) - t.L)

    dls = [adjusted_dL(t) for t in cands]
    cost = []
    for s in SLOTS6:
        anchor, win = ANCHORS[mode][s]
        row = []
        for t, dl in zip(cands, dls):
            ns = named_slot(t)
            d = hue_dist(t.h, anchor)
            allowed = NAME_FORCED_WINDOW if ns == s else win
            if s in forced or d > allowed:
                row.append(1e3)
                continue
            c = (d / win) ** 2
            if ns == s:
                c = min(c, 1.0) - 1.2
            elif ns is not None:
                c += 4.0
            if t.weak == s:
                c -= 0.4
            elif t.weak is not None and ns is None:
                c += 0.4
            c += 0.6 * max(0.0, (0.09 - t.C) / 0.09)
            c += lchange_w * dl
            if t.semantic:
                c -= 0.15
            if brand is not None and t.name == brand.name:
                c -= 0.2
            row.append(c)
        row += [SYNTH_COST if k == SLOTS6.index(s) and s not in forced else 1e3 for k in range(6)]
        cost.append(row)
    assign = hungarian(cost)

    slots = {}
    assignment = {}
    assigned_tok = {}
    for i, s in enumerate(SLOTS6):
        idx = ANSI_INDEX[s]
        j = assign[i]
        t = forced.get(s)
        if t is None and j < len(cands) and cost[i][j] < 500:
            t = cands[j]
        if t is not None:
            C = t.C
            hx = t.hex
            note_pre = ""
            if chroma_floor and mode == "dark" and s in PASTEL_FLOOR and C < PASTEL_FLOOR[s]:
                C = PASTEL_FLOOR[s]
                hx = oklch_hex(t.L, C, t.h)
                note_pre = "chroma %.3f->%.3f (pastel floor); " % (t.C, C)
            hx2, note = fit_lc(hx, bg.hex, lo_for(t.h, C, s), keep_hi, lighter)
            if wcag(hx2, bg.hex) < MIN_WCAG_HUE:
                # the low edge of the Lc band can be below WCAG 3 (pale hues on a light background)
                hx2 = at_wcag(bg.hex, t.h, C, MIN_WCAG_HUE, lighter, start_lc=lc(hx2, bg.hex))
                note += "; lightness moved to WCAG %.1f" % cl.GATES["ansi_normal"]["gate"]["min_wcag"]
            origin = "brand" if brand is not None and t.name == brand.name else (
                "token-named" if named_slot(t) == s else "token")
            if s in forced:
                origin = "override"
            slots[idx] = Slot(hx2, "token:%s" % t.name, note_pre + note, origin, t.h, C)
            used.add(t.name)
            assignment[s] = t.name
            assigned_tok[s] = t
        else:
            anchor, win = ANCHORS[mode][s]
            h, hnote = _synth_hue(s, brand, win)
            C = max(SYNTH_C_FLOOR[s], min(SYNTH_C_MAX[s], brand_C))
            tgt = max(T["normal"][s], lo_for(h, C, s))
            slots[idx] = Slot(at_lc(bg.hex, h, C, tgt, lighter), "synthesized",
                              "%s, C %.3f, Lc %.0f" % (hnote, C, tgt), "synth", h, C)
            assignment[s] = None

    # ---- brand: when no hue slot shows the brand color, it becomes the bright step of the nearest hue
    brand_bright = None
    if brand is not None and brand.C >= MIN_CHROMA_CHROMATIC and brand.name not in used:
        near = sorted((hue_dist(slots[ANSI_INDEX[s]].h, brand.h), s) for s in SLOTS6)
        carried = any(hue_dist(slots[ANSI_INDEX[s]].h, brand.h) <= BRAND_CARRIED_HUE
                      and slots[ANSI_INDEX[s]].C >= BRAND_CARRIED_C * brand.C for s in SLOTS6)
        if not carried and near[0][0] <= BRAND_BRIGHT_MAX_DIFF and slots[ANSI_INDEX[near[0][1]]].C >= 0.04:
            brand_bright = near[0][1]

    # ---- brights
    blo0, bhi = T["bright_keep"]
    for s in SLOTS6:
        idx = ANSI_INDEX[s]
        n_slot = slots[idx]
        n_lc = lc(n_slot.hex, bg.hex)
        blo = max(blo0, hue_floor(bg.hex, mode, 1.0, n_slot.h, n_slot.C * (1.0 if mode == "dark" else 1.05)))
        if s == brand_bright:
            lo_b = max(cl.GATES["ansi_bright"]["target_" + mode]["min_lc"], n_lc + BRAND_BRIGHT_STEP,
                       hue_floor(bg.hex, mode, 1.0, brand.h, brand.C))
            v = lc(brand.hex, bg.hex)
            bh = brand.h
            if ((brand.L > L_of(bg.hex)) == lighter) and lo_b <= v <= bhi:
                hx, note = brand.hex, "exact (Lc %.1f)" % v
            else:
                # The gamut cuts chroma when the lightness moves. A small hue turn can keep more of it.
                best_c = None
                room = BRAND_BRIGHT_MAX_DIFF + 3.0   # stay inside the bright_relation gate (30 degrees)
                for k in range(-int(BRAND_HUE_TURN), int(BRAND_HUE_TURN) + 1, 2):
                    h2 = (brand.h + k) % 360.0
                    if hue_dist(h2, n_slot.h) > room:
                        continue
                    c2 = at_lc(bg.hex, h2, brand.C, lo_b, lighter)
                    key = (round(cl.srgb_to_oklch(cl.parse_hex(c2))[1], 2), -abs(k))
                    if best_c is None or key > best_c[0]:
                        best_c = (key, c2, h2, k)
                if best_c is None:
                    best_c = (None, at_lc(bg.hex, brand.h, brand.C, lo_b, lighter), brand.h, 0)
                hx, bh = best_c[1], best_c[2]
                note = "lightness moved to Lc %.0f" % lo_b
                if best_c[3]:
                    note += ", hue turned %+d to keep chroma" % best_c[3]
            slots[idx + 8] = Slot(hx, "token:%s" % brand.name,
                                  "brand color as the bright step of %s (hue %+.0f); %s"
                                  % (s, hue_dist(n_slot.h, bh) * hue_dir(n_slot.h, bh), note),
                                  "brand", bh, brand.C)
            used.add(brand.name)
            continue
        if mode == "dark":
            tgt = min(T["bright_max"], max(n_lc + T["bright_step"], 70.0))
        else:
            tgt = min(T["bright_max"], max(n_lc + T["bright_step"], T["bright"][s]))
        tgt = max(tgt, blo)
        best = None
        # a token that was too strong for the normal band is the exact bright color (C9 D5)
        at = assigned_tok.get(s)
        if at is not None and n_slot.hex != at.hex:
            v = lc(at.hex, bg.hex)
            on_side = (at.L > L_of(bg.hex)) == lighter
            if on_side and max(blo, n_lc + 4) <= v <= bhi and cl.delta_e_ok_rgb(at.hex, n_slot.hex) >= 0.03:
                slots[idx + 8] = Slot(at.hex, "token:%s" % at.name, "exact (Lc %.1f); the normal color is its lighter step" % v
                                      if not lighter else "exact (Lc %.1f)" % v, "token", at.h, at.C)
                continue
        for t in toks:
            if t.name in used or t.C < MIN_CHROMA_CHROMATIC or t.role in EXCLUDED_FROM_HUES or t.soft:
                continue
            if t.hex in {x.hex for x in slots.values()}:
                continue
            if hue_dist(t.h, n_slot.h) > 15 or t.C < 0.6 * n_slot.C:
                continue
            # the token must be nearer to this hue than to another hue: an orange that sits between red
            # and yellow is the bright step of one of them only (else two bright colors look the same)
            if any(hue_dist(t.h, slots[ANSI_INDEX[o]].h) < hue_dist(t.h, n_slot.h) for o in SLOTS6 if o != s):
                continue
            v = lc(t.hex, bg.hex)
            on_side = (t.L > L_of(bg.hex)) == lighter
            if on_side and max(blo, n_lc + 4) <= v <= bhi:
                d = abs(v - tgt) / 20.0
            else:
                continue
            if best is None or d < best[0]:
                best = (d, t)
        if best is not None and cl.delta_e_ok_rgb(best[1].hex, n_slot.hex) >= 0.03:
            t = best[1]
            slots[idx + 8] = Slot(t.hex, "token:%s" % t.name, "exact (Lc %.1f)" % lc(t.hex, bg.hex), "token", t.h, t.C)
            used.add(t.name)
        else:
            C = n_slot.C * (1.0 if mode == "dark" else 1.05)
            slots[idx + 8] = Slot(at_lc(bg.hex, n_slot.h, C, tgt, lighter), "derived:%s" % s,
                                  "hue and chroma of %s, Lc %.0f" % (s, tgt), "derived", n_slot.h, C)

    # ---- grays
    hN, cN = tint
    fg_lc = lc(fg.hex, bg.hex)
    bgL, bgC, bgh = cl.srgb_to_oklch(cl.parse_hex(bg.hex))
    bgh = bgh if bgh == bgh else hN
    if mode == "dark":
        L0 = bgL - 0.07 if bgL >= 0.18 else bgL + 0.06
        slots[0] = Slot(oklch_hex(L0, min(bgC, 0.03), bgh), "derived:background",
                        "dark surface (L %.2f) for black text on colored bars" % L0, "derived", bgh, min(bgC, 0.03))
        slots[7] = Slot(at_lc(bg.hex, hN, min(cN, 0.02), min(T["n7"], fg_lc - 4), True), "synthesized",
                        "neutral tint, Lc %.0f" % min(T["n7"], fg_lc - 4), "synth", hN, min(cN, 0.02))
        v15 = min(100.0, max(T["n15"], fg_lc))
        slots[15] = Slot(at_lc(bg.hex, hN, min(cN, 0.012), v15, True), "synthesized",
                         "neutral tint, Lc %.0f" % v15, "synth", hN, min(cN, 0.012))
    else:
        Lf, Cf, hf = cl.srgb_to_oklch(cl.parse_hex(fg.hex))
        hf = hf if hf == hf else hN
        v0 = max(T["n0"], fg_lc)
        slots[0] = Slot(at_lc(bg.hex, hf, min(Cf, 0.03), v0, False), "derived:foreground",
                        "full-strength ink in the text hue", "derived", hf, min(Cf, 0.03))
        slots[7] = Slot(at_lc(bg.hex, hN, min(cN, 0.015), T["n7"], False), "synthesized",
                        "light gray that stays readable, Lc %.0f" % T["n7"], "synth", hN, min(cN, 0.015))
        slots[15] = Slot(at_lc(bg.hex, hN, min(cN, 0.01), T["n15"], False), "synthesized",
                         "lighter gray that stays readable, Lc %.0f" % T["n15"], "synth", hN, min(cN, 0.01))
    # brightBlack: a muted/faint text token when one fits, else synthesized
    lo8, hi8 = 38.0, min(60.0, fg_lc - 25.0)
    best = None
    for t in toks:
        if t.role not in ("muted", "faint", "fg", "neutral") or t.name in used or t.state or t.C > 0.08:
            continue
        hx, note = fit_lc(t.hex, bg.hex, lo8, max(lo8, hi8), lighter)
        dl = abs(L_of(hx) - t.L)
        if dl > 0.12:
            continue
        d = dl + (0 if t.role in ("muted", "faint") else 0.05) + (0 if t.semantic else 0.01)
        if best is None or d < best[0]:
            best = (d, t, hx, note)
    if best is not None:
        _, t, hx, note = best
        slots[8] = Slot(hx, "token:%s" % t.name, note, "token", t.h, t.C)
        used.add(t.name)
    else:
        slots[8] = Slot(at_lc(bg.hex, hN, min(cN, 0.02), T["n8"], lighter), "synthesized",
                        "neutral tint, Lc %.0f" % T["n8"], "synth", hN, min(cN, 0.02))

    # ---- cursor, selection, bold
    out = {"background": bg, "foreground": fg}
    for i in range(16):
        out[i] = slots[i]
    out["bold"] = make_bold(bg, fg, toks, mode, tint, used)
    out["cursor"] = make_cursor(bg.hex, brand, fg, lighter, T)
    out["selection"] = make_selection(out, brand, mode)
    unused = [t.name for t in toks if t.name not in used and t.name != (brand.name if brand else None)]
    return {"slots": out, "mode": mode, "derived": derived, "brand": brand.name if brand else None,
            "brand_hex": brand.hex if brand else None, "notes": notes, "assignment": assignment,
            "unused_tokens": unused, "neutral_tint": [round(tint[0], 1), round(tint[1], 3)],
            "brand_chroma": round(brand_C, 3), "token_hex": {t.name: t.hex for t in toks}}


def make_bold(bg: Slot, fg: Slot, toks: List[Token], mode: str, tint: Tuple[float, float], used: set) -> Slot:
    """Bold text. A heading text token is the bold color when it is stronger than the text. Dark mode
    without one: the text color, a step brighter (below the halation gate). Else: the text color."""
    lighter = mode == "dark"
    fg_lc = lc(fg.hex, bg.hex)
    top = cl.GATES["halation"]["gate"]["max_lc"] - 1.5 if lighter else 108.0
    best = None
    for t in toks:
        if t.role != "fg" or t.state or t.C > 0.08 or not (set(t.words) & HEADING_W):
            continue
        v = lc(t.hex, bg.hex)
        if ((t.L > L_of(bg.hex)) == lighter) and fg_lc + 1.0 <= v <= top and wcag(t.hex, bg.hex) >= 7.0:
            if best is None or v > best[0]:
                best = (v, t)
    if best is not None:
        v, t = best
        used.add(t.name)
        return Slot(t.hex, "token:%s" % t.name, "exact (Lc %.1f); heading text token" % v, "token")
    if lighter and fg_lc + BOLD_STEP_MIN <= top:
        hN, cN = tint
        v = min(top, fg_lc + BOLD_STEP_DARK)
        return Slot(at_lc(bg.hex, hN, min(cN, 0.012), v, True), "derived:foreground",
                    "the text color, brighter: Lc %.0f" % v, "derived")
    return Slot(fg.hex, "alias:foreground", "same as text", "alias")


def make_cursor(bg: str, brand: Optional[Token], fg: Slot, lighter: bool, T: dict) -> Slot:
    if brand is None:
        return Slot(fg.hex, "alias:foreground", "no brand color", "alias")
    if wcag(brand.hex, bg) >= T["cursor_wcag"] and ((L_of(brand.hex) > L_of(bg)) == lighter):
        return Slot(brand.hex, "token:%s" % brand.name, "exact (WCAG %.2f)" % wcag(brand.hex, bg), "brand")
    # the brand color is too weak here: a step of the brand ramp that passes is better than a new color
    ramp = [t for t in getattr(brand, "ramp", []) if wcag(t.hex, bg) >= T["cursor_wcag"]
            and ((t.L > L_of(bg)) == lighter)]
    if ramp:
        ramp.sort(key=lambda t: (cl.delta_e_ok_rgb(t.hex, brand.hex), 0 if t.semantic else 1, t.order))
        t = ramp[0]
        return Slot(t.hex, "token:%s" % t.name,
                    "exact (WCAG %.2f); a step of the brand ramp, the brand color %s is too weak for a cursor here"
                    % (wcag(t.hex, bg), brand.hex), "brand", t.h, t.C)
    hx = at_wcag(bg, brand.h, brand.C, T["cursor_wcag"], lighter, start_lc=40.0)
    return Slot(hx, "token:%s" % brand.name, "lightness moved to WCAG %.1f" % T["cursor_wcag"], "brand",
                brand.h, brand.C)


SEL_MIN_WCAG_VS_BG = 1.10  # C9 D2: dEok alone inflates near black; the selection must also differ in luminance


def selection_score(sel: str, slots: dict) -> Tuple[int, float]:
    """(gate failures, target miss) for one selection color. Lower is better."""
    bg = slots["background"].hex
    fg = slots["foreground"].hex
    G = cl.GATES["selection"]
    fails = 0
    miss = 0.0
    cr = wcag(fg, sel)
    v = lc(fg, sel)
    bgs = [bg] + [c for _d, c in cl.translucent_backgrounds(bg, slots["background"].alpha)]
    d = min(cl.delta_e_ok_rgb(sel, b) for b in bgs)
    amin = min(lc(slots[i].hex, sel) for i in list(range(1, 7)) + list(range(9, 15)))
    if cr < G["gate"]["fg_min_wcag"] or v < G["gate"]["fg_min_lc"]:
        fails += 1
    if d < G["gate"]["sel_min_dEok_vs_bg"] or min(wcag(sel, b) for b in bgs) < SEL_MIN_WCAG_VS_BG:
        fails += 1
    if amin < G["gate"]["ansi_min_lc"]:
        fails += 1
    miss += max(0.0, G["target"]["fg_min_lc"] - v) / 10.0
    lo, hi = G["target"]["sel_dEok_vs_bg_range"]
    miss += max(0.0, lo - d) * 20 + max(0.0, d - hi) * 20
    miss += max(0.0, G["target"]["ansi_min_lc"] - amin) / 10.0
    miss += abs(d - 0.09) * 2
    return fails, miss


def make_selection(slots: dict, brand: Optional[Token], mode: str) -> Slot:
    bg = slots["background"].hex
    fg = slots["foreground"].hex
    best = None
    tints = []
    if brand is not None:
        tints.append(("brand", brand.hex))
    tints.append(("text", fg))
    for label, tint in tints:
        for k in range(3, 51):
            t = k / 100.0
            sh = mix_oklab(bg, tint, t)
            f, m = selection_score(sh, slots)
            m += 0.0 if label == "brand" else 0.3
            key = (f, m)
            if best is None or key < best[0]:
                best = (key, sh, "OKLab mix of background and %s, %.2f" % (label, t))
    if best[0][0] > 0:
        bgL, bgC, bgh = cl.srgb_to_oklch(cl.parse_hex(bg))
        bgh = bgh if bgh == bgh else 0.0
        for k in range(3, 26):
            d = k / 100.0 * (1 if mode == "dark" else -1)
            sh = oklch_hex(bgL + d, bgC, bgh)
            f, m = selection_score(sh, slots)
            if (f, m) < best[0]:
                best = ((f, m), sh, "background lightness %+.2f" % d)
    return Slot(best[1], "mix:background+%s" % ("brand" if brand else "text"), best[2], "derived")
