"""gates.py - check a mapped theme against colorlab.GATES and repair it until every hard gate passes.

check() is stricter than colorlab.check_theme in one point: a missing SelectionColor or
CursorColor is a failure (Terminal would use its own default, which nobody checked).

repair() is a greedy local search. In each round it takes the first failure, lists the slots
that the failure names, and tries variants of each slot (lightness first, then hue and chroma,
then a synthesized replacement). It keeps the variant with the fewest failures; on a tie, the
smallest change. Slots with a higher priority (override > brand > named token > token >
derived > synthesized) move last. When the search stops with failures left, a fallback
replaces the chromatic slots with synthesized ones, then the grays. The search never moves the
background: theme.build() rebuilds the whole theme on a standard background when needed.
Every change is logged for the report.
"""
import re
from typing import Dict, List, Optional, Tuple

from . import colorlab as cl
from .mapper import (ANCHORS, ANSI_INDEX, PRIORITY, SEL_MIN_WCAG_VS_BG, SLOTS6, SYNTH_C_FLOOR, SYNTH_C_MAX, SYNTH_HUES, TARGETS, Slot,
                     at_lc, at_wcag, fg_floor, hue_floor, lc, L_of, make_cursor, make_selection, oklch_hex)

NAME_TO_INDEX = dict((n, i) for i, n in enumerate(cl.ANSI_NAMES))
MAX_ROUNDS = 60
MAX_EVALS = 8000   # gate checks per build (all repair rounds and fallbacks); a count, not a clock, so the
                   # output is the same on every computer


def theme_dict(slots: dict, mode: str, name: str = "") -> dict:
    return {"name": name, "mode": mode, "background": slots["background"].hex,
            "foreground": slots["foreground"].hex, "bold": slots["bold"].hex,
            "cursor": slots["cursor"].hex, "selection_background": slots["selection"].hex,
            "ansi": [slots[i].hex for i in range(16)], "background_alpha": slots["background"].alpha}


HUE_VS_TEXT_MIN_DE = 0.06


def check(slots: dict, mode: str) -> dict:
    """colorlab.check_theme (which also checks a translucent background over each desktop) plus three
    rules from the C9 review:
    - a missing selection or cursor color fails;
    - the selection must differ from the background in luminance too (WCAG >= 1.10);
    - each hue color must differ from the text color (dEok >= 0.06), else colored text reads as plain text."""
    res = cl.check_theme(theme_dict(slots, mode))
    for key, gid in (("selection", "selection"), ("cursor", "cursor")):
        if not slots.get(key):
            res["failures"].append({"id": gid, "detail": "no %s color" % key})
    if slots.get("selection"):
        bg = slots["background"]
        for desk, b in [(None, bg.hex)] + cl.translucent_backgrounds(bg.hex, bg.alpha):
            r = cl.contrast_ratio(slots["selection"].hex, b)
            if r < SEL_MIN_WCAG_VS_BG:
                f = {"id": "selection", "detail": "selection vs bg WCAG %.3f < %.2f (invisible)" % (r, SEL_MIN_WCAG_VS_BG)}
                if desk:
                    f["detail"] += " [desktop %s, bg %s]" % (desk, b)
                    f["desktop"] = desk
                res["failures"].append(f)
    fg = slots["foreground"].hex
    for i in list(range(1, 7)) + list(range(9, 15)):
        d = cl.delta_e_ok_rgb(slots[i].hex, fg)
        if d < HUE_VS_TEXT_MIN_DE:
            res["failures"].append({"id": "hue_vs_text", "detail": "%s %s dEok %.3f from the text color" % (cl.ANSI_NAMES[i], slots[i].hex, d)})
    res["pass"] = not res["failures"]
    res["failed_gate_ids"] = sorted(set(f["id"] for f in res["failures"]))
    return res


# ---------------------------------------------------------------- what a failure names

def implicated(f: dict) -> List[object]:
    gid, det = f["id"], f["detail"]
    words = re.findall(r"[A-Za-z]+", det)
    names = [w for w in words if w in NAME_TO_INDEX]
    idx = [NAME_TO_INDEX[n] for n in names]
    if gid == "fg_contrast":
        return ["foreground"]
    if gid == "faint_text":
        return ["foreground"] if "foreground" in words else idx[:1]
    if gid == "hue_vs_text":
        # the text color can move too: on a very dark bg the faint floor leaves the hue colors little room
        return idx[:1] + ["foreground"]
    if gid == "halation":
        first = det.split()[0]
        return [NAME_TO_INDEX.get(first, first)]
    if gid in ("ansi_normal", "ansi_bright", "dim_brightBlack", "grays_dark", "inks_light"):
        return idx[:1] or [8]
    if gid == "bright_relation":
        return idx[:1] + ["derive:%d" % idx[0]] if idx else []
    if gid == "separation":
        return idx[:2]
    if gid == "cvd":
        m = re.match(r"(\w+)/(\w+)", det)
        return [NAME_TO_INDEX[m.group(1)], NAME_TO_INDEX[m.group(2)]] if m else []
    if gid == "selection":
        return ["selection"]
    if gid == "cursor":
        return ["cursor"]
    if gid == "bold":
        return ["bold"]
    if gid == "text_on_color":
        return idx[1:2] + [0]
    return []


