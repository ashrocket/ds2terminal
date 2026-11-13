"""colorlab: color science primitives for terminal-theme readability.

Python 3.9+, standard library only. No numpy.

All RGB tuples are gamma-encoded sRGB floats in [0, 1] unless a name says
"linear". Hex strings are "#rrggbb" (or "#rgb").

Sources (constants copied from these files; see tests for reference values):
  sRGB transfer, sRGB<->XYZ (rational D65 matrices), XYZ<->OKLab (64-bit
  matrices), Bradford D65->D50, CIE Lab:
      CSS Color 4, conversions.js
      https://github.com/w3c/csswg-drafts/blob/main/css-color-4/conversions.js
      (fetched at csswg-drafts commit 7b4c69ecaf9289d1bd5455d6bea10eec0b4a4399)
      OKLab: Bjorn Ottosson, https://bottosson.github.io/posts/oklab/
  Gamut mapping: CSS Color 4 section 13.2 "Binary Search Gamut Map with Local
      MINDE", https://www.w3.org/TR/css-color-4/#binsearch (JND 0.02,
      epsilon 0.0001).
  WCAG 2.x relative luminance and contrast ratio:
      https://www.w3.org/TR/WCAG22/#dfn-relative-luminance
      https://www.w3.org/TR/WCAG22/#dfn-contrast-ratio
  APCA-W3 0.0.98G-4g (apca-w3 0.1.9):
      https://github.com/Myndex/apca-w3/blob/master/src/apca-w3.js
      (fetched at commit 6c5c066cf0c853507930a4239b129283b8e05353)
  CIEDE2000: Sharma, Wu, Dalal (2005), "The CIEDE2000 color-difference
      formula: implementation notes, supplementary test data, and
      mathematical observations", Color Res. Appl. 30(1):21-30.
  CVD simulation: Machado, Oliveira, Fernandes (2009), "A Physiologically-
      based Model for Simulation of Color Vision Deficiency", IEEE TVCG
      15(6):1291-1298, doi:10.1109/TVCG.2009.113. Severity-1.0 matrices from
      http://www.inf.ufrgs.br/~oliveira/pubs_files/CVD_Simulation/CVD_Simulation.html
      as copied in colorspacious cvd.py (commit 58948923b7...). Applied to
      LINEAR sRGB.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

RGB = Tuple[float, float, float]
Vec3 = Tuple[float, float, float]

# ---------------------------------------------------------------- hex / math


def parse_hex(s: str) -> RGB:
    """'#rrggbb', 'rrggbb', '#rgb' -> sRGB floats in [0,1]."""
    h = s.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 8:  # rrggbbaa: alpha ignored here
        h = h[:6]
    if len(h) != 6:
        raise ValueError("bad hex color: %r" % (s,))
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def to_hex(rgb: Sequence[float]) -> str:
    out = []
    for c in rgb:
        v = int(round(max(0.0, min(1.0, c)) * 255.0))
        out.append("%02x" % v)
    return "#" + "".join(out)


def _rgb(c) -> RGB:
    """Accept hex string or 3-sequence."""
    if isinstance(c, str):
        return parse_hex(c)
    return (float(c[0]), float(c[1]), float(c[2]))


def _mul(M: Sequence[Sequence[float]], v: Sequence[float]) -> Vec3:
    return (
        M[0][0] * v[0] + M[0][1] * v[1] + M[0][2] * v[2],
        M[1][0] * v[0] + M[1][1] * v[1] + M[1][2] * v[2],
        M[2][0] * v[0] + M[2][1] * v[1] + M[2][2] * v[2],
    )


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


# ---------------------------------------------------------------- sRGB


def srgb_to_linear_channel(c: float) -> float:
    """IEC 61966-2-1 sRGB EOTF, extended to negatives (CSS Color 4 lin_sRGB)."""
    a = abs(c)
    if a <= 0.04045:
        return c / 12.92
    return math.copysign(((a + 0.055) / 1.055) ** 2.4, c)


def linear_to_srgb_channel(c: float) -> float:
    a = abs(c)
    if a > 0.0031308:
        return math.copysign(1.055 * a ** (1.0 / 2.4) - 0.055, c)
    return 12.92 * c


def srgb_to_linear(rgb) -> RGB:
    r, g, b = _rgb(rgb)
    return (srgb_to_linear_channel(r), srgb_to_linear_channel(g), srgb_to_linear_channel(b))


def linear_to_srgb(lin: Sequence[float]) -> RGB:
    return (linear_to_srgb_channel(lin[0]), linear_to_srgb_channel(lin[1]), linear_to_srgb_channel(lin[2]))


# CSS Color 4 conversions.js: lin_sRGB_to_XYZ / XYZ_to_lin_sRGB (D65, rational)
M_LIN_SRGB_TO_XYZ = (
    (506752 / 1228815, 87881 / 245763, 12673 / 70218),
    (87098 / 409605, 175762 / 245763, 12673 / 175545),
    (7918 / 409605, 87881 / 737289, 1001167 / 1053270),
)
M_XYZ_TO_LIN_SRGB = (
    (12831 / 3959, -329 / 214, -1974 / 3959),
    (-851781 / 878810, 1648619 / 878810, 36519 / 878810),
    (705 / 12673, -2585 / 12673, 705 / 667),
)
# CSS Color 4 conversions.js: XYZ_to_OKLab / OKLab_to_XYZ (64-bit, D65)
M_XYZ_TO_LMS = (
    (0.8190224379967030, 0.3619062600528904, -0.1288737815209879),
    (0.0329836539323885, 0.9292868615863434, 0.0361446663506424),
    (0.0481771893596242, 0.2642395317527308, 0.6335478284694309),
)
M_LMS_TO_OKLAB = (
    (0.2104542683093140, 0.7936177747023054, -0.0040720430116193),
    (1.9779985324311684, -2.4285922420485799, 0.4505937096174110),
    (0.0259040424655478, 0.7827717124575296, -0.8086757549230774),
)
M_LMS_TO_XYZ = (
    (1.2268798758459243, -0.5578149944602171, 0.2813910456659647),
    (-0.0405757452148008, 1.1122868032803170, -0.0717110580655164),
    (-0.0763729366746601, -0.4214933324022432, 1.5869240198367816),
)
M_OKLAB_TO_LMS = (
    (1.0000000000000000, 0.3963377773761749, 0.2158037573099136),
    (1.0000000000000000, -0.1055613458156586, -0.0638541728258133),
    (1.0000000000000000, -0.0894841775298119, -1.2914855480194092),
)
# Bradford D65 -> D50 (CSS Color 4 conversions.js D65_to_D50)
M_D65_TO_D50 = (
    (1.0479297925449969, 0.022946870601609652, -0.05019226628920524),
    (0.02962780877005599, 0.9904344267538799, -0.017073799063418826),
    (-0.009243040646204504, 0.015055191490298152, 0.7518742814281371),
)
D50_WHITE = (0.3457 / 0.3585, 1.0, (1.0 - 0.3457 - 0.3585) / 0.3585)


def linear_srgb_to_xyz(lin: Sequence[float]) -> Vec3:
    return _mul(M_LIN_SRGB_TO_XYZ, lin)


def xyz_to_linear_srgb(xyz: Sequence[float]) -> Vec3:
    return _mul(M_XYZ_TO_LIN_SRGB, xyz)


def xyz_to_oklab(xyz: Sequence[float]) -> Vec3:
    lms = _mul(M_XYZ_TO_LMS, xyz)
    return _mul(M_LMS_TO_OKLAB, (_cbrt(lms[0]), _cbrt(lms[1]), _cbrt(lms[2])))


def oklab_to_xyz(lab: Sequence[float]) -> Vec3:
    lms = _mul(M_OKLAB_TO_LMS, lab)
    return _mul(M_LMS_TO_XYZ, (lms[0] ** 3, lms[1] ** 3, lms[2] ** 3))


def srgb_to_oklab(rgb) -> Vec3:
    return xyz_to_oklab(linear_srgb_to_xyz(srgb_to_linear(rgb)))


def oklab_to_srgb(lab: Sequence[float]) -> RGB:
    """Unclamped: may return out-of-gamut values."""
    return linear_to_srgb(xyz_to_linear_srgb(oklab_to_xyz(lab)))


def oklab_to_oklch(lab: Sequence[float]) -> Vec3:
    """Returns (L, C, h_degrees). h is NaN when C <= 0.000004 (CSS powerless hue)."""
    L, a, b = lab
    C = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360.0
    if C <= 0.000004:
        h = float("nan")
    return (L, C, h)


def oklch_to_oklab(lch: Sequence[float]) -> Vec3:
    L, C, h = lch
    if h != h:  # NaN hue
        return (L, 0.0, 0.0)
    r = math.radians(h)
    return (L, C * math.cos(r), C * math.sin(r))


def srgb_to_oklch(rgb) -> Vec3:
    return oklab_to_oklch(srgb_to_oklab(rgb))


def oklch_to_srgb(lch: Sequence[float]) -> RGB:
    """Unclamped."""
    return oklab_to_srgb(oklch_to_oklab(lch))


def srgb_to_cielab_d50(rgb) -> Vec3:
    """sRGB -> CIE Lab (D50, Bradford), as CSS Color 4 lab()."""
    xyz = _mul(M_D65_TO_D50, linear_srgb_to_xyz(srgb_to_linear(rgb)))
    eps = 216.0 / 24389.0
    kap = 24389.0 / 27.0
    f = []
    for v, w in zip(xyz, D50_WHITE):
        x = v / w
        f.append(_cbrt(x) if x > eps else (kap * x + 16.0) / 116.0)
    return (116.0 * f[1] - 16.0, 500.0 * (f[0] - f[1]), 200.0 * (f[1] - f[2]))


# ---------------------------------------------------------------- WCAG 2.x


def wcag_luminance(rgb) -> float:
    """WCAG 2.2 relative luminance (piecewise sRGB, 0.2126/0.7152/0.0722)."""
    r, g, b = srgb_to_linear(rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(c1, c2) -> float:
    """WCAG 2.x contrast ratio (L1 + 0.05) / (L2 + 0.05), symmetric, 1..21."""
    a = wcag_luminance(c1)
    b = wcag_luminance(c2)
    hi, lo = (a, b) if a >= b else (b, a)
    return (hi + 0.05) / (lo + 0.05)


# WCAG 2.2 thresholds (https://www.w3.org/TR/WCAG22/)
WCAG_SC_1_4_3_AA_TEXT = 4.5      # SC 1.4.3 Contrast (Minimum), normal text
WCAG_SC_1_4_3_AA_LARGE = 3.0     # SC 1.4.3, large text (>=18pt or 14pt bold)
WCAG_SC_1_4_6_AAA_TEXT = 7.0     # SC 1.4.6 Contrast (Enhanced), normal text
WCAG_SC_1_4_6_AAA_LARGE = 4.5
WCAG_SC_1_4_11_NON_TEXT = 3.0    # SC 1.4.11 Non-text Contrast (UI, focus, cursor)

# ---------------------------------------------------------------- APCA-W3


class SA98G:
    """APCA 0.0.98G-4g constants, verbatim from apca-w3.js."""
    mainTRC = 2.4
    sRco = 0.2126729
    sGco = 0.7151522
    sBco = 0.0721750
    normBG = 0.56
    normTXT = 0.57
    revTXT = 0.62
    revBG = 0.65
    blkThrs = 0.022
    blkClmp = 1.414
    scaleBoW = 1.14
    scaleWoB = 1.14
    loBoWoffset = 0.027
    loWoBoffset = 0.027
    deltaYmin = 0.0005
    loClip = 0.1


def apca_y(rgb) -> float:
    """APCA screen luminance: simple 2.4 exponent, NOT the piecewise sRGB curve."""
    r, g, b = _rgb(rgb)
    # apca-w3 sRGBtoY works on 0-255 ints: chan/255.0 ** 2.4. Floats are identical.
    return (SA98G.sRco * r ** SA98G.mainTRC
            + SA98G.sGco * g ** SA98G.mainTRC
            + SA98G.sBco * b ** SA98G.mainTRC)


def apca_contrast(txt_y: float, bg_y: float) -> float:
    """APCAcontrast(txtY, bgY) -> signed Lc. Positive = dark text on light bg."""
    if not (0.0 <= txt_y <= 1.1 and 0.0 <= bg_y <= 1.1):
        return 0.0
    if txt_y <= SA98G.blkThrs:
        txt_y = txt_y + (SA98G.blkThrs - txt_y) ** SA98G.blkClmp
    if bg_y <= SA98G.blkThrs:
        bg_y = bg_y + (SA98G.blkThrs - bg_y) ** SA98G.blkClmp
    if abs(bg_y - txt_y) < SA98G.deltaYmin:
        return 0.0
    if bg_y > txt_y:  # BoW
        sapc = (bg_y ** SA98G.normBG - txt_y ** SA98G.normTXT) * SA98G.scaleBoW
        out = 0.0 if sapc < SA98G.loClip else sapc - SA98G.loBoWoffset
    else:  # WoB, negative
        sapc = (bg_y ** SA98G.revBG - txt_y ** SA98G.revTXT) * SA98G.scaleWoB
        out = 0.0 if sapc > -SA98G.loClip else sapc + SA98G.loWoBoffset
    return out * 100.0


def apca_lc(text, background) -> float:
    """Signed APCA Lc of TEXT on BACKGROUND (argument order matters)."""
    return apca_contrast(apca_y(text), apca_y(background))


# APCA Bronze Simple Mode levels (|Lc|), from "APCA in a Nutshell"
# https://git.apcacontrast.com/documentation/APCA_in_a_Nutshell
APCA_BODY_PREFERRED = 90.0   # fluent body text >= 14px/400
APCA_BODY_MIN = 75.0         # body text >= 18px/400; non-body >= 15px/400
APCA_CONTENT_MIN = 60.0      # content text that is not body text
APCA_LARGE_MIN = 45.0        # headlines, fine-detail pictograms
APCA_SPOT_MIN = 30.0         # absolute minimum for any text (placeholder, disabled)
APCA_NONTEXT_MIN = 15.0      # point of invisibility for many users

# ---------------------------------------------------------------- deltaE


def delta_e_ok(lab1: Sequence[float], lab2: Sequence[float]) -> float:
    """deltaEOK: Euclidean distance in OKLab (CSS Color 4 section 13.1.2). JND ~0.02."""
    return math.sqrt((lab1[0] - lab2[0]) ** 2 + (lab1[1] - lab2[1]) ** 2 + (lab1[2] - lab2[2]) ** 2)


def delta_e_ok_rgb(c1, c2) -> float:
    return delta_e_ok(srgb_to_oklab(c1), srgb_to_oklab(c2))


def ciede2000(lab1: Sequence[float], lab2: Sequence[float],
              kL: float = 1.0, kC: float = 1.0, kH: float = 1.0) -> float:
    """CIEDE2000 per Sharma et al. 2005 (validated against their 34 test pairs)."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    G = 0.5 * (1.0 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25.0 ** 7)))
    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = math.hypot(a1p, b1)
    C2p = math.hypot(a2p, b2)
    h1p = 0.0 if (a1p == 0 and b1 == 0) else math.degrees(math.atan2(b1, a1p)) % 360.0
    h2p = 0.0 if (a2p == 0 and b2 == 0) else math.degrees(math.atan2(b2, a2p)) % 360.0
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180.0:
            dhp -= 360.0
        elif dhp < -180.0:
            dhp += 360.0
    dHp = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))
    Lbarp = (L1 + L2) / 2.0
    Cbarp = (C1p + C2p) / 2.0
    if C1p * C2p == 0:
        hbarp = h1p + h2p
    else:
        if abs(h1p - h2p) <= 180.0:
            hbarp = (h1p + h2p) / 2.0
        elif h1p + h2p < 360.0:
            hbarp = (h1p + h2p + 360.0) / 2.0
        else:
            hbarp = (h1p + h2p - 360.0) / 2.0
    T = (1.0 - 0.17 * math.cos(math.radians(hbarp - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hbarp))
         + 0.32 * math.cos(math.radians(3.0 * hbarp + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hbarp - 63.0)))
    dtheta = 30.0 * math.exp(-(((hbarp - 275.0) / 25.0) ** 2))
    RC = 2.0 * math.sqrt(Cbarp ** 7 / (Cbarp ** 7 + 25.0 ** 7))
    SL = 1.0 + (0.015 * (Lbarp - 50.0) ** 2) / math.sqrt(20.0 + (Lbarp - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cbarp
    SH = 1.0 + 0.015 * Cbarp * T
    RT = -math.sin(math.radians(2.0 * dtheta)) * RC
    return math.sqrt((dLp / (kL * SL)) ** 2 + (dCp / (kC * SC)) ** 2 + (dHp / (kH * SH)) ** 2
                     + RT * (dCp / (kC * SC)) * (dHp / (kH * SH)))


def ciede2000_rgb(c1, c2) -> float:
    return ciede2000(srgb_to_cielab_d50(c1), srgb_to_cielab_d50(c2))


# ---------------------------------------------------------------- gamut mapping


def in_srgb_gamut(rgb: Sequence[float], eps: float = 0.000075) -> bool:
    return all(-eps <= c <= 1.0 + eps for c in rgb)


def clip_srgb(rgb: Sequence[float]) -> RGB:
    return (max(0.0, min(1.0, rgb[0])), max(0.0, min(1.0, rgb[1])), max(0.0, min(1.0, rgb[2])))


def gamut_map_oklch(lch: Sequence[float]) -> RGB:
    """CSS Color 4 section 13.2 Binary Search Gamut Map with Local MINDE, to sRGB.

    Input OKLCH (L 0..1, C, h deg). Returns in-gamut sRGB floats.
    """
    JND = 0.02
    EPS = 0.0001
    L, C, h = lch
    if L >= 1.0:
        return (1.0, 1.0, 1.0)
    if L <= 0.0:
        return (0.0, 0.0, 0.0)
    origin_rgb = oklch_to_srgb((L, C, h))
    if in_srgb_gamut(origin_rgb):
        return clip_srgb(origin_rgb)

    def delta(rgb_clipped, lch_cur):
        return delta_e_ok(srgb_to_oklab(rgb_clipped), oklch_to_oklab(lch_cur))

    current = [L, C, h]
    clipped = clip_srgb(oklch_to_srgb(current))
    E = delta(clipped, current)
    if E < JND:
        return clipped
    lo = 0.0
    hi = C
    min_in_gamut = True
    while hi - lo > EPS:
        chroma = (lo + hi) / 2.0
        current[1] = chroma
        cur_rgb = oklch_to_srgb(current)
        if min_in_gamut and in_srgb_gamut(cur_rgb):
            lo = chroma
            continue
        clipped = clip_srgb(cur_rgb)
        E = delta(clipped, current)
        if E < JND:
            if JND - E < EPS:
                return clipped
            min_in_gamut = False
            lo = chroma
        else:
            hi = chroma
    return clipped


# ---------------------------------------------------------------- CVD

# Machado et al. 2009, severity 1.0 (protanopia, deuteranopia, tritanopia).
MACHADO_2009 = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779),
               (-0.078411, 0.930809, 0.147602),
               (0.004733, 0.691367, 0.303900)),
}


