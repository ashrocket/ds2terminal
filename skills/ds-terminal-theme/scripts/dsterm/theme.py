"""theme.py - one call from a ModePalette to a checked, repaired theme.

build() runs: mapper.map_mode -> overrides (--set) -> gates.repair. It returns the slots,
the provenance, the repair log and the final gate check.
"""
import re
from typing import Dict, List, Optional, Tuple

from . import colorlab as cl
from . import gates as G
from . import mapper as M
from .roles import ModePalette, Token

ROLE_ALIASES = {
    "bg": "background", "background": "background",
    "fg": "foreground", "text": "foreground", "foreground": "foreground",
    "bold": "bold", "cursor": "cursor", "selection": "selection",
}
PREFER_ROLES = ("bg", "fg", "brand") + M.SLOTS6
TERMINAL_KEY = {"background": "BackgroundColor", "foreground": "TextColor", "bold": "TextBoldColor",
                "cursor": "CursorColor", "selection": "SelectionColor"}
for _i, _k in enumerate(("ANSIBlackColor", "ANSIRedColor", "ANSIGreenColor", "ANSIYellowColor",
                         "ANSIBlueColor", "ANSIMagentaColor", "ANSICyanColor", "ANSIWhiteColor",
                         "ANSIBrightBlackColor", "ANSIBrightRedColor", "ANSIBrightGreenColor",
                         "ANSIBrightYellowColor", "ANSIBrightBlueColor", "ANSIBrightMagentaColor",
                         "ANSIBrightCyanColor", "ANSIBrightWhiteColor")):
    TERMINAL_KEY[_i] = _k


class OverrideError(ValueError):
    pass


def slot_key(role: str):
    """'red' -> 1, 'brightRed' / 'bright-red' -> 9, '12' -> 12, 'fg' -> 'foreground'."""
    r = role.strip()
    low = r.lower().replace("-", "").replace("_", "")
    if low in ROLE_ALIASES:
        return ROLE_ALIASES[low]
    if re.fullmatch(r"\d{1,2}", r) and 0 <= int(r) <= 15:
        return int(r)
    for i, n in enumerate(cl.ANSI_NAMES):
        if n.lower() == low:
            return i
    raise OverrideError("unknown role %r (use bg, fg, bold, cursor, selection, black..brightWhite or 0..15)" % role)


def parse_hex(v: str) -> str:
    v = v.strip()
    if not re.fullmatch(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v):
        raise OverrideError("bad color %r (use #rrggbb)" % v)
    return cl.to_hex(cl.parse_hex(v if v.startswith("#") else "#" + v))


def parse_pairs(items: Optional[List[str]], what: str) -> List[Tuple[str, str]]:
    out = []
    for it in items or []:
        if "=" not in it:
            raise OverrideError("%s %r: use ROLE=VALUE" % (what, it))
        k, v = it.split("=", 1)
        out.append((k.strip(), v.strip()))
    return out


def resolve_prefer(pal: ModePalette, pairs: List[Tuple[str, str]], all_tokens: List[Token]) -> Dict[str, Token]:
    """--prefer-token ROLE=TOKEN -> {role: Token}. The token may also be one that was left out."""
    by_name = {t.name: t for t in all_tokens}
    out = {}
    for role, name in pairs:
        r = role.lower()
        if r in ("background",):
            r = "bg"
        if r in ("foreground", "text"):
            r = "fg"
        if r not in PREFER_ROLES:
            raise OverrideError("--prefer-token role %r: use one of %s" % (role, ", ".join(PREFER_ROLES)))
        t = by_name.get(name)
        if t is None:
            tails = [x for n, x in by_name.items() if re.split(r"[./]", n)[-1] == name or n.endswith("-" + name)]
            if len(tails) == 1:
                t = tails[0]
        if t is None:
            import difflib
            close = difflib.get_close_matches(name, list(by_name), n=5, cutoff=0.4)
            raise OverrideError("--prefer-token %s=%s: no color token with that name%s" % (
                role, name, (" (close: %s)" % ", ".join(close)) if close else ""))
        out[r] = t
        if t not in pal.tokens:
            pal.tokens.append(t)
    return out


