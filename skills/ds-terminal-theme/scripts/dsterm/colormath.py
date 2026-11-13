#!/usr/bin/env python3
"""colormath.py - CSS Color 4/5 parsing and conversion to sRGB (stdlib only, Python >= 3.9).

parse_color(text) -> dict | None
  {"rgb": (r, g, b) floats 0..1 in sRGB after CSS gamut mapping,
   "alpha": float, "space": source space name, "mapped": bool (True if gamut-mapped),
   "hex": "#rrggbb"}
Matrices and the gamut-mapping algorithm follow CSS Color 4 (sample code, sec. 13.2).
"""
import math
import re

# ---------------------------------------------------------------- named colors (CSS Color 4, 148 names)
_NAMED_SRC = (
    "aliceblue:f0f8ff antiquewhite:faebd7 aqua:00ffff aquamarine:7fffd4 azure:f0ffff beige:f5f5dc "
    "bisque:ffe4c4 black:000000 blanchedalmond:ffebcd blue:0000ff blueviolet:8a2be2 brown:a52a2a "
    "burlywood:deb887 cadetblue:5f9ea0 chartreuse:7fff00 chocolate:d2691e coral:ff7f50 "
    "cornflowerblue:6495ed cornsilk:fff8dc crimson:dc143c cyan:00ffff darkblue:00008b darkcyan:008b8b "
    "darkgoldenrod:b8860b darkgray:a9a9a9 darkgreen:006400 darkgrey:a9a9a9 darkkhaki:bdb76b "
    "darkmagenta:8b008b darkolivegreen:556b2f darkorange:ff8c00 darkorchid:9932cc darkred:8b0000 "
    "darksalmon:e9967a darkseagreen:8fbc8f darkslateblue:483d8b darkslategray:2f4f4f "
    "darkslategrey:2f4f4f darkturquoise:00ced1 darkviolet:9400d3 deeppink:ff1493 deepskyblue:00bfff "
    "dimgray:696969 dimgrey:696969 dodgerblue:1e90ff firebrick:b22222 floralwhite:fffaf0 "
    "forestgreen:228b22 fuchsia:ff00ff gainsboro:dcdcdc ghostwhite:f8f8ff gold:ffd700 goldenrod:daa520 "
    "gray:808080 green:008000 greenyellow:adff2f grey:808080 honeydew:f0fff0 hotpink:ff69b4 "
    "indianred:cd5c5c indigo:4b0082 ivory:fffff0 khaki:f0e68c lavender:e6e6fa lavenderblush:fff0f5 "
    "lawngreen:7cfc00 lemonchiffon:fffacd lightblue:add8e6 lightcoral:f08080 lightcyan:e0ffff "
    "lightgoldenrodyellow:fafad2 lightgray:d3d3d3 lightgreen:90ee90 lightgrey:d3d3d3 lightpink:ffb6c1 "
    "lightsalmon:ffa07a lightseagreen:20b2aa lightskyblue:87cefa lightslategray:778899 "
    "lightslategrey:778899 lightsteelblue:b0c4de lightyellow:ffffe0 lime:00ff00 limegreen:32cd32 "
    "linen:faf0e6 magenta:ff00ff maroon:800000 mediumaquamarine:66cdaa mediumblue:0000cd "
    "mediumorchid:ba55d3 mediumpurple:9370db mediumseagreen:3cb371 mediumslateblue:7b68ee "
    "mediumspringgreen:00fa9a mediumturquoise:48d1cc mediumvioletred:c71585 midnightblue:191970 "
    "mintcream:f5fffa mistyrose:ffe4e1 moccasin:ffe4b5 navajowhite:ffdead navy:000080 oldlace:fdf5e6 "
    "olive:808000 olivedrab:6b8e23 orange:ffa500 orangered:ff4500 orchid:da70d6 palegoldenrod:eee8aa "
    "palegreen:98fb98 paleturquoise:afeeee palevioletred:db7093 papayawhip:ffefd5 peachpuff:ffdab9 "
    "peru:cd853f pink:ffc0cb plum:dda0dd powderblue:b0e0e6 purple:800080 rebeccapurple:663399 "
    "red:ff0000 rosybrown:bc8f8f royalblue:4169e1 saddlebrown:8b4513 salmon:fa8072 sandybrown:f4a460 "
    "seagreen:2e8b57 seashell:fff5ee sienna:a0522d silver:c0c0c0 skyblue:87ceeb slateblue:6a5acd "
    "slategray:708090 slategrey:708090 snow:fffafa springgreen:00ff7f steelblue:4682b4 tan:d2b48c "
    "teal:008080 thistle:d8bfd8 tomato:ff6347 turquoise:40e0d0 violet:ee82ee wheat:f5deb3 white:ffffff "
    "whitesmoke:f5f5f5 yellow:ffff00 yellowgreen:9acd32"
)
NAMED = dict(p.split(":") for p in _NAMED_SRC.split())


