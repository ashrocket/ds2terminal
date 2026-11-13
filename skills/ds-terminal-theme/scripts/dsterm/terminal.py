"""terminal.py - write Apple Terminal .terminal profiles (stdlib only, Python >= 3.9).

Only the verified sRGB encoding is kept (variants c and d of the format research):

  NSColorSpace 1, NSComponents "r g b a" (sRGB, no NUL, alpha always present),
  NSRGB fallback (ends in NUL), NSCustomColorSpace -> {NSID 7, NSICC <sRGB ICC bytes>},
  NSLinearExposure "1".

The ICC bytes come from /System/Library/ColorSync/Profiles/sRGB Profile.icc. When that
file is missing (Linux, CI), the color space is {NSID 7} with no NSICC (variant d,
which decodes the same on macOS 26).

The NSRGB fallback is sRGB converted to Generic RGB, as AppKit writes it. macOS 26 ignores
NSRGB when NSComponents is present (variant c3), so the fallback only helps old readers.

Never write sRGB numbers into a Generic RGB color (NSColorSpace 1 with no custom space):
that shifts colors by up to 63/255.
"""
import os
import plistlib

ICC_DIR = "/System/Library/ColorSync/Profiles"
SRGB_ICC_PATH = os.path.join(ICC_DIR, "sRGB Profile.icc")

PROFILE_VERSION = 2.09
DEFAULT_FONT = "SFMonoTerminal-Regular"

ANSI_KEYS = (
    "ANSIBlackColor", "ANSIRedColor", "ANSIGreenColor", "ANSIYellowColor",
    "ANSIBlueColor", "ANSIMagentaColor", "ANSICyanColor", "ANSIWhiteColor",
    "ANSIBrightBlackColor", "ANSIBrightRedColor", "ANSIBrightGreenColor",
    "ANSIBrightYellowColor", "ANSIBrightBlueColor", "ANSIBrightMagentaColor",
    "ANSIBrightCyanColor", "ANSIBrightWhiteColor",
)
COLOR_KEYS = ANSI_KEYS + ("BackgroundColor", "TextColor", "TextBoldColor",
                          "CursorColor", "SelectionColor")
CURSOR_TYPES = {"block": 0, "underline": 1, "bar": 2}

_cache = {}


def _read(path):
    if path not in _cache:
        with open(path, "rb") as f:
            _cache[path] = f.read()
    return _cache[path]


def srgb_icc_bytes():
    """The sRGB ICC profile bytes, or None when the file does not exist."""
    if os.path.isfile(SRGB_ICC_PATH):
        return _read(SRGB_ICC_PATH)
    return None


# ---------------------------------------------------------------- NSRGB fallback
# AppKit writes an NSRGB fallback in Generic RGB (gamma 1.8). This matrix maps linear sRGB
# to linear Generic RGB. It was fitted to 43 in-gamut fallbacks that AppKit wrote
# with the real ICC profiles on a Mac; the max error is 1.2e-5 (0.003/255).
# So the output is the same on macOS and Linux, apart from the NSICC bytes.
_SRGB_TO_GENERIC = (
    (0.974850784866691, 0.02731500820475384, -0.0021599777255653153),
    (-0.020012943087016725, 1.0541909469399768, -0.03422455777805759),
    (0.001684182737306103, 0.0015554067931078577, 0.996742268831773),
)


def _srgb_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def srgb_to_generic(rgb):
    """sRGB -> Generic RGB (gamma 1.8), clipped to [0, 1]."""
    lin = [_srgb_lin(float(c)) for c in rgb]
    out = []
    for row in _SRGB_TO_GENERIC:
        v = sum(row[k] * lin[k] for k in range(3))
        out.append(max(0.0, min(1.0, v)) ** (1.0 / 1.8))
    return out


# ---------------------------------------------------------------- archives

def fmt(x):
    """AppKit's number format for NSRGB / NSComponents strings."""
    s = "%.10g" % float(x)
    return "0" if s in ("-0", "-0.0") else s


def parse_hex(h):
    """'#rrggbb' / '#rrggbbaa' / '#rgb' -> (r, g, b, a) floats."""
    h = h.strip().lstrip("#")
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    if len(h) not in (6, 8):
        raise ValueError("bad hex color %r" % h)
    vals = [int(h[i:i + 2], 16) / 255.0 for i in range(0, len(h), 2)]
    if len(vals) == 3:
        vals.append(1.0)
    return tuple(vals)


def _cls(name):
    return {"$classname": name, "$classes": [name, "NSObject"]}


def _keyed(objects):
    return plistlib.dumps({"$version": 100000, "$archiver": "NSKeyedArchiver",
                           "$top": {"root": plistlib.UID(1)}, "$objects": objects},
                          fmt=plistlib.FMT_BINARY, sort_keys=False)


def _rgb_bytes(vals, alpha, nul=True, always_alpha=False):
    parts = [fmt(v) for v in vals]
    if always_alpha or alpha != 1.0:
        parts.append(fmt(alpha))
    s = " ".join(parts).encode("ascii")
    return s + b"\0" if nul else s