# ---------------------------------------------------------------- slot variants

def _lc_grid(mode: str, kind: str, floor: float = 46.0) -> List[float]:
    if kind == "chromatic":
        lo = int(max(46.0, floor))
        return [float(x) for x in (range(lo, 101, 3) if mode == "dark" else range(lo, 92, 2))]
    return [float(x) for x in range(30, 106, 3)]


def variants(key, slots: dict, mode: str) -> List[Tuple[int, Slot, str]]:
    """Return [(stage, Slot, note)] for one slot. Stage 0 = lightness only, 1 = hue/chroma,
    2 = synthesized replacement. The search stops at the first stage that helps."""
    bg = slots["background"].hex
    lighter = mode == "dark"
    out = []
    if key == "selection":
        return []
    if key == "cursor":
        cur = slots["cursor"]
        for r in (3.2, 4.5, 6.0, 8.0):
            hx = at_wcag(bg, cur.h, max(cur.C, 0.0), r, lighter, start_lc=30.0)
            out.append((0, _mk(cur, hx, "WCAG %.1f" % r), "lightness for WCAG %.1f" % r))
        return out
    if key == "bold":
        f = slots["foreground"]
        return [(0, _mk(slots["bold"], f.hex, "same as text"), "bold = text")]
    if isinstance(key, str) and key.startswith("derive:"):
        i = int(key.split(":")[1])
        if 9 <= i <= 14:
            n, b = slots[i - 8], slots[i]
            v = max(lc(b.hex, bg), lc(n.hex, bg) + (8 if mode == "dark" else 10),
                    hue_floor(bg, mode, slots["background"].alpha, n.h, n.C))
            hx = at_lc(bg, n.h, n.C, min(v, 100.0), lighter)
            s = Slot(hx, "derived:%s" % cl.ANSI_NAMES[i - 8], "hue and chroma of the normal color",
                     "derived", n.h, n.C)
            s.original = b.original
            return [(0, s, "bright derived from normal")]
        return []
    s = slots[key]
    chromatic = isinstance(key, int) and (1 <= key <= 6 or 9 <= key <= 14)
    kind = "chromatic" if chromatic else "neutral"
    alpha = slots["background"].alpha
    floor = hue_floor(bg, mode, alpha, s.h, s.C) if chromatic else 46.0
    grid = _lc_grid(mode, kind, floor)
    if key == "foreground":
        # never offer a text color whose faint form fails (C9 repeat, review A1)
        grid = [v for v in grid if v >= fg_floor(bg, mode, alpha)] or [fg_floor(bg, mode, alpha)]
    for v in grid:
        hx = at_lc(bg, s.h, s.C, v, lighter)
        out.append((0, _mk(s, hx, "Lc %.0f" % v), "lightness to Lc %.0f" % v))
    if mode == "dark" and key == 0:
        bL = L_of(bg)
        for d in (-0.10, -0.07, -0.04, 0.04, 0.07, 0.10):
            if 0.0 <= bL + d <= 1.0:
                out.append((0, _mk(s, oklch_hex(bL + d, s.C, s.h), "bg L %+.2f" % d), "black at bg L %+.2f" % d))
    if not chromatic:
        return out
    pri = PRIORITY.get(s.origin, 0)
    hue_steps = (-24, -16, -10, -5, 5, 10, 16, 24) if pri <= 1 else ((-10, -5, 5, 10) if pri <= 3 else (-6, 6))
    cur_lc = lc(s.hex, bg)
    lcs = sorted(set([cur_lc] + [x for x in _lc_grid(mode, kind, floor)[::2]]))
    for dh in hue_steps:
        for cf in (1.0, 0.75, 1.3):
            for v in lcs:
                h = (s.h + dh) % 360.0
                C = max(0.03, min(0.25, s.C * cf))
                hx = at_lc(bg, h, C, max(v, hue_floor(bg, mode, alpha, h, C)), lighter)
                out.append((1, _mk(s, hx, "hue %+d, C x%.2f, Lc %.0f" % (dh, cf, v), h, C),
                            "hue %+d, chroma x%.2f, Lc %.0f" % (dh, cf, v)))
    base = key if key < 8 else key - 8
    nm = SLOTS6[base - 1]
    for dh in (0, -8, 8):
        h = (SYNTH_HUES[nm] + dh) % 360.0
        C = (SYNTH_C_FLOOR[nm] + SYNTH_C_MAX[nm]) / 2
        for v in lcs:
            hx = at_lc(bg, h, C, max(v, hue_floor(bg, mode, alpha, h, C)), lighter)
            ns = Slot(hx, "synthesized", "replaced: hue %.0f C %.3f Lc %.0f" % (h, C, v), "synth", h, C)
            ns.original = s.original
            out.append((2, ns, "replaced by synthesized %s (hue %.0f, Lc %.0f)" % (nm, h, v)))
    return out


