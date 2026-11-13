"""roles.py - token roles and color modes for one design system (stdlib only, Python >= 3.9).

Input: the IR from normalize.build_ir. Output: one ModePalette for each color mode
(light, dark) that the design system defines.

Rules:
- The mode kind comes from the lightness of the background token, never from the mode name.
  The claude.ai Design System calls screen-size breakpoints "themes"; they are
  not color modes.
- Two or more IR modes of the same kind become one palette. The preferred mode wins; the
  others are reported.
- Semantic alias tokens (color-brand -> hb-pink) are preferred over raw tokens.
- When a design system has semantic aliases, raw tokens that no alias uses and that do not
  share the name prefix of the used tokens are "unrelated" (for example a client's colors,
  northwind-*). They are left out by default and listed in the report.
"""
import math
import re
from typing import Dict, List, Optional, Tuple

from . import colorlab as cl

# ---------------------------------------------------------------- name words

TEXT_W = {"text", "fg", "foreground", "ink", "body", "copy", "on", "onsurface", "onbackground", "type", "content"}
BG_W = {"bg", "background", "canvas", "paper", "page", "base", "backdrop", "app", "ground"}
SURFACE_W = {"surface", "card", "panel", "container", "overlay", "inset", "elevated", "sheet", "well", "raised"}
MUTED_W = {"muted", "subdued", "dim", "secondary"}
FAINT_W = {"faint", "subtle", "placeholder", "disabled", "hint", "quiet", "tertiary"}
BORDER_W = {"rule", "border", "divider", "outline", "stroke", "separator", "hairline", "line", "ring"}
ACCENT_W = {"accent", "primary", "brand", "key", "cta", "action", "interactive", "tint"}
NEUTRAL_W = {"grey", "gray", "neutral", "stone", "black", "white", "slate", "zinc", "charcoal"}
STATE_W = {"hover", "pressed", "active", "focus", "visited", "selected", "disabled"}
SOFT_W = {"soft", "tint", "wash", "light", "pale", "lighter", "lightest", "subtle", "weak"}
STRONG = {  # semantic words -> ANSI hue slot (strong signal)
    "red": ["danger", "error", "critical", "negative", "destructive", "fail", "failure", "invalid", "alert"],
    "green": ["success", "positive", "ok", "valid", "pass", "confirm", "added", "online"],
    "yellow": ["warning", "warn", "caution", "attention", "pending", "modified"],
    "blue": ["info", "information", "link", "notice"],
    "magenta": ["done", "merged", "sponsor", "sponsors", "special", "discovery", "upsell"],
    "cyan": [],
}
WEAK = {  # hue words (weak signal)
    "red": ["red", "crimson", "scarlet", "tomato", "ruby", "coral", "terracotta", "rust", "brick"],
    "green": ["green", "emerald", "lime", "olive", "sage", "forest", "mint", "jade"],
    "yellow": ["yellow", "amber", "gold", "sand", "ochre", "mustard", "honey", "lemon", "saffron", "orange"],
    "blue": ["blue", "navy", "cobalt", "azure", "sky", "indigo", "denim", "sapphire"],
    "magenta": ["purple", "violet", "magenta", "pink", "fuchsia", "plum", "lavender", "grape", "berry", "rose"],
    "cyan": ["cyan", "teal", "aqua", "turquoise", "lagoon", "petrol"],
}
MIN_CHROMA_CHROMATIC = 0.035   # below this a token cannot carry an ANSI hue
ALIAS_MIN = 4                  # a design system with this many semantic aliases has a semantic layer

NEUTRAL_ROLES = ("bg", "surface", "fg", "muted", "faint", "border", "neutral")
EXCLUDED_FROM_HUES = ("bg", "surface", "border", "on-color", "fg", "container", "muted", "faint", "neutral")