def bg_feasible(bg: str, mode: str, alpha: float = 1.0) -> bool:
    """True when the best possible text on bg leaves room for every band (Lc 85 and WCAG 8).
    A translucent bg must leave room over every desktop too."""
    ink = "#ffffff" if mode == "dark" else "#000000"
    bgs = [bg] + [c for _d, c in cl.translucent_backgrounds(bg, alpha)]
    for b in bgs:
        if cl.lc_abs(ink, b) < 85.0 or cl.contrast_ratio(ink, b) < 8.0:
            return False
    if mode == "dark":
        # faint hue colors must leave room below the text: near black, every hue needs Lc 95+
        return M.faint_floor(bg, mode, alpha) <= DARK_FAINT_FLOOR_MAX
    return alpha >= 1.0 or _light_band_ok(bgs)


DARK_FAINT_FLOOR_MAX = 86.0   # set with the faint model before the measurement; the measured floors are far below it


def _light_band_ok(bgs: List[str]) -> bool:
    """Light mode, translucent: green, yellow and cyan must be dark enough for faint text on every
    composite and light enough for black text on them (text_on_color). A darker composite can
    close this band."""
    aim = cl.GATES["faint_text"]["gate"]["ansi_min_lc"] + 0.5
    tmin = cl.GATES["text_on_color"]["gate"]["min_lc"] + 0.5
    for h in (130.0, 90.0, 200.0):
        ok = False
        for i in range(199, 59, -1):   # light to dark
            x = M.oklch_hex(i * 0.005, 0.10, h)
            if cl.lc_abs("#000000", x) < tmin:
                break   # darker colors only lose more
            if all(cl.lc_abs(cl.faint(x, b), b) >= aim and cl.lc_abs(x, b) >= 45.0 for b in bgs):
                ok = True
                break
        if not ok:
            return False
    return True


def min_alpha(bg: str, mode: str) -> Optional[float]:
    """Lowest background alpha (step 0.01) at which bg_feasible is still true; None if never."""
    if not bg_feasible(bg, mode):
        return None
    a = 1.0
    while a > 0.0 and bg_feasible(bg, mode, round(a - 0.01, 2)):
        a = round(a - 0.01, 2)
    return a


HUE_SLOTS = {1: "red", 2: "green", 3: "yellow", 4: "blue", 5: "magenta", 6: "cyan"}


def build(pal: ModePalette, mode: str, derived: bool = False, prefer: Optional[Dict[str, Token]] = None,
          sets: Optional[List[Tuple[str, str]]] = None, chroma_floor: bool = True, alpha: float = 1.0,
          advise: bool = True, max_evals: int = G.MAX_EVALS) -> dict:
    """alpha < 1 (--translucent) makes every gate also run on the background composited over a
    black and a white desktop."""
    sets = sets or []
    brand = (prefer or {}).get("brand") or pal.brand
    force = {}
    for role, val in sets:
        k = slot_key(role)
        if k in ("background", "foreground"):
            hx = parse_hex(val)
            force[k] = M.Slot(hx, "override", "--set %s=%s" % (role, hx), "override")
    notes = list(pal.notes)
    for role, val in sets:
        k = slot_key(role)
        if k in HUE_SLOTS or (isinstance(k, int) and k - 8 in HUE_SLOTS):
            nm = HUE_SLOTS[k if k < 8 else k - 8]
            L, C, h = cl.srgb_to_oklch(cl.parse_hex(parse_hex(val)))
            anchor = M.ANCHORS[mode][nm][0]
            if C < 0.035 or M.hue_dist(h, anchor) > 45:
                notes.append("warning: --set %s=%s does not look %s (hue %.0f, chroma %.3f)" % (role, val, nm, h if h == h else 0, C))

    budget = {"left": max_evals}

    def attempt(force_now):
        m = M.map_mode(pal, mode, derived, prefer=prefer, chroma_floor=chroma_floor, force=force_now)
        slots = m["slots"]
        slots["background"].alpha = alpha
        if alpha < 1.0:
            # solve the selection again: it must also stand out from the desktop composites
            slots["selection"] = M.make_selection(slots, brand, mode)
        if not bg_feasible(slots["background"].hex, mode, alpha):
            # no search can pass on this background: do not spend the repair budget
            chk = G.check(slots, mode)
            return m, slots, [], chk, chk
        lighter = mode == "dark"
        T = M.TARGETS[mode]
        for role, val in sets:
            k = slot_key(role)
            if k in ("background", "foreground"):
                continue
            hx = parse_hex(val)
            slots[k] = M.Slot(hx, "override", "--set %s=%s" % (role, hx), "override")
        set_keys = {slot_key(r) for r, _ in sets}
        if "cursor" not in set_keys and "foreground" in force_now:
            slots["cursor"] = M.make_cursor(slots["background"].hex, brand, slots["foreground"], lighter, T)
        if "selection" not in set_keys and sets:
            slots["selection"] = M.make_selection(slots, brand, mode)
        before = G.check(slots, mode)
        slots, log, res = G.repair(slots, mode, brand, budget=budget)
        return m, slots, log, res, before

    m, slots, log, res, before = attempt(force)
    first_bg = slots["background"].hex
    if not res["pass"]:
        # the background cannot carry a readable theme: rebuild every slot on a standard background
        old = slots["background"].hex
        L, C, h = cl.srgb_to_oklch(cl.parse_hex(old))
        # a translucent light theme needs the lightest background: the black desktop darkens it
        nb = M.oklch_hex((0.985 if alpha >= 1.0 else 1.0) if mode == "light" else 0.22, min(C, 0.02), h if h == h else 260.0)
        f2 = dict((k, v) for k, v in force.items() if k != "background")   # keep --set fg (C12 review B1)
        f2.update({"_retry": True, "background": M.Slot(nb, "synthesized", "standard %s background; %s failed the gates" % (mode, old), "synth")})
        if "background" in force:
            log.append("override background %s was replaced by %s to pass the gates" % (force["background"].hex, nb))
        m, slots, log2, res, _b = attempt(f2)
        why = "it cannot carry readable text" if not bg_feasible(old, mode, alpha) else "the theme failed the gates on it"
        if alpha < 1.0 and bg_feasible(old, mode):
            why += " at alpha %.2f" % alpha
        log = log + ["background %s -> %s: %s; every slot was mapped again" % (old, nb, why)] + log2
    if alpha < 1.0 and not res["pass"] and advise:
        notes.append(_alpha_advice(pal, mode, derived, prefer, sets, chroma_floor, alpha, first_bg))
    for k, s in slots.items():
        if s.origin == "override" and s.hex != s.original:
            log.append("override %s %s was changed to %s to pass the gates" % (k, s.original, s.hex))
    return {"mode": mode, "derived": derived, "slots": slots, "check": res, "before": before, "alpha": alpha,
            "repairs": log, "brand": m["brand"], "brand_hex": m["brand_hex"], "assignment": m["assignment"],
            "notes": notes + m["notes"], "unused_tokens": m["unused_tokens"], "neutral_tint": m["neutral_tint"],
            "brand_chroma": m["brand_chroma"], "token_hex": m.get("token_hex", {})}