# ---------------------------------------------------------------- matrices (CSS Color 4 conversions.js)
def _mul(m, v):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


M_SRGB_TO_XYZ = ((0.41239079926595934, 0.357584339383878, 0.1804807884018343),
                 (0.21263900587151027, 0.715168678767756, 0.07219231536073371),
                 (0.01933081871559182, 0.11919477979462598, 0.9505321522496607))
M_XYZ_TO_SRGB = ((3.2409699419045226, -1.537383177570094, -0.4986107602930034),
                 (-0.9692436362808796, 1.8759675015077202, 0.04155505740717559),
                 (0.05563007969699366, -0.20397695888897652, 1.0569715142428786))
M_P3_TO_XYZ = ((0.4865709486482162, 0.26566769316909306, 0.1982172852343625),
               (0.2289745640697488, 0.6917385218365064, 0.079286914093745),
               (0.0, 0.04511338185890264, 1.043944368900976))
M_A98_TO_XYZ = ((0.5766690429101305, 0.1855582379065463, 0.1882286462349947),
                (0.29734497525053605, 0.6273635662554661, 0.07529145849399788),
                (0.02703136138641234, 0.07068885253582723, 0.9913375368376388))
M_PROPHOTO_TO_XYZ50 = ((0.7977666449006423, 0.13518129740053308, 0.0313477341283922),
                       (0.2880748288194013, 0.711835234241873, 0.00008993693872564),
                       (0.0, 0.0, 0.8251046025104602))
M_2020_TO_XYZ = ((0.6369580483012914, 0.14461690358620832, 0.1688809751641721),
                 (0.2627002120112671, 0.6779980715188708, 0.05930171646986196),
                 (0.0, 0.028072693049087428, 1.060985057710791))
M_D50_TO_D65 = ((0.955473421488075, -0.02309845494876471, 0.06325924320057072),
                (-0.0283697093338637, 1.0099953980813041, 0.021041441191917323),
                (0.012314014864481998, -0.020507649298898964, 1.330365926242124))
M_D65_TO_D50 = ((1.0479297925449969, 0.022946870601609652, -0.05019226628920524),
                (0.02962780877005599, 0.9904344267538799, -0.017073799063418826),
                (-0.009243040646204504, 0.015055191490298152, 0.7518742814281371))
M_XYZ_TO_LMS = ((0.8190224379967030, 0.3619062600528904, -0.1288737815209879),
                (0.0329836539323885, 0.9292868615863434, 0.0361446663506424),
                (0.0481771893596242, 0.2642395317527308, 0.6335478284694309))
M_LMSG_TO_OKLAB = ((0.2104542683093140, 0.7936177747023054, -0.0040720430116193),
                   (1.9779985324311684, -2.4285922420485799, 0.4505937096174110),
                   (0.0259040424655478, 0.7827717124575296, -0.8086757549230774))
M_OKLAB_TO_LMSG = ((1.0, 0.3963377773761749, 0.2158037573099136),
                   (1.0, -0.1055613458156586, -0.0638541728258133),
                   (1.0, -0.0894841775298119, -1.2914855480194092))
M_LMS_TO_XYZ = ((1.2268798758459243, -0.5578149944602171, 0.2813910456659647),
                (-0.0405757452148008, 1.1122868032803170, -0.0717110580655164),
                (-0.0763729366746601, -0.4214933324022432, 1.5869240198367816))
D50_WHITE = (0.3457 / 0.3585, 1.0, (1.0 - 0.3457 - 0.3585) / 0.3585)