def simulate_cvd(rgb, kind: str, matrix=None, clip: bool = True) -> RGB:
    """Simulate color-vision deficiency: matrix applied in LINEAR sRGB."""
    M = matrix if matrix is not None else MACHADO_2009[kind]
    lin = _mul(M, srgb_to_linear(rgb))
    if clip:
        lin = (max(0.0, min(1.0, lin[0])), max(0.0, min(1.0, lin[1])), max(0.0, min(1.0, lin[2])))
    return linear_to_srgb(lin)


# ---------------------------------------------------------------- helpers


def hue_diff(h1: float, h2: float) -> float:
    """Smallest absolute angle between two hues in degrees (NaN if either is NaN)."""
    d = abs((h1 - h2) % 360.0)
    return min(d, 360.0 - d)


def composite(fg, bg, alpha: float) -> RGB:
    """Source-over in gamma-encoded sRGB (how AppKit blends window bg over desktop)."""
    f = _rgb(fg)
    b = _rgb(bg)
    return tuple(alpha * f[i] + (1.0 - alpha) * b[i] for i in range(3))  # type: ignore


# Terminal draws faint (SGR 2) text as the text color mixed toward the cell background. Measured on
# Terminal 2.15 (macOS 26.7.3), 2026-11-12, with tools/measure/drive_probe2.py on two
# opaque profiles (dark and light) and on black and white cell backgrounds: 38 samples. For each
# sRGB-encoded channel:
#     faint = ((1 - DIM_BLEND) * color^DIM_POWER + DIM_BLEND * bg^DIM_POWER) ^ (1 / DIM_POWER)
# DIM_BLEND 0.60 and DIM_POWER 1.26 fit the samples to RMS 1.8 of 255 (fit_faint.py). A plain 50% mix
# in sRGB (the model before the measurement) has RMS 17: real faint text is weaker, most of all dark
# text on a light background (black on white draws as #a9a9a9, not #808080).
DIM_BLEND = 0.60
DIM_POWER = 1.26