def color_archive(rgba, icc="auto", nsrgb="generic"):
    """NSKeyedArchiver bytes for one sRGB NSColor.

    rgba: (r, g, b, a) sRGB floats 0..1.
    icc: "auto" (embed the ICC bytes when the file exists), "none" (always {NSID 7}).
    nsrgb: "generic" (AppKit's Generic RGB fallback) or "same" (repeat the sRGB values).
    """
    r, g, b, a = [float(v) for v in rgba]
    fb = srgb_to_generic((r, g, b)) if nsrgb == "generic" else (r, g, b)
    icc_bytes = srgb_icc_bytes() if icc == "auto" else None
    root = {"$class": plistlib.UID(5 if icc_bytes else 4),
            "NSComponents": _rgb_bytes((r, g, b), a, nul=False, always_alpha=True),
            "NSRGB": _rgb_bytes(fb, a), "NSColorSpace": 1,
            "NSCustomColorSpace": plistlib.UID(2), "NSLinearExposure": b"1"}
    if icc_bytes:
        cs = {"NSID": 7, "NSICC": plistlib.UID(3), "$class": plistlib.UID(4)}
        return _keyed(["$null", root, cs, icc_bytes, _cls("NSColorSpace"), _cls("NSColor")])
    cs = {"NSID": 7, "$class": plistlib.UID(3)}
    return _keyed(["$null", root, cs, _cls("NSColorSpace"), _cls("NSColor")])


def font_archive(postscript_name, size):
    """NSFont archive as AppKit writes it (NSfFlags is 16)."""
    root = {"NSSize": float(size), "NSfFlags": 16, "NSName": plistlib.UID(2),
            "$class": plistlib.UID(3)}
    return _keyed(["$null", root, clean_name(postscript_name), _cls("NSFont")])


# ---------------------------------------------------------------- decoding (tests, report)

def decode_color(blob):
    """Return (r, g, b, a, info) from an archive that color_archive wrote."""
    d = plistlib.loads(blob)
    objs = d["$objects"]
    root = objs[d["$top"]["root"].data]
    comps = [float(x) for x in root["NSComponents"].decode("ascii").split()]
    cs = objs[root["NSCustomColorSpace"].data]
    info = {"NSColorSpace": root["NSColorSpace"], "NSID": cs.get("NSID"),
            "has_icc": "NSICC" in cs, "nsrgb": root["NSRGB"]}
    return comps[0], comps[1], comps[2], comps[3], info


def decode_font(blob):
    d = plistlib.loads(blob)
    objs = d["$objects"]
    root = objs[d["$top"]["root"].data]
    return objs[root["NSName"].data], root["NSSize"]


# ---------------------------------------------------------------- profile

def build_profile(name, colors, font=(DEFAULT_FONT, 13.0), cursor="block", cursor_blink=False,
                  columns=None, rows=None, icc="auto", nsrgb="generic", background_alpha=1.0):
    """Return the profile dict. colors: {ColorKey: '#rrggbb' or '#rrggbbaa'}.
    The background is opaque (alpha 1, blur 0) unless background_alpha < 1 (--translucent)."""
    missing = [k for k in COLOR_KEYS if k not in colors]
    if missing:
        raise KeyError("missing color keys: %s" % ", ".join(missing))
    d = {
        "type": "Window Settings",
        "name": clean_name(name),
        "ProfileCurrentVersion": PROFILE_VERSION,
        "Font": font_archive(font[0], font[1]),
        "FontAntialias": True,
        "FontWidthSpacing": 1.0,
        "FontHeightSpacing": 1.0,
        "UseBoldFonts": True,
        "UseBrightBold": False,
        "BlinkText": False,
        "DisableANSIColor": False,
        "DynamicANSIForegroundColors": False,
        "CursorType": CURSOR_TYPES[cursor],
        "CursorBlink": bool(cursor_blink),
        "BackgroundBlur": 0.0,
    }
    if columns:
        d["columnCount"] = int(columns)
    if rows:
        d["rowCount"] = int(rows)
    for k, v in colors.items():
        if k not in COLOR_KEYS:
            raise KeyError("unknown color key %r" % k)
        rgba = parse_hex(v)
        if k == "BackgroundColor":
            rgba = rgba[:3] + (float(background_alpha),)
        d[k] = color_archive(rgba, icc=icc, nsrgb=nsrgb)
    return d


def dumps_profile(profile):
    return plistlib.dumps(profile, fmt=plistlib.FMT_XML, sort_keys=True)


def write_profile(path, profile):
    """Write an XML plist .terminal file (the format of Terminal's export)."""
    data = dumps_profile(profile)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def _xml_ok(ch):
    o = ord(ch)
    return 0x20 <= o <= 0xD7FF and o != 0x7F or 0xE000 <= o <= 0xFFFD or o >= 0x10000


def clean_name(name):
    """Profile name that an XML plist accepts: control characters, surrogates and U+FFFE/U+FFFF
    become spaces; runs collapse."""
    s = "".join(ch if _xml_ok(ch) else " " for ch in str(name))
    return " ".join(s.split()) or "Untitled"


def cap_name(name, max_bytes=200):
    """Clean the name and cap it at max_bytes of UTF-8, so a mode suffix still fits in a file name."""
    s = clean_name(name)
    while len(s.encode("utf-8")) > max_bytes:
        s = s[:-1]
    return s.lstrip(".").strip() or "Untitled"


def safe_filename(name, max_bytes=240):
    """File name for a profile name: no '/' or ':', at most 240 UTF-8 bytes."""
    s = "".join("-" if ch in "/:" else ch for ch in clean_name(name)).lstrip(".") or "Untitled"
    while len(s.encode("utf-8")) > max_bytes:
        s = s[:-1]
    return s + ".terminal"