ADVICE_TRIES = 4
ADVICE_EVALS = 2000


def _alpha_advice(pal, mode, derived, prefer, sets, chroma_floor, alpha, first_bg) -> str:
    """A note for a translucent theme that fails: the lowest alpha that a real build passes with
    (checked, from the feasibility limit up, at most ADVICE_TRIES builds), and the limit for the
    design system's own background."""
    msg = "translucency: alpha %.2f fails" % alpha
    std = M.oklch_hex(1.0, 0.0, 0.0) if mode == "light" else None
    start = None
    for b in ([first_bg] + ([std] if std else [])):
        lo = min_alpha(b, mode)
        if lo is not None and lo >= alpha and (start is None or lo < start):
            start = lo
    found = None
    a = max(start or alpha + 0.01, alpha + 0.01)
    kw = dict(prefer=prefer, sets=sets, chroma_floor=chroma_floor, advise=False, max_evals=ADVICE_EVALS)
    for _ in range(ADVICE_TRIES):
        if a >= 1.0:
            break
        th = build(pal, mode, derived, alpha=round(a, 2), **kw)
        if th["check"]["pass"]:
            found = (round(a, 2), th["slots"]["background"].hex)
            break
        a += 0.01
    if found:
        msg += "; --translucent %.2f passes (checked, background %s)" % found
    elif build(pal, mode, derived, alpha=1.0, **kw)["check"]["pass"]:
        msg += "; no alpha up to %.2f passed; the opaque theme passes (checked): leave out --translucent" % min(a, 1.0)
    else:
        msg += "; no alpha up to %.2f passed, and the opaque theme fails too" % min(a, 1.0)
    own = min_alpha(first_bg, mode)
    if own is not None and own > alpha and (not found or found[1] != first_bg):
        msg += "; to keep the background %s, alpha must be at least %.2f (a lower limit, not checked)" % (first_bg, own)
    return msg


def terminal_colors(slots: dict) -> Dict[str, str]:
    return {TERMINAL_KEY[k]: s.hex for k, s in slots.items() if k in TERMINAL_KEY}