def _mk(s: Slot, hx: str, note: str, h: Optional[float] = None, C: Optional[float] = None) -> Slot:
    n = Slot(hx, s.source, (s.note + "; " if s.note else "") + "repair: " + note, s.origin,
             s.h if h is None else h, s.C if C is None else C)
    n.original = s.original
    return n


def _apply(slots: dict, target, cand: Slot, mode: str, brand) -> dict:
    """Put cand into slots; return the old values of every key that changed. A normal color
    takes its derived bright with it; the text color takes its bold and cursor aliases."""
    saved = {target: slots[target]}
    slots[target] = cand
    if target == "foreground":
        # bold and cursor that copy the text color follow it
        for k in ("bold", "cursor"):
            if slots[k].source == "alias:foreground":
                saved[k] = slots[k]
                n = slots[k].copy()
                n.hex, n.h, n.C = cand.hex, cand.h, cand.C
                slots[k] = n
    if isinstance(target, int) and 1 <= target <= 6 and slots[target + 8].origin == "derived":
        bg = slots["background"].hex
        b = slots[target + 8]
        v = min(100.0, max(lc(b.hex, bg), lc(cand.hex, bg) + (8.0 if mode == "dark" else 10.0)))
        v = max(v, hue_floor(bg, mode, slots["background"].alpha, cand.h, cand.C))
        nb = Slot(at_lc(bg, cand.h, cand.C, v, mode == "dark"), b.source, "hue and chroma of the normal color",
                  "derived", cand.h, cand.C)
        nb.original = b.original
        saved[target + 8] = b
        slots[target + 8] = nb
    return saved


def _change(s: Slot) -> float:
    return cl.delta_e_ok_rgb(s.hex, s.original) * (1 + PRIORITY.get(s.origin, 0))


def quality(slots: dict, mode: str) -> float:
    """Soft cost of a palette: chromatic colors outside their Lc band, or with lost chroma."""
    T = TARGETS[mode]
    bg = slots["background"].hex
    pen = 0.0
    for i in list(range(1, 7)) + list(range(9, 15)):
        s = slots[i]
        lo, hi = T["normal_keep"] if i < 8 else T["bright_keep"]
        v = lc(s.hex, bg)
        pen += max(0.0, lo - v, v - hi) * 0.08
        C = cl.srgb_to_oklch(cl.parse_hex(s.hex))[1]
        want = min(s.C, 0.10)
        if C < 0.7 * want:
            pen += (0.7 * want - C) * 40.0
    return pen


def _score(slots: dict, mode: str) -> Tuple[int, float]:
    r = check(slots, mode)
    return len(r["failures"]), len(r["misses"]) * 0.5 + quality(slots, mode)



def _key_name(k) -> str:
    return cl.ANSI_NAMES[k] if isinstance(k, int) else str(k)