def faint(color, bg, blend: Optional[float] = None) -> str:
    """Hex of faint (SGR 2) text in this color on bg. blend is the share of the background."""
    t = DIM_BLEND if blend is None else blend
    c = _rgb(color)
    b = _rgb(bg)
    p = DIM_POWER
    return to_hex(tuple(((1.0 - t) * max(0.0, c[i]) ** p + t * max(0.0, b[i]) ** p) ** (1.0 / p)
                        for i in range(3)))


def translucent_backgrounds(bg, alpha: float, gates: Optional[dict] = None) -> List[Tuple[str, str]]:
    """[(desktop, composite hex)]: what a background of this alpha looks like over each desktop
    in GATES["translucency"]. Empty when the background is opaque."""
    if alpha >= 1.0:
        return []
    G = gates or GATES
    return [(d, to_hex(composite(bg, d, alpha))) for d in G["translucency"]["gate"]["desktops"]]


ANSI_NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
              "brightBlack", "brightRed", "brightGreen", "brightYellow",
              "brightBlue", "brightMagenta", "brightCyan", "brightWhite")


# ---------------------------------------------------------------- solvers


def lc_abs(text, background) -> float:
    return abs(apca_lc(text, background))


def solve_lightness_for_lc(background, hue: float, chroma: float, target_abs_lc: float,
                           lighter: bool) -> Optional[Tuple[float, RGB]]:
    """Find OKLCH L (hue/chroma fixed, gamut-mapped) whose |Lc| on `background`
    equals target_abs_lc, with text lighter (dark mode) or darker (light mode)
    than the background. Returns (L, rgb) or None if unreachable."""
    bgL = srgb_to_oklab(background)[0]
    lo, hi = (bgL, 1.0) if lighter else (0.0, bgL)

    def lc_at(L):
        rgb = gamut_map_oklch((L, chroma, hue))
        return lc_abs(rgb, background), rgb

    far = hi if lighter else lo
    best_lc, best_rgb = lc_at(far)
    if best_lc < target_abs_lc:
        return None
    for _ in range(40):
        mid = (lo + hi) / 2.0
        v, _rgb = lc_at(mid)
        # |Lc| grows as L moves away from bg
        if lighter:
            if v >= target_abs_lc:
                hi = mid
            else:
                lo = mid
        else:
            if v >= target_abs_lc:
                lo = mid
            else:
                hi = mid
    L = hi if lighter else lo
    return L, gamut_map_oklch((L, chroma, hue))