def split_words(name: str) -> List[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return [w for w in re.split(r"[^a-zA-Z0-9]+", s.lower()) if w]


def classify(words: List[str]) -> Tuple[str, Optional[str], Optional[str], bool]:
    """Return (role, strong_slot, weak_slot, accent) from the words of a token name."""
    ws = set(words)
    if words and "base" in ws and words[-1] != "base":
        ws.discard("base")  # 'color.base.white' is a palette group, not a background
    has_text = bool(ws & TEXT_W)
    has_bg, has_surface = bool(ws & BG_W), bool(ws & SURFACE_W)
    strong = next((s for s, lst in STRONG.items() if ws & set(lst)), None)
    weak = next((s for s, lst in WEAK.items() if ws & set(lst)), None)
    accent = bool(ws & ACCENT_W) or (("secondary" in ws or "tertiary" in ws)
                                     and not has_text and not has_bg and not has_surface)
    colored = bool(strong or accent or weak)
    if ws & BORDER_W:
        role = "border"
    elif "on" in ws and len(ws) > 1:
        if ws & {"surface", "background"}:
            role = "muted" if "variant" in ws else "fg"
        else:
            role = "on-color"
    elif colored and (has_surface or "container" in ws or (has_bg and strong)):
        role = "container"
    elif colored and not (has_bg or has_surface) and not has_text:
        role = "chromatic"
    elif has_text or ((ws & (MUTED_W | FAINT_W)) and not (has_bg or has_surface)):
        if strong or (weak and not ws & NEUTRAL_W):
            role = "chromatic"
        else:
            role = "faint" if ws & FAINT_W else ("muted" if ws & MUTED_W else "fg")
    elif has_surface or (has_bg and ws & (FAINT_W | MUTED_W | {"inset", "overlay", "alt", "warm"})):
        role = "surface"
    elif has_bg:
        role = "bg"
    elif ws & NEUTRAL_W:
        role = "neutral"
    elif strong or weak or accent:
        role = "chromatic"
    else:
        role = "unknown"
    return role, strong, weak, accent


class Token(object):
    """One resolved, opaque color token."""

    def __init__(self, name: str, hexcol: str, alias_of: Optional[str] = None, description: str = "",
                 order: int = 0):
        self.name = name
        self.hex = cl.to_hex(cl.parse_hex(hexcol[:7]))
        self.alias_of = alias_of
        self.description = description or ""
        self.order = order
        self.L, self.C, self.h = cl.srgb_to_oklch(cl.parse_hex(self.hex))
        if self.C < 1e-6 or self.h != self.h:
            self.h = 0.0
        self.words = split_words(name)
        self.role, self.strong, self.weak, self.accent = classify(self.words)
        self.state = bool(set(self.words) & STATE_W)
        self.soft = bool(set(self.words) & SOFT_W)
        self.used_by_alias = False
        self.prefix = self.words[0] if self.words else ""

    @property
    def semantic(self) -> bool:
        return self.alias_of is not None

    def __repr__(self):
        return "Token(%s %s %s)" % (self.name, self.hex, self.role)


class ModePalette(object):
    """The tokens of one color mode, with the roles picked for it."""

    def __init__(self, kind: str, source_mode: str, tokens: List[Token], ignored: List[Token],
                 notes: List[str], kind_basis: str):
        self.kind = kind
        self.source_mode = source_mode
        self.tokens = tokens
        self.ignored = ignored
        self.notes = notes
        self.kind_basis = kind_basis
        self.bg = pick_bg(tokens, kind)
        self.fg = pick_fg(tokens, kind, self.bg)
        self.brand = pick_brand(tokens)

    def summary(self) -> dict:
        def t(x):
            return {"name": x.name, "hex": x.hex} if x is not None else None
        return {"kind": self.kind, "source_mode": self.source_mode, "kind_basis": self.kind_basis,
                "tokens": len(self.tokens), "ignored": [x.name for x in self.ignored],
                "bg": t(self.bg), "fg": t(self.fg), "brand": t(self.brand), "notes": list(self.notes)}


# ---------------------------------------------------------------- role picks

def _pref(t: Token) -> Tuple[int, int]:
    """Sort key: semantic aliases first, then tokens that aliases use, then the rest."""
    return (0 if t.semantic else (1 if t.used_by_alias else 2), t.order)


def pick_bg(tokens: List[Token], kind: Optional[str] = None) -> Optional[Token]:
    """The default background: a bg-named token, else a page/surface token. No state tokens."""
    def ok(t):
        if t.state or t.role not in ("bg", "surface"):
            return False
        if kind == "light":
            return t.L >= 0.60
        if kind == "dark":
            return t.L <= 0.45
        return True
    bgs = [t for t in tokens if ok(t)]
    pageish = {"page", "app", "canvas", "base", "default", "bg", "background"}
    # semantic aliases first; then page-like names; a page surface beats a card
    bgs.sort(key=lambda t: (_pref(t)[0], 0 if set(t.words) & pageish else 1,
                            0 if t.role == "bg" else 1, len(t.words), t.order))
    return bgs[0] if bgs else None


def pick_fg(tokens: List[Token], kind: Optional[str], bg: Optional[Token]) -> Optional[Token]:
    """The default text color: a body/text token on the far side of the background."""
    bgL = bg.L if bg is not None else (0.97 if kind == "light" else 0.2)
    far = [t for t in tokens if t.role == "fg" and not t.state and abs(t.L - bgL) >= 0.35]
    if not far:
        return None

    def key(t):
        ws = set(t.words)
        body = 0 if ws & {"body", "default", "primary", "copy", "base"} else (1 if ws & {"text", "fg", "foreground", "ink"} else 2)
        return (body, 1 if ws & {"heading", "title", "display", "strong", "emphasis"} else 0) + _pref(t)
    far.sort(key=key)
    return far[0]


def pick_brand(tokens: List[Token]) -> Optional[Token]:
    chrom = [t for t in tokens if t.C >= MIN_CHROMA_CHROMATIC and t.role not in EXCLUDED_FROM_HUES
             and not t.state and not t.soft]
    for test in (lambda t: t.accent and "brand" in t.words,
                 lambda t: t.accent and not set(t.words) & {"secondary", "tertiary"},
                 lambda t: t.accent,
                 lambda t: t.role in ("chromatic", "unknown") and not t.strong,
                 lambda t: True):
        c = sorted([t for t in chrom if test(t)], key=lambda t: (len(t.words),) + _pref(t))
        if c:
            return c[0]
    return None


# ---------------------------------------------------------------- pool building

DROPPED_ALPHA = []


def tokens_from_ir_mode(toks: List[dict]) -> List[Token]:
    out = []
    seen = set()
    for i, d in enumerate(toks):
        if float(d.get("alpha", 1.0)) < 0.9:
            DROPPED_ALPHA.append(str(d.get("name")))
            continue
        hx = d.get("value_srgb")
        if not isinstance(hx, str) or not hx.startswith("#"):
            continue
        name = str(d.get("name"))
        if name in seen:
            continue
        seen.add(name)
        alias = d.get("aliasOf")
        if isinstance(alias, list):
            alias = alias[-1] if alias else None
        out.append(Token(name, hx, alias_of=alias, description=d.get("description", ""), order=i))
    by_name = {t.name: t for t in out}
    for t in out:
        if t.alias_of:
            tgt = by_name.get(str(t.alias_of))
            if tgt is None:
                # aliasOf may be a path like "color.hb-pink" or "hb-pink"
                tail = str(t.alias_of).replace("{", "").replace("}", "").split(".")[-1]
                tgt = by_name.get(tail)
            if tgt is not None:
                tgt.used_by_alias = True
    return out


def split_unrelated(tokens: List[Token], keep_all: bool = False) -> Tuple[List[Token], List[Token], List[str]]:
    """Return (kept, ignored, notes). See the module docstring."""
    notes = []
    aliases = [t for t in tokens if t.semantic]
    if keep_all or len(aliases) < ALIAS_MIN:
        return tokens, [], notes
    used = [t for t in tokens if t.used_by_alias]
    prefixes = {}
    for t in used:
        prefixes[t.prefix] = prefixes.get(t.prefix, 0) + 1
    # a prefix counts as "the system's own" when at least 2 used tokens carry it
    own = {p for p, n in prefixes.items() if n >= 2}
    kept, ignored = [], []
    for t in tokens:
        if t.semantic or t.used_by_alias or (own and t.prefix in own):
            kept.append(t)
        else:
            ignored.append(t)
    if ignored:
        notes.append("left out %d raw tokens that no semantic token uses and that do not share the "
                     "prefix %s (use --all-tokens to keep them)" % (len(ignored), "/".join(sorted(own)) or "-"))
    return kept, ignored, notes


def detect_kind(tokens: List[Token]) -> Tuple[Optional[str], str]:
    """Light or dark, from the background lightness (OKLab L < 0.5 is dark)."""
    bg = pick_bg(tokens)
    if bg is not None:
        return ("dark" if bg.L < 0.5 else "light"), "background %s %s (L %.2f)" % (bg.name, bg.hex, bg.L)
    fgs = [t for t in tokens if t.role == "fg" and not t.state]
    if fgs:
        fgs.sort(key=_pref)
        f = fgs[0]
        return ("light" if f.L < 0.5 else "dark"), "text %s %s (L %.2f)" % (f.name, f.hex, f.L)
    neutrals = sorted(t.L for t in tokens if t.C < 0.05)
    if neutrals:
        # more light neutrals than dark ones: a light UI
        light = sum(1 for x in neutrals if x >= 0.5)
        return ("light" if light >= len(neutrals) - light else "dark"), "neutral token lightness"
    return None, "no background, text or neutral token"


def _signature(tokens: List[Token]) -> frozenset:
    return frozenset((t.name, t.hex) for t in tokens)


VARIANT_WORDS = ("high", "contrast", "colorblind", "tritanopia", "protanopia", "deuteranopia", "dimmed",
                 "dim", "mobile", "tablet", "desktop", "print", "compact", "dense", "legacy", "inverse")


def extract(ir: dict, keep_all: bool = False, source_mode: Optional[str] = None) -> Tuple[Dict[str, ModePalette], List[str]]:
    """Return ({'light': ModePalette, 'dark': ModePalette} subset, notes)."""
    notes = []
    del DROPPED_ALPHA[:]
    groups = {}  # kind -> [(mode_id, tokens, ignored, notes, basis)]
    modes = ir.get("modes") or {}
    for mid, mv in modes.items():
        if source_mode and mid != source_mode:
            continue
        toks = tokens_from_ir_mode(mv.get("tokens") or [])
        if not toks:
            continue
        kept, ignored, n = split_unrelated(toks, keep_all)
        kind, basis = detect_kind(kept)
        if kind is None:
            kind, basis = "light", basis + "; assumed light"
        name_kind = mv.get("kind")
        if name_kind and name_kind != kind:
            n.append("mode '%s': the name or normalizer says %s, but the background is %s; uses %s"
                     % (mid, name_kind, kind, kind))
        groups.setdefault(kind, []).append((mid, kept, ignored, n, basis))
    if source_mode and source_mode not in modes:
        notes.append("--source-mode %s: no such mode; the modes are %s" % (source_mode, ", ".join(sorted(modes)) or "none"))
    out = {}
    for kind, items in groups.items():
        def pen(it):
            segs = re.split(r"[-_ ]", it[0].lower())
            return (sum(1 for s in segs if s in VARIANT_WORDS), 0 if it[0] in ("default", kind) else 1,
                    -len(it[1]), it[0])
        items.sort(key=pen)
        mid, kept, ignored, n, basis = items[0]
        for it in items[1:]:
            n.extend(x for x in it[3] if "the name or normalizer says" in x)
        if len(items) > 1:
            same = [it[0] for it in items[1:] if _signature(it[1]) == _signature(kept)]
            diff = [it[0] for it in items[1:] if it[0] not in same]
            if same:
                n.append("%s modes %s have the same colors as '%s' (breakpoints or variants); not used"
                         % (kind, same, mid))
            if diff:
                n.append("%s modes %s are variants; '%s' is used" % (kind, diff, mid))
        out[kind] = ModePalette(kind, mid, kept, ignored, n, basis)
    if not out:
        alpha = len(set(DROPPED_ALPHA))
        notes.append("no opaque color tokens found" + (" (%d tokens have alpha < 0.9 and are not used)" % alpha if alpha else ""))
    return out, notes


def tokens_from_hex_list(pairs: List[Tuple[str, str]]) -> List[Token]:
    """Tokens from (name, hex) pairs (tests, --palette input)."""
    return [Token(n, h, order=i) for i, (n, h) in enumerate(pairs)]


def hue_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def circ_mean(hs: List[float], ws: Optional[List[float]] = None) -> float:
    ws = ws or [1.0] * len(hs)
    x = sum(w * math.cos(math.radians(h)) for h, w in zip(hs, ws))
    y = sum(w * math.sin(math.radians(h)) for h, w in zip(hs, ws))
    return math.degrees(math.atan2(y, x)) % 360.0