def _srgb_lin(c):
    a = abs(c)
    return c / 12.92 if a <= 0.04045 else math.copysign(((a + 0.055) / 1.055) ** 2.4, c)


def _srgb_gam(c):
    a = abs(c)
    return 12.92 * c if a <= 0.0031308 else math.copysign(1.055 * a ** (1 / 2.4) - 0.055, c)


def _a98_lin(c):
    return math.copysign(abs(c) ** (563 / 256), c)


def _pp_lin(c):
    a = abs(c)
    return c / 16 if a <= 16 / 512 else math.copysign(a ** 1.8, c)


def _2020_lin(c):
    al, be = 1.09929682680944, 0.018053968510807
    a = abs(c)
    return c / 4.5 if a < be * 4.5 else math.copysign(((a + al - 1) / al) ** (1 / 0.45), c)


def lab_to_xyz50(L, a, b):
    k, e = 24389 / 27, 216 / 24389
    f1 = (L + 16) / 116
    f0 = a / 500 + f1
    f2 = f1 - b / 200
    x = f0 ** 3 if f0 ** 3 > e else (116 * f0 - 16) / k
    y = ((L + 16) / 116) ** 3 if L > k * e else L / k
    z = f2 ** 3 if f2 ** 3 > e else (116 * f2 - 16) / k
    return (x * D50_WHITE[0], y * D50_WHITE[1], z * D50_WHITE[2])


def oklab_to_xyz(L, a, b):
    lms = _mul(M_OKLAB_TO_LMSG, (L, a, b))
    return _mul(M_LMS_TO_XYZ, tuple(v ** 3 for v in lms))


def xyz_to_oklab(xyz):
    lms = _mul(M_XYZ_TO_LMS, xyz)
    return _mul(M_LMSG_TO_OKLAB, tuple(math.copysign(abs(v) ** (1 / 3), v) for v in lms))


def hsl_to_srgb(h, s, l):
    # s, l in 0..1
    h = h % 360
    def f(n):
        k = (n + h / 30) % 12
        a = s * min(l, 1 - l)
        return l - a * max(-1, min(k - 3, 9 - k, 1))
    return (f(0), f(8), f(4))


def hwb_to_srgb(h, w, b):
    if w + b >= 1:
        g = w / (w + b)
        return (g, g, g)
    rgb = hsl_to_srgb(h, 1, 0.5)
    return tuple(c * (1 - w - b) + w for c in rgb)


def to_xyz65(space, c):
    """Convert coords in `space` to XYZ-D65."""
    if space == "srgb":
        return _mul(M_SRGB_TO_XYZ, tuple(_srgb_lin(v) for v in c))
    if space == "srgb-linear":
        return _mul(M_SRGB_TO_XYZ, c)
    if space == "display-p3":
        return _mul(M_P3_TO_XYZ, tuple(_srgb_lin(v) for v in c))
    if space == "display-p3-linear":
        return _mul(M_P3_TO_XYZ, c)
    if space == "a98-rgb":
        return _mul(M_A98_TO_XYZ, tuple(_a98_lin(v) for v in c))
    if space == "prophoto-rgb":
        return _mul(M_D50_TO_D65, _mul(M_PROPHOTO_TO_XYZ50, tuple(_pp_lin(v) for v in c)))
    if space == "rec2020":
        return _mul(M_2020_TO_XYZ, tuple(_2020_lin(v) for v in c))
    if space in ("xyz", "xyz-d65"):
        return tuple(c)
    if space == "xyz-d50":
        return _mul(M_D50_TO_D65, c)
    if space == "lab":
        return _mul(M_D50_TO_D65, lab_to_xyz50(*c))
    if space == "lch":
        L, C, H = c
        hr = math.radians(H)
        return _mul(M_D50_TO_D65, lab_to_xyz50(L, C * math.cos(hr), C * math.sin(hr)))
    if space == "oklab":
        return oklab_to_xyz(*c)
    if space == "oklch":
        L, C, H = c
        hr = math.radians(H)
        return oklab_to_xyz(L, C * math.cos(hr), C * math.sin(hr))
    if space == "hsl":
        return to_xyz65("srgb", hsl_to_srgb(*c))
    if space == "hwb":
        return to_xyz65("srgb", hwb_to_srgb(*c))
    raise ValueError("unknown space " + space)