# ---------------------------------------------------------------- readability gates
#
# level "gate"   = must pass; a generator must repair the theme until it passes.
# level "target" = should pass; a generator optimizes toward it.
# All Lc values are |APCA Lc| (polarity removed). dEok = Euclidean OKLab distance.
# Thresholds are calibrated against 27 reference themes (see themes.json, stats.json).

GATES = {
    "version": "1.0",
    "fg_contrast": {
        "gate": {"min_lc": 75.0, "min_wcag": 7.0},
        "target": {"min_lc": 90.0},
        "why": "Default text is body-like text at ~12-13px/400. APCA bronze: Lc 75 is the body-text "
               "minimum and Lc 90 the preferred level (and the level for 12px/400 non-body text). "
               "WCAG 2.2 SC 1.4.6 (AAA) 7:1 as the second floor.",
    },
    "halation": {
        "modes": ["dark"],
        "gate": {"max_lc": 104.0, "slots": ["foreground", "bold", "white", "brightWhite"]},
        "target": {"fg_max_lc": 100.0, "fg_max_L": 0.94, "bg_min_L": 0.15},
        "why": "No standard sets a maximum for small text; this is a heuristic. Lc > 104 is reachable "
               "only with near-#fff text on near-#000 backgrounds (#fff on #000 = Lc -107.9), the "
               "pairing that causes halation/smear for astigmatic readers. Reference dark themes: fg L "
               "0.65-0.98 (median 0.88), bg L 0.18-0.33.",
    },
    "ansi_normal": {
        "slots": [1, 2, 3, 4, 5, 6],
        "gate": {"min_lc": 45.0, "min_wcag": 3.0},
        "target_dark": {"min_lc": 60.0, "min_wcag": 4.5},
        "target_light": {"min_lc": 54.0, "max_lc": 66.0, "min_wcag": 3.0},
        "why": "Colored text (errors, diffs, ls, grep) must be readable. APCA Lc 45 = large/heavy text "
               "minimum, Lc 60 = content text minimum. WCAG 3:1 (SC 1.4.3 large text) floor, 4.5:1 "
               "target in dark mode. Light mode: normal slots are also BACKGROUNDS under black text "
               "(tmux, htop, macOS ls); with black ~#1b1f24 on bg ~#fafafa both constraints hold only "
               "for Lc ~54-68 (WCAG 3.0-4.4), so the light target is a band.",
    },
    "ansi_bright": {
        "slots": [9, 10, 11, 12, 13, 14],
        "gate": {"min_lc": 45.0, "min_wcag": 3.0},
        "target_dark": {"min_lc": 60.0, "min_wcag": 4.5},
        "target_light": {"min_lc": 66.0, "min_wcag": 4.5},
        "why": "Bright colors are text colors too (bold-as-bright, prompts). Light mode: make bright = "
               "the darker, higher-contrast ink (as Selenized Light does), since apps rarely use 100-107 "
               "backgrounds.",
    },
    "bright_relation": {
        "gate": {"max_hue_diff": 30.0, "min_chroma_ratio": 0.5, "only_if_normal_C_at_least": 0.04},
        "target": {"min_dEok": 0.03, "dark_min_dL": -0.01, "light_min_dLc": 0.0},
        "why": "Bright N must read as the same hue as normal N (bright red is red). Bold-as-bright "
               "needs a visible step (>= 1.5 JND).",
    },
    "dim_brightBlack": {
        "slots": [8],
        "gate": {"min_lc": 30.0, "max_lc_vs_fg_gap": 15.0},
        "target": {"min_lc": 40.0, "max_lc": 60.0, "max_lc_vs_fg_gap": 25.0, "min_wcag": 3.0},
        "why": "Color 8 is the de-facto 'dim' color: zsh-autosuggestions default fg=8, comments, git "
               "graph, prompt metadata. APCA Lc 30 is the absolute minimum for spot-readable text "
               "(placeholder/disabled). It must stay clearly dimmer than fg (>= Lc 15 lower).",
    },
    "grays_dark": {
        "modes": ["dark"],
        "gate": {"white_min_lc": 60.0, "brightWhite_min_lc": 60.0},
        "target": {"white_min_lc": 75.0, "brightWhite_ge_white": True, "black_min_dEok_vs_bg": 0.03,
                   "black_max_dL_vs_bg": 0.15},
        "why": "Dark mode: 7/15 are text colors. 0 is a background/surface color and the text color "
               "on colored bars (htop, tmux, macOS ls), so it stays dark; black-as-text on the default "
               "background is not supported (11/14 reference dark themes have |Lc| < 15 for it).",
    },
    "inks_light": {
        "modes": ["light"],
        "gate": {"black_min_lc": 75.0, "white_min_lc": 30.0, "brightWhite_min_lc": 30.0},
        "target": {"black_ge_fg": True, "white_lc_range": [45.0, 60.0], "brightWhite_lighter_than_white": True},
        "why": "Light mode: the classic trap is white (7/15) text vanishing on a light background; many "
               "tools emit 37/97 assuming a dark terminal (git blame default 'white', CLI headings). "
               "Keep 7/15 light but spot-readable (Lc >= 30, e.g. ~#c7c7c7 on #fff), 15 lighter than 7 so "
               "they still work as light backgrounds. 0 must be a full-strength ink.",
    },
    "separation": {
        "gate": {"min_dEok": 0.06},
        "target": {"min_dEok": 0.10, "min_hue_diff": 25.0, "hue_needs_C": 0.05},
        "why": "Each of the six hues is a separate category; 0.06 = 3x the OKLab JND (0.02). Text "
               "glyphs are small fields, which need more than 1 JND.",
    },
    "cvd": {
        "types": ["protan", "deutan"],
        "target_types": ["protan", "deutan", "tritan"],
        "pairs": {"red/green": [1, 2], "red/yellow": [1, 3], "red/magenta": [1, 5]},
        "gate": {"red/green": 0.06, "red/yellow": 0.05, "red/magenta": 0.05},
        "target": {"red/green": 0.10, "red_green_min_dL": 0.05, "tritan_all_pairs": 0.05},
        "how": "Measured lever (cvd_search.py): a red/green lightness gap. Dark: red |Lc| ~55, green |Lc| "
               "~85-88 gives worst-case 0.14-0.16; light: red ~55, green ~66-72 gives 0.12-0.13. Red hue "
               "~10-20 (crimson) + green hue ~125-135 (yellow-green) beats conventional 25/145.",
        "why": "Machado 2009 severity 1.0 dichromat simulation. red/green = git diff and git status; "
               "red/yellow = rustc/cargo error vs warning; red/magenta = gcc/clang error vs warning. "
               "Gate covers protan+deutan (~6% of men, per Machado/colorspacious notes); tritan (<0.01%) "
               "is a target only. "
               "A lightness gap survives every CVD type. Reference: GitHub Colorblind themes reach 0.27-0.31 "
               "for red/green; the median reference theme is ~0.10.",
    },
    "selection": {
        "gate": {"fg_min_wcag": 4.5, "fg_min_lc": 60.0, "sel_min_dEok_vs_bg": 0.05, "ansi_min_lc": 30.0},
        "target": {"fg_min_lc": 75.0, "sel_dEok_vs_bg_range": [0.06, 0.20], "ansi_min_lc": 45.0},
        "why": "Terminal.app has no selection-text color key (SelectionColor only), so selected text keeps "
               "its own color over SelectionColor: fg and every chromatic ANSI color must stay readable on "
               "it, and the highlight must be visible against bg. APCA clips |Lc| < ~7 to 0, so "
               "selection-vs-bg uses dEok.",
    },
    "cursor": {
        "gate": {"min_wcag": 3.0},
        "target": {"min_wcag": 4.5, "min_lc": 45.0},
        "why": "WCAG 2.2 SC 1.4.11 non-text contrast 3:1 (and SC 2.4.13 AAA focus 3:1). Target 4.5:1 so a "
               "glyph drawn in bg color on a block cursor stays readable (Terminal.app has no cursor-text "
               "color key).",
    },
    "bold": {
        "gate": {"max_lc_drop_vs_fg": 2.0},
        "target": {"max_dEok_vs_fg": 0.10},
        "why": "TextBoldColor must not be dimmer than fg, and should read as the same color.",
    },
    "text_on_color": {
        "gate": {"black_on": [2, 3, 6], "min_lc": 30.0},
        "target": {"best_of_black_white_min_lc": {"dark": 45.0, "light": 35.0}, "black_on_red_min_lc": 30.0},
        "why": "ANSI colors are used as BACKGROUNDS with black text: tmux status-style bg=green,fg=black; "
               "htop function bar and selection black-on-cyan, headers black-on-green/yellow; macOS ls "
               "LSCOLORS default exfxcxdxbxegedabagacadah (black on red/cyan/green/brown). In light mode "
               "the best-of target is 35, because ANSI >= WCAG 3:1 on a light bg caps black-on-color at "
               "~Lc 30-45 (verified with the solver).",
    },
    "faint_text": {
        "slots": [1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14],
        "gate": {"fg_min_lc": 30.0, "fg_min_lc_dark": 30.0, "ansi_min_lc": 15.0},
        "target": {"fg_min_lc": 38.0, "fg_min_lc_dark": 33.0, "ansi_min_lc": 20.0},
        "why": "User feedback: Claude Code draws collapsed previews and secondary text with SGR 2 "
               "(faint), which almost vanished. The faint color is measured (DIM_BLEND, DIM_POWER), and it is "
               "weak: faint #ffffff reaches at most Lc 36 on a dark background, and faint #000000 reaches Lc 46 "
               "on #ffffff. The limits before the measurement (text 45, hue colors 30) cannot be reached: a "
               "faint hue color in dark mode reaches about Lc 33 at most (a pale yellow), and most hues stay below Lc 30. Faint text has "
               "the role of bright black (secondary text), so it has the same gate: Lc 30, the APCA minimum "
               "for spot text. A faint hue color must stay discernible: Lc 15, the APCA minimum for a visible "
               "non-text item. Reference: the faint hue colors of Snazzy, Dracula, GitHub Dark and Tokyo "
               "Night are Lc 12-33. A failure raises the text or color contrast, never the blend.",
    },
    "translucency": {
        "gate": {"desktops": ["#000000", "#ffffff"]},
        "why": "User feedback (a light translucent theme with Claude Code): a translucent background lets the "
               "desktop show through and text fades. The generator emits alpha 1 and blur 0 by default. With "
               "alpha < 1, the background is composited over a black and a white desktop (the two extremes), "
               "and every gate must pass on both composites too. Blur and desktop detail are not modelled.",
    },
}