def repair(slots: dict, mode: str, brand=None, allow_fallback: bool = True,
           budget: Optional[dict] = None) -> Tuple[dict, List[str], dict]:
    """Return (slots, log, final check). Works on a copy; the input does not change.
    budget {"left": n} is shared by every repair of one build (default: MAX_EVALS)."""
    if budget is None:
        budget = {"left": MAX_EVALS}
    slots = dict((k, v.copy()) for k, v in slots.items())
    log = []
    for _round in range(MAX_ROUNDS):
        res = check(slots, mode)
        if res["pass"]:
            return slots, log, res
        nfail = len(res["failures"])
        progress = False
        for f in res["failures"]:
            if f["id"] == "selection" or (f["id"] == "cursor" and "no " in f["detail"]):
                sel = make_selection(slots, brand, mode)
                if sel.hex != slots["selection"].hex:
                    slots["selection"] = sel
                    log.append("selection re-solved -> %s (%s)" % (sel.hex, sel.note))
                    progress = True
                    break
            keys = implicated(f)
            keys.sort(key=lambda k: PRIORITY.get(slots[k].origin, 0) if k in slots else -1)
            best = None
            pool = []
            for k in keys:
                if k not in slots and not (isinstance(k, str) and k.startswith("derive:")):
                    continue
                target = int(k.split(":")[1]) if isinstance(k, str) and k.startswith("derive:") else k
                pool.extend((st, target, cand, note) for st, cand, note in variants(k, slots, mode))
            # all implicated slots compete inside a stage; a later stage runs only when needed
            for stage in (1, 2):
                for st, target, cand, note in pool:
                    if max(st, 1) != stage or budget["left"] <= 0:
                        continue
                    budget["left"] -= 1
                    saved = _apply(slots, target, cand, mode, brand)
                    sc = _score(slots, mode)
                    key = (sc[0], sc[1] + 5.0 * _change(cand))
                    slots.update(saved)
                    if best is None or key < best[0]:
                        best = (key, target, cand, note)
                if best is not None and best[0][0] < nfail:
                    break
            if best is not None and best[0][0] < nfail:
                _, target, cand, note = best
                old = slots[target].hex
                _apply(slots, target, cand, mode, brand)
                log.append("%s %s -> %s: %s (fixes %s)" % (_key_name(target), old, cand.hex, note, f["id"]))
                progress = True
                break
        if not progress:
            break
    res = check(slots, mode)
    if res["pass"] or not allow_fallback:
        return slots, log, res
    return fallback(slots, mode, brand, log, budget)


def fallback(slots: dict, mode: str, brand, log: List[str], budget: Optional[dict] = None) -> Tuple[dict, List[str], dict]:
    """Synthesize the slots that still fail, in growing steps, until every gate passes."""
    T = TARGETS[mode]
    lighter = mode == "dark"
    steps = ("chromatic", "grays")
    for step in steps:
        res = check(slots, mode)
        if res["pass"]:
            break
        bg = slots["background"].hex
        alpha = slots["background"].alpha
        if step == "chromatic":
            for nm in SLOTS6:
                i = ANSI_INDEX[nm]
                h, C = SYNTH_HUES[nm], (SYNTH_C_FLOOR[nm] + SYNTH_C_MAX[nm]) / 2
                nv = max(T["normal"][nm], hue_floor(bg, mode, alpha, h, C))
                n = at_lc(bg, h, C, nv, lighter)
                bv = max((nv + 8) if mode == "dark" else max(T["bright"][nm], nv + 6), hue_floor(bg, mode, alpha, h, C))
                slots[i] = Slot(n, "synthesized", "fallback: hue %.0f Lc %d" % (h, nv), "synth", h, C)
                slots[i + 8] = Slot(at_lc(bg, h, C, min(bv, 100), lighter), "derived:%s" % nm,
                                    "fallback: hue %.0f Lc %d" % (h, bv), "derived", h, C)
            log.append("fallback: all 12 chromatic colors synthesized from the research bands")
        elif step == "grays":
            fg_lc = lc(slots["foreground"].hex, bg)
            if mode == "dark":
                bL = L_of(bg)
                slots[0] = Slot(oklch_hex(bL - 0.07 if bL >= 0.18 else bL + 0.06, 0.01, 260), "synthesized", "fallback", "synth")
                slots[7] = Slot(at_lc(bg, 260, 0.01, min(78, fg_lc - 4), True), "synthesized", "fallback", "synth")
                slots[15] = Slot(at_lc(bg, 260, 0.008, min(100, max(92, fg_lc)), True), "synthesized", "fallback", "synth")
            else:
                slots[0] = Slot(at_lc(bg, 260, 0.015, 100, False), "synthesized", "fallback", "synth")
                slots[7] = Slot(at_lc(bg, 260, 0.01, 48, False), "synthesized", "fallback", "synth")
                slots[15] = Slot(at_lc(bg, 260, 0.008, 32, False), "synthesized", "fallback", "synth")
            slots[8] = Slot(at_lc(bg, 260, 0.02, max(33.0, min(45.0, fg_lc - 20)), lighter), "synthesized", "fallback", "synth")
            log.append("fallback: grays synthesized")
        slots["cursor"] = make_cursor(slots["background"].hex, brand, slots["foreground"], lighter, T)
        slots["selection"] = make_selection(slots, brand, mode)
        # run the local search again on the new state (no further fallback)
        slots, more, res = repair(slots, mode, brand, allow_fallback=False, budget=budget)
        log.extend(more)
    return slots, log, check(slots, mode)