def xyz_to_srgb(xyz):
    return tuple(_srgb_gam(v) for v in _mul(M_XYZ_TO_SRGB, xyz))


def _in_gamut(rgb, eps=1e-6):
    return all(-eps <= v <= 1 + eps for v in rgb)


def _clip(rgb):
    return tuple(min(1.0, max(0.0, v)) for v in rgb)


def _delta_eok(rgb, lab):
    l2 = xyz_to_oklab(to_xyz65("srgb", rgb))
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(l2, lab)))


def gamut_map_srgb(space, coords):
    """CSS Color 4 sec. 13.2.2 'CSS gamut map' to sRGB. Returns ((r,g,b), mapped)."""
    xyz = to_xyz65(space, coords)
    rgb = xyz_to_srgb(xyz)
    if _in_gamut(rgb, 2e-4):  # < 1/19 of an 8-bit step: treat as in gamut
        return _clip(rgb), False
    L, a, b = xyz_to_oklab(xyz)
    if L >= 1:
        return (1.0, 1.0, 1.0), True
    if L <= 0:
        return (0.0, 0.0, 0.0), True
    C = math.hypot(a, b)
    H = math.atan2(b, a)
    JND, EPS = 0.02, 0.0001

    def oklch_rgb(c):
        lab = (L, c * math.cos(H), c * math.sin(H))
        return xyz_to_srgb(oklab_to_xyz(*lab)), lab

    cur_rgb, cur_lab = oklch_rgb(C)
    clipped = _clip(cur_rgb)
    if _delta_eok(clipped, cur_lab) < JND:
        return clipped, True
    lo, hi, lo_in = 0.0, C, True
    while hi - lo > EPS:
        ch = (lo + hi) / 2
        cur_rgb, cur_lab = oklch_rgb(ch)
        if lo_in and _in_gamut(cur_rgb):
            lo = ch
            continue
        clipped = _clip(cur_rgb)
        E = _delta_eok(clipped, cur_lab)
        if E < JND:
            if JND - E < EPS:
                return clipped, True
            lo_in = False
            lo = ch
        else:
            hi = ch
    return clipped, True


def to_hex(rgb):
    return "#" + "".join("%02x" % int(round(min(1.0, max(0.0, v)) * 255)) for v in rgb)