def _hue_ok(lch, min_c):
    return lch[1] >= min_c and lch[2] == lch[2]


def check_theme(theme: dict, gates: Optional[dict] = None) -> dict:
    """Check a theme dict {background, foreground, ansi[16], cursor?, selection_background?, bold?,
    background_alpha?} against GATES. Returns {name, mode, pass, failures[], misses[], metrics{}}."""
    G = gates or GATES
    bg = theme["background"]
    fg = theme["foreground"]
    a = theme["ansi"]
    bgL = srgb_to_oklab(bg)[0]
    mode = theme.get("mode") or ("dark" if bgL < 0.5 else "light")
    fails = []
    misses = []
    met = {}

    def F(gid, msg):
        fails.append({"id": gid, "detail": msg})

    def M(gid, msg):
        misses.append({"id": gid, "detail": msg})

    fg_lc = lc_abs(fg, bg)
    fg_cr = contrast_ratio(fg, bg)
    met["fg_lc"] = round(fg_lc, 1)
    met["fg_wcag"] = round(fg_cr, 2)
    g = G["fg_contrast"]
    if fg_lc < g["gate"]["min_lc"] or fg_cr < g["gate"]["min_wcag"]:
        F("fg_contrast", "fg |Lc| %.1f, WCAG %.2f (need >= %.0f and >= %.1f)" % (fg_lc, fg_cr, g["gate"]["min_lc"], g["gate"]["min_wcag"]))
    elif fg_lc < g["target"]["min_lc"]:
        M("fg_contrast", "fg |Lc| %.1f < %.0f" % (fg_lc, g["target"]["min_lc"]))

    if mode == "dark":
        g = G["halation"]
        named = {"foreground": fg, "bold": theme.get("bold"), "white": a[7], "brightWhite": a[15]}
        for k in g["gate"]["slots"]:
            c = named.get(k)
            if c and lc_abs(c, bg) > g["gate"]["max_lc"]:
                F("halation", "%s %s |Lc| %.1f > %.0f" % (k, c, lc_abs(c, bg), g["gate"]["max_lc"]))
        fgL = srgb_to_oklab(fg)[0]
        if fg_lc > g["target"]["fg_max_lc"] or fgL > g["target"]["fg_max_L"] or bgL < g["target"]["bg_min_L"]:
            M("halation", "fg |Lc| %.1f, fg L %.3f, bg L %.3f" % (fg_lc, fgL, bgL))

    for key in ("ansi_normal", "ansi_bright"):
        g = G[key]
        tg = g["target_" + mode]
        for i in g["slots"]:
            v = lc_abs(a[i], bg)
            cr = contrast_ratio(a[i], bg)
            if v < g["gate"]["min_lc"] or cr < g["gate"]["min_wcag"]:
                F(key, "%s %s |Lc| %.1f WCAG %.2f" % (ANSI_NAMES[i], a[i], v, cr))
            elif v < tg["min_lc"] or cr < tg["min_wcag"]:
                M(key, "%s |Lc| %.1f WCAG %.2f" % (ANSI_NAMES[i], v, cr))
            if "max_lc" in tg and v > tg["max_lc"]:
                M(key, "%s |Lc| %.1f > %.0f (hurts black-on-color)" % (ANSI_NAMES[i], v, tg["max_lc"]))
    met["min_normal_lc"] = round(min(lc_abs(a[i], bg) for i in range(1, 7)), 1)
    met["min_bright_lc"] = round(min(lc_abs(a[i], bg) for i in range(9, 15)), 1)

    g = G["bright_relation"]
    for i in range(1, 7):
        n = srgb_to_oklch(a[i])
        b = srgb_to_oklch(a[i + 8])
        if n[1] >= g["gate"]["only_if_normal_C_at_least"]:
            hd = hue_diff(n[2], b[2]) if b[2] == b[2] else 180.0
            if hd > g["gate"]["max_hue_diff"] or b[1] < g["gate"]["min_chroma_ratio"] * n[1]:
                F("bright_relation", "%s vs %s: hue diff %.0f, C %.3f vs %.3f" % (ANSI_NAMES[i + 8], ANSI_NAMES[i], hd, b[1], n[1]))
        d = delta_e_ok_rgb(a[i], a[i + 8])
        if d < g["target"]["min_dEok"]:
            M("bright_relation", "%s ~ %s (dEok %.3f)" % (ANSI_NAMES[i + 8], ANSI_NAMES[i], d))
        if mode == "dark" and b[0] - n[0] < g["target"]["dark_min_dL"]:
            M("bright_relation", "%s darker than %s (dL %.3f)" % (ANSI_NAMES[i + 8], ANSI_NAMES[i], b[0] - n[0]))
        if mode == "light" and lc_abs(a[i + 8], bg) - lc_abs(a[i], bg) < g["target"]["light_min_dLc"]:
            M("bright_relation", "%s lower contrast than %s" % (ANSI_NAMES[i + 8], ANSI_NAMES[i]))

    g = G["dim_brightBlack"]
    v8 = lc_abs(a[8], bg)
    met["brightBlack_lc"] = round(v8, 1)
    if v8 < g["gate"]["min_lc"] or v8 > fg_lc - g["gate"]["max_lc_vs_fg_gap"]:
        F("dim_brightBlack", "brightBlack %s |Lc| %.1f (need %.0f..%.1f)" % (a[8], v8, g["gate"]["min_lc"], fg_lc - g["gate"]["max_lc_vs_fg_gap"]))
    elif v8 < g["target"]["min_lc"] or v8 > g["target"]["max_lc"] or v8 > fg_lc - g["target"]["max_lc_vs_fg_gap"] \
            or contrast_ratio(a[8], bg) < g["target"]["min_wcag"]:
        M("dim_brightBlack", "brightBlack |Lc| %.1f WCAG %.2f" % (v8, contrast_ratio(a[8], bg)))

    if mode == "dark":
        g = G["grays_dark"]
        v7 = lc_abs(a[7], bg)
        v15 = lc_abs(a[15], bg)
        if v7 < g["gate"]["white_min_lc"]:
            F("grays_dark", "white %s |Lc| %.1f < %.0f" % (a[7], v7, g["gate"]["white_min_lc"]))
        if v15 < g["gate"]["brightWhite_min_lc"]:
            F("grays_dark", "brightWhite %s |Lc| %.1f < %.0f" % (a[15], v15, g["gate"]["brightWhite_min_lc"]))
        if v7 < g["target"]["white_min_lc"]:
            M("grays_dark", "white |Lc| %.1f" % v7)
        if v15 < v7:
            M("grays_dark", "brightWhite (|Lc| %.1f) dimmer than white (%.1f)" % (v15, v7))
        d0 = delta_e_ok_rgb(a[0], bg)
        dL0 = srgb_to_oklab(a[0])[0] - bgL
        if d0 < g["target"]["black_min_dEok_vs_bg"] or dL0 > g["target"]["black_max_dL_vs_bg"]:
            M("grays_dark", "black dEok vs bg %.3f, dL %.3f" % (d0, dL0))
    else:
        g = G["inks_light"]
        v0 = lc_abs(a[0], bg)
        v7 = lc_abs(a[7], bg)
        v15 = lc_abs(a[15], bg)
        if v0 < g["gate"]["black_min_lc"]:
            F("inks_light", "black %s |Lc| %.1f < %.0f" % (a[0], v0, g["gate"]["black_min_lc"]))
        if v7 < g["gate"]["white_min_lc"]:
            F("inks_light", "white %s |Lc| %.1f < %.0f (invisible white text)" % (a[7], v7, g["gate"]["white_min_lc"]))
        if v15 < g["gate"]["brightWhite_min_lc"]:
            F("inks_light", "brightWhite %s |Lc| %.1f < %.0f (invisible white text)" % (a[15], v15, g["gate"]["brightWhite_min_lc"]))
        if v0 < fg_lc:
            M("inks_light", "black |Lc| %.1f < fg %.1f" % (v0, fg_lc))
        lo, hi = g["target"]["white_lc_range"]
        if not (lo <= v7 <= hi):
            M("inks_light", "white |Lc| %.1f outside %.0f..%.0f" % (v7, lo, hi))
        if srgb_to_oklab(a[15])[0] <= srgb_to_oklab(a[7])[0]:
            M("inks_light", "brightWhite not lighter than white")

    g = G["separation"]
    for group in ((1, 2, 3, 4, 5, 6), (9, 10, 11, 12, 13, 14)):
        worst = None
        for x in range(len(group)):
            for y in range(x + 1, len(group)):
                i, j = group[x], group[y]
                d = delta_e_ok_rgb(a[i], a[j])
                if worst is None or d < worst[0]:
                    worst = (d, i, j)
                if d < g["gate"]["min_dEok"]:
                    F("separation", "%s/%s dEok %.3f" % (ANSI_NAMES[i], ANSI_NAMES[j], d))
                elif d < g["target"]["min_dEok"]:
                    M("separation", "%s/%s dEok %.3f" % (ANSI_NAMES[i], ANSI_NAMES[j], d))
                li = srgb_to_oklch(a[i])
                lj = srgb_to_oklch(a[j])
                if _hue_ok(li, g["target"]["hue_needs_C"]) and _hue_ok(lj, g["target"]["hue_needs_C"]):
                    hd = hue_diff(li[2], lj[2])
                    if hd < g["target"]["min_hue_diff"]:
                        M("separation", "%s/%s hue diff %.0f deg" % (ANSI_NAMES[i], ANSI_NAMES[j], hd))
        if group[0] == 1:
            met["min_pair_dEok"] = round(worst[0], 3)

    g = G["cvd"]
    cvd_min = {}
    for pname, (i, j) in g["pairs"].items():
        for k in g["types"]:
            d = delta_e_ok_rgb(simulate_cvd(a[i], k), simulate_cvd(a[j], k))
            cvd_min[pname] = min(cvd_min.get(pname, 9.0), d)
            if d < g["gate"][pname]:
                F("cvd", "%s under %s dEok %.3f < %.2f" % (pname, k, d, g["gate"][pname]))
    for pname, (i, j) in g["pairs"].items():
        for k in g["target_types"]:
            if k in g["types"]:
                continue
            d = delta_e_ok_rgb(simulate_cvd(a[i], k), simulate_cvd(a[j], k))
            if d < g["target"]["tritan_all_pairs"]:
                M("cvd", "%s under %s dEok %.3f" % (pname, k, d))
    met["cvd_red_green_min"] = round(cvd_min["red/green"], 3)
    if cvd_min["red/green"] < g["target"]["red/green"]:
        M("cvd", "red/green worst-case dEok %.3f" % cvd_min["red/green"])
    dl = abs(srgb_to_oklab(a[1])[0] - srgb_to_oklab(a[2])[0])
    if dl < g["target"]["red_green_min_dL"]:
        M("cvd", "red/green lightness gap %.3f" % dl)

    sel = theme.get("selection_background")
    g = G["selection"]
    if sel:
        cr = contrast_ratio(fg, sel)
        v = lc_abs(fg, sel)
        d = delta_e_ok_rgb(sel, bg)
        amin = min(lc_abs(a[i], sel) for i in list(range(1, 7)) + list(range(9, 15)))
        met["fg_on_sel_lc"] = round(v, 1)
        met["sel_dEok"] = round(d, 3)
        met["ansi_on_sel_min_lc"] = round(amin, 1)
        if cr < g["gate"]["fg_min_wcag"] or v < g["gate"]["fg_min_lc"]:
            F("selection", "fg on selection %s: WCAG %.2f |Lc| %.1f" % (sel, cr, v))
        elif v < g["target"]["fg_min_lc"]:
            M("selection", "fg on selection |Lc| %.1f" % v)
        if d < g["gate"]["sel_min_dEok_vs_bg"]:
            F("selection", "selection vs bg dEok %.3f" % d)
        elif not (g["target"]["sel_dEok_vs_bg_range"][0] <= d <= g["target"]["sel_dEok_vs_bg_range"][1]):
            M("selection", "selection vs bg dEok %.3f" % d)
        if amin < g["gate"]["ansi_min_lc"]:
            F("selection", "weakest chromatic ANSI on selection |Lc| %.1f" % amin)
        elif amin < g["target"]["ansi_min_lc"]:
            M("selection", "weakest chromatic ANSI on selection |Lc| %.1f" % amin)
    else:
        M("selection", "no SelectionColor (Terminal default)")

    cur = theme.get("cursor")
    g = G["cursor"]
    if cur:
        cr = contrast_ratio(cur, bg)
        met["cursor_wcag"] = round(cr, 2)
        if cr < g["gate"]["min_wcag"]:
            F("cursor", "cursor %s WCAG %.2f" % (cur, cr))
        elif cr < g["target"]["min_wcag"] or lc_abs(cur, bg) < g["target"]["min_lc"]:
            M("cursor", "cursor WCAG %.2f |Lc| %.1f" % (cr, lc_abs(cur, bg)))
    else:
        M("cursor", "no CursorColor (Terminal default)")

    bold = theme.get("bold")
    if bold:
        g = G["bold"]
        if lc_abs(bold, bg) < fg_lc - g["gate"]["max_lc_drop_vs_fg"]:
            F("bold", "bold %s |Lc| %.1f < fg %.1f" % (bold, lc_abs(bold, bg), fg_lc))
        if delta_e_ok_rgb(bold, fg) > g["target"]["max_dEok_vs_fg"]:
            M("bold", "bold differs from fg (dEok %.3f)" % delta_e_ok_rgb(bold, fg))

    g = G["text_on_color"]
    for i in g["gate"]["black_on"]:
        v = lc_abs(a[0], a[i])
        if v < g["gate"]["min_lc"]:
            F("text_on_color", "black text on %s |Lc| %.1f" % (ANSI_NAMES[i], v))
    for i in range(1, 7):
        best = max(lc_abs(a[0], a[i]), lc_abs(a[7], a[i]), lc_abs(a[15], a[i]))
        if best < g["target"]["best_of_black_white_min_lc"][mode]:
            M("text_on_color", "best of black/white/brightWhite on %s |Lc| %.1f" % (ANSI_NAMES[i], best))
    if lc_abs(a[0], a[1]) < g["target"]["black_on_red_min_lc"]:
        M("text_on_color", "black on red |Lc| %.1f" % lc_abs(a[0], a[1]))
    met["black_on_green_cyan_yellow_min_lc"] = round(min(lc_abs(a[0], a[i]) for i in (2, 3, 6)), 1)

    g = G["faint_text"]
    sfx = "_dark" if mode == "dark" else ""
    ffg = faint(fg, bg)
    v = lc_abs(ffg, bg)
    met["faint_fg_lc"] = round(v, 1)
    if v < g["gate"]["fg_min_lc" + sfx]:
        F("faint_text", "faint foreground %s -> %s |Lc| %.1f < %.0f" % (fg, ffg, v, g["gate"]["fg_min_lc" + sfx]))
    elif v < g["target"]["fg_min_lc" + sfx]:
        M("faint_text", "faint foreground |Lc| %.1f < %.0f" % (v, g["target"]["fg_min_lc" + sfx]))
    fmin = None
    for i in g["slots"]:
        fc = faint(a[i], bg)
        v = lc_abs(fc, bg)
        fmin = v if fmin is None else min(fmin, v)
        if v < g["gate"]["ansi_min_lc"]:
            F("faint_text", "faint %s %s -> %s |Lc| %.1f < %.0f" % (ANSI_NAMES[i], a[i], fc, v, g["gate"]["ansi_min_lc"]))
    met["faint_ansi_min_lc"] = round(fmin, 1)
    if g["gate"]["ansi_min_lc"] <= fmin < g["target"].get("ansi_min_lc", 0.0):
        M("faint_text", "weakest faint hue color |Lc| %.1f < %.0f" % (fmin, g["target"]["ansi_min_lc"]))

    alpha = theme.get("background_alpha")
    alpha = 1.0 if alpha is None else float(alpha)
    if alpha < 1.0:
        tr = {"alpha": alpha, "desktops": []}
        for desk, comp in translucent_backgrounds(bg, alpha, G):
            sub = dict(theme, background=comp, background_alpha=1.0, mode=mode)
            r = check_theme(sub, G)
            for f in r["failures"]:
                fails.append({"id": f["id"], "detail": "%s [desktop %s, bg %s]" % (f["detail"], desk, comp), "desktop": desk})
            row = {"desktop": desk, "background": comp, "pass": r["pass"]}
            row.update(r["metrics"])
            tr["desktops"].append(row)
        met["translucency"] = tr

    return {"name": theme.get("name"), "mode": mode, "pass": not fails,
            "failed_gate_ids": sorted(set(f["id"] for f in fails)),
            "failures": fails, "misses": misses, "metrics": met}