def relative_luminance(rgb):
    lin = [_srgb_lin(v) for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


# ---------------------------------------------------------------- parsing
_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_HUE_UNITS = {"deg": 1.0, "rad": 180 / math.pi, "grad": 0.9, "turn": 360.0, "": 1.0}


class ColorError(ValueError):
    pass


def _hue(tok):
    if tok == "none":
        return 0.0
    m = re.fullmatch("(" + _NUM + ")(deg|rad|grad|turn)?", tok, re.I)
    if not m:
        raise ColorError("bad hue " + tok)
    return float(m.group(1)) * _HUE_UNITS[(m.group(2) or "").lower()]


def _val(tok, pct_ref, num_scale=1.0):
    """Number or percentage. pct_ref = value that 100% maps to; plain numbers multiplied by num_scale."""
    if tok == "none":
        return 0.0
    if tok.endswith("%"):
        return float(tok[:-1]) / 100.0 * pct_ref
    if not re.fullmatch(_NUM, tok):
        raise ColorError("bad number " + tok)
    return float(tok) * num_scale


def _alpha(tok):
    if tok is None:
        return 1.0
    return max(0.0, min(1.0, _val(tok, 1.0)))


def split_top(s, sep=","):
    out, depth, cur, q = [], 0, [], None
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return out


def _args(inner):
    """Split function args into (components list, alpha token or None, legacy_commas bool)."""
    legacy = "," in inner
    if legacy:
        parts = [p.strip() for p in inner.split(",")]
        if any(" " in p.strip() for p in parts):
            raise ColorError("mixed syntax")
        alpha = parts[3] if len(parts) == 4 else None
        comps = parts[:3]
        if len(parts) not in (3, 4):
            raise ColorError("bad arg count")
        return comps, alpha, True
    if "/" in inner:
        a, b = inner.split("/", 1)
        comps, alpha = a.split(), b.strip()
    else:
        comps, alpha = inner.split(), None
    return comps, alpha, False


def _result(space, coords, alpha):
    rgb, mapped = gamut_map_srgb(space, coords)
    return {"rgb": rgb, "alpha": round(alpha, 4), "space": space, "mapped": mapped, "hex": to_hex(rgb)}


_PREDEF = ("srgb", "srgb-linear", "display-p3", "display-p3-linear", "a98-rgb", "prophoto-rgb",
           "rec2020", "xyz", "xyz-d50", "xyz-d65")


def parse_color(text, allow_bare=None):
    """Parse a CSS color string. allow_bare: None | 'rgb' | 'hsl' | 'both' to accept bare
    triplets such as '220 138 120' or '222.2 47.4% 11.2%' (Tailwind-v3 / shadcn style)."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    s = re.sub(r"\s*!(important|default|global)\s*$", "", s, flags=re.I)
    low = s.lower()
    try:
        if low.startswith("#"):
            h = low[1:]
            if not re.fullmatch(r"[0-9a-f]+", h) or len(h) not in (3, 4, 6, 8):
                return None
            if len(h) in (3, 4):
                h = "".join(c * 2 for c in h)
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
            a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
            return _result("srgb", (r, g, b), a)
        if low in NAMED:
            h = NAMED[low]
            return _result("srgb", tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)), 1.0)
        if low == "transparent":
            return {"rgb": (0.0, 0.0, 0.0), "alpha": 0.0, "space": "srgb", "mapped": False, "hex": "#000000"}
        m = re.fullmatch(r"([a-z-]+)\((.*)\)", low, re.S)
        if m:
            fn, inner = m.group(1), m.group(2).strip()
            if inner.startswith("from "):
                raise ColorError("relative color syntax unsupported")
            if "var(" in inner or "calc(" in inner or "{" in inner or "$" in inner:
                raise ColorError("unresolved expression")
            if fn in ("rgb", "rgba"):
                # Sass-style rgba(<color>, a)
                parts = split_top(inner)
                if len(parts) == 2:
                    base = parse_color(parts[0])
                    if base is None:
                        raise ColorError("bad rgba(color,a)")
                    base = dict(base)
                    base["alpha"] = round(base["alpha"] * _alpha(parts[1]), 4)
                    return base
                comps, al, _ = _args(inner)
                if len(comps) != 3:
                    raise ColorError("rgb arity")
                rgb = tuple(_val(c, 1.0, 1 / 255) for c in comps)
                return _result("srgb", rgb, _alpha(al))
            if fn in ("hsl", "hsla"):
                comps, al, _ = _args(inner)
                if len(comps) != 3:
                    raise ColorError("hsl arity")
                return _result("hsl", (_hue(comps[0]), _val(comps[1], 1.0, 0.01), _val(comps[2], 1.0, 0.01)), _alpha(al))
            if fn == "hwb":
                comps, al, _ = _args(inner)
                return _result("hwb", (_hue(comps[0]), _val(comps[1], 1.0, 0.01), _val(comps[2], 1.0, 0.01)), _alpha(al))
            if fn == "lab":
                comps, al, _ = _args(inner)
                return _result("lab", (_val(comps[0], 100.0), _val(comps[1], 125.0), _val(comps[2], 125.0)), _alpha(al))
            if fn == "lch":
                comps, al, _ = _args(inner)
                return _result("lch", (_val(comps[0], 100.0), _val(comps[1], 150.0), _hue(comps[2])), _alpha(al))
            if fn == "oklab":
                comps, al, _ = _args(inner)
                return _result("oklab", (_val(comps[0], 1.0), _val(comps[1], 0.4), _val(comps[2], 0.4)), _alpha(al))
            if fn == "oklch":
                comps, al, _ = _args(inner)
                return _result("oklch", (_val(comps[0], 1.0), _val(comps[1], 0.4), _hue(comps[2])), _alpha(al))
            if fn == "color":
                comps, al, _ = _args(inner)
                sp = comps[0]
                if sp not in _PREDEF:
                    raise ColorError("unsupported color() space " + sp)
                vals = tuple(_val(c, 1.0) for c in comps[1:4])
                return _result(sp, vals, _alpha(al))
            if fn == "color-mix":
                return color_mix(inner)
            if fn == "light-dark":
                parts = split_top(inner)
                return parse_color(parts[0])  # caller handles mode-specific choice
            raise ColorError("unsupported function " + fn)
        if allow_bare:
            return parse_bare(s, allow_bare)
    except (ColorError, ValueError, IndexError, ZeroDivisionError, OverflowError):
        return None
    return None


def parse_bare(s, mode="both"):
    m = re.fullmatch(r"\s*(\S+)[ ,]+(\S+)[ ,]+(\S+)\s*(?:/\s*(\S+))?\s*", s)
    if not m:
        return None
    a, b, c, al = m.groups()
    try:
        if mode in ("hsl", "both") and b.endswith("%") and c.endswith("%") and not a.endswith("%"):
            r = _result("hsl", (_hue(a), _val(b, 1.0), _val(c, 1.0)), _alpha(al))
            r["space"] = "bare-hsl"
            return r
        if mode in ("rgb", "both") and all(re.fullmatch(r"\d{1,3}", x) for x in (a, b, c)):
            vals = [int(x) for x in (a, b, c)]
            if max(vals) <= 255:
                r = _result("srgb", tuple(v / 255 for v in vals), _alpha(al))
                r["space"] = "bare-rgb"
                return r
    except (ColorError, ValueError):
        return None
    return None


def _to_space(space, rgb_xyz):
    """XYZ-D65 -> coordinates in an interpolation space."""
    xyz = rgb_xyz
    if space == "srgb":
        return xyz_to_srgb(xyz)
    if space == "srgb-linear":
        return _mul(M_XYZ_TO_SRGB, xyz)
    if space in ("xyz", "xyz-d65"):
        return xyz
    if space == "xyz-d50":
        return _mul(M_D65_TO_D50, xyz)
    if space == "oklab":
        return xyz_to_oklab(xyz)
    if space == "oklch":
        L, a, b = xyz_to_oklab(xyz)
        return (L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360)
    if space in ("lab", "lch"):
        x, y, z = _mul(M_D65_TO_D50, xyz)
        k, e = 24389 / 27, 216 / 24389
        fx, fy, fz = (v ** (1 / 3) if v > e else (k * v + 16) / 116 for v in (x / D50_WHITE[0], y, z / D50_WHITE[2]))
        L, a, b = 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)
        if space == "lab":
            return (L, a, b)
        return (L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360)
    if space == "display-p3":
        inv = _inv3(M_P3_TO_XYZ)
        return tuple(_srgb_gam(v) for v in _mul(inv, xyz))
    if space in ("hsl", "hwb"):
        r, g, b = xyz_to_srgb(xyz)
        mx, mn = max(r, g, b), min(r, g, b)
        d = mx - mn
        h = 0.0
        if d:
            if mx == r:
                h = ((g - b) / d) % 6
            elif mx == g:
                h = (b - r) / d + 2
            else:
                h = (r - g) / d + 4
            h *= 60
        if space == "hwb":
            return (h, mn, 1 - mx)
        l = (mx + mn) / 2
        s = 0.0 if d == 0 else d / (1 - abs(2 * l - 1))
        return (h, s, l)
    raise ColorError("unsupported interpolation space " + space)


def _inv3(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return ((( e * i - f * h) / det, -(b * i - c * h) / det, (b * f - c * e) / det),
            (-(d * i - f * g) / det, (a * i - c * g) / det, -(a * f - c * d) / det),
            (( d * h - e * g) / det, -(a * h - b * g) / det, (a * e - b * d) / det))


_POLAR_HUE_INDEX = {"oklch": 2, "lch": 2, "hsl": 0, "hwb": 0}


def color_mix(inner):
    parts = split_top(inner)
    if len(parts) != 3:
        raise ColorError("color-mix arity")
    m = re.fullmatch(r"in\s+([a-z0-9-]+)(?:\s+(shorter|longer|increasing|decreasing)\s+hue)?", parts[0].strip())
    if not m:
        raise ColorError("color-mix space")
    space, hue_mode = m.group(1), (m.group(2) or "shorter")
    items = []
    for p in parts[1:]:
        pm = re.fullmatch(r"(.*?)\s+(" + _NUM + r")%\s*|\s*(" + _NUM + r")%\s+(.*)", p, re.S)
        if pm and pm.group(1) is not None:
            col, pct = pm.group(1), float(pm.group(2)) / 100
        elif pm:
            col, pct = pm.group(4), float(pm.group(3)) / 100
        else:
            col, pct = p, None
        c = parse_color(col)
        if c is None:
            raise ColorError("color-mix component")
        items.append((c, pct))
    (c1, p1), (c2, p2) = items
    if p1 is None and p2 is None:
        p1 = p2 = 0.5
    elif p1 is None:
        p1 = 1 - p2
    elif p2 is None:
        p2 = 1 - p1
    total = p1 + p2
    if total <= 0:
        raise ColorError("color-mix zero")
    alpha_mult = min(1.0, total)
    p1, p2 = p1 / total, p2 / total
    v1 = list(_to_space(space, to_xyz65("srgb", c1["rgb"])))
    v2 = list(_to_space(space, to_xyz65("srgb", c2["rgb"])))
    a1, a2 = c1["alpha"], c2["alpha"]
    hi = _POLAR_HUE_INDEX.get(space)
    if hi is not None:
        h1, h2 = v1[hi] % 360, v2[hi] % 360
        d = h2 - h1
        if hue_mode == "shorter":
            if d > 180:
                h1 += 360
            elif d < -180:
                h2 += 360
        elif hue_mode == "longer":
            if 0 < d < 180:
                h1 += 360
            elif -180 < d <= 0:
                h2 += 360
        elif hue_mode == "increasing" and d < 0:
            h2 += 360
        elif hue_mode == "decreasing" and d > 0:
            h1 += 360
        v1[hi], v2[hi] = h1, h2
    a = a1 * p1 + a2 * p2
    out = []
    for i in range(3):
        if i == hi:
            out.append((v1[i] * p1 + v2[i] * p2) % 360)
        else:
            pre = v1[i] * a1 * p1 + v2[i] * a2 * p2
            out.append(pre / a if a else 0.0)
    if space == "oklab" or space == "oklch" or space == "lab" or space == "lch" or space in _PREDEF or space in ("hsl", "hwb"):
        res = _result(space if space != "xyz" else "xyz-d65", tuple(out), a * alpha_mult)
        res["space"] = "color-mix/" + space
        return res
    raise ColorError("color-mix space")


def parse_structured(v):
    """DTCG 2025 color object {colorSpace, components, alpha, hex} or Figma {r,g,b,a} (0..1)."""
    if not isinstance(v, dict):
        return None
    try:
        if "colorSpace" in v and "components" in v:
            sp = str(v["colorSpace"]).lower()
            comps = [0.0 if c == "none" else float(c) for c in v["components"]]
            alpha = float(v.get("alpha", 1.0))
            if sp == "hsl":
                coords = (comps[0], comps[1] / 100, comps[2] / 100)
            elif sp == "hwb":
                coords = (comps[0], comps[1] / 100, comps[2] / 100)
            elif sp in ("lab", "lch", "oklab", "oklch") or sp in _PREDEF:
                coords = tuple(comps[:3])
            else:
                raise ColorError("space")
            r = _result(sp, coords, alpha)
            r["space"] = "dtcg/" + sp
            hx = v.get("hex")
            if isinstance(hx, str):
                r["hex_declared"] = hx.lower()
            return r
        if "hex" in v and isinstance(v["hex"], str):
            r = parse_color(v["hex"] if v["hex"].startswith("#") else "#" + v["hex"])
            if r and "alpha" in v:
                r = dict(r)
                r["alpha"] = float(v["alpha"])
            return r
        if all(k in v for k in ("r", "g", "b")) and all(isinstance(v[k], (int, float)) for k in ("r", "g", "b")):
            vals = [float(v[k]) for k in ("r", "g", "b")]
            if max(vals) > 1.0:
                vals = [x / 255 for x in vals]
            r = _result("srgb", tuple(vals), float(v.get("a", 1.0)) if not isinstance(v.get("a"), str) else 1.0)
            r["space"] = "rgb-object"
            return r
    except (ColorError, ValueError, TypeError, IndexError):
        return None
    return None

