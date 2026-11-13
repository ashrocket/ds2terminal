"""fonts.py (from research fontfind.py) - pure-stdlib (Python >= 3.9) finder for installed fonts and their
PostScript names, with a monospace verdict suitable for Terminal.app.

Reads only the sfnt tables it needs (name, post, OS/2, hhea, hmtx, cmap, fvar)
with seek(), so huge files (emoji, CJK collections) cost little.

usage: python3 -I fontfind.py [--all] [--json] [--find SUBSTRING] [--include-hidden]
       default: list monospace faces only.
"""
import json
import os
import struct
import sys
import time

FONT_DIRS = [
    "/System/Applications/Utilities/Terminal.app/Contents/Resources/Fonts",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
]
EXTS = (".ttf", ".otf", ".ttc", ".otc")


def _u16(b, o):
    return struct.unpack(">H", b[o:o + 2])[0]


def _u32(b, o):
    return struct.unpack(">I", b[o:o + 4])[0]


class Face(object):
    def __init__(self, f, base):
        self.f = f
        f.seek(base)
        hdr = f.read(12)
        self.ok = len(hdr) == 12 and hdr[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true")
        self.tables = {}
        if not self.ok:
            return
        n = _u16(hdr, 4)
        d = f.read(16 * n)
        for i in range(n):
            tag, _, off, ln = struct.unpack(">4sIII", d[16 * i:16 * i + 16])
            self.tables[tag.decode("latin-1")] = (off, ln)

    def table(self, tag, maxlen=None):
        if tag not in self.tables:
            return None
        off, ln = self.tables[tag]
        self.f.seek(off)
        return self.f.read(ln if maxlen is None else min(ln, maxlen))


def _names(t):
    out = {}
    if not t or len(t) < 6:
        return out
    count, soff = _u16(t, 2), _u16(t, 4)
    best = {}
    for i in range(count):
        p, e, l, nid, ln, off = struct.unpack(">6H", t[6 + 12 * i:18 + 12 * i])
        raw = t[soff + off:soff + off + ln]
        if p == 3 and e in (1, 10):
            rank = 0 if l == 0x409 else 1
            s = raw.decode("utf-16-be", "replace")
        elif p == 0:
            rank, s = 2, raw.decode("utf-16-be", "replace")
        elif p == 1 and e == 0:
            rank = 3 if l == 0 else 4
            s = raw.decode("mac_roman", "replace")
        else:
            continue
        if nid not in best or rank < best[nid][0]:
            best[nid] = (rank, s)
    for nid, (_, s) in best.items():
        out[nid] = s
    return out


def _cmap_lookup(t, codes):
    """Return {codepoint: glyphId} using cmap format 4 or 12 (Unicode subtables)."""
    if not t:
        return {}
    n = _u16(t, 2)
    subs = {}
    for i in range(n):
        p, e, off = struct.unpack(">HHI", t[4 + 8 * i:12 + 8 * i])
        subs[(p, e)] = off
    for key in ((3, 10), (0, 4), (3, 1), (0, 3), (0, 1), (0, 0)):
        if key not in subs:
            continue
        o = subs[key]
        fmt = _u16(t, o)
        res = {}
        if fmt == 4:
            segx2 = _u16(t, o + 6)
            ends = o + 14
            starts = ends + segx2 + 2
            deltas = starts + segx2
            ranges = deltas + segx2
            for c in codes:
                for s in range(segx2 // 2):
                    end = _u16(t, ends + 2 * s)
                    if c <= end:
                        start = _u16(t, starts + 2 * s)
                        if c < start:
                            break
                        delta = _u16(t, deltas + 2 * s)
                        ro = _u16(t, ranges + 2 * s)
                        if ro == 0:
                            g = (c + delta) & 0xFFFF
                        else:
                            ga = ranges + 2 * s + ro + 2 * (c - start)
                            g = _u16(t, ga)
                            if g:
                                g = (g + delta) & 0xFFFF
                        if g:
                            res[c] = g
                        break
            return res
        if fmt == 12:
            ng = _u32(t, o + 12)
            groups = [struct.unpack(">III", t[o + 16 + 12 * i:o + 28 + 12 * i]) for i in range(ng)]
            for c in codes:
                for s, e, g0 in groups:
                    if s <= c <= e:
                        res[c] = g0 + (c - s)
                        break
            return res
    return {}


def _ascii_advances(face):
    hhea = face.table("hhea", 36)
    if not hhea or "hmtx" not in face.tables:
        return None
    nh = _u16(hhea, 34)
    cmap = face.table("cmap")
    gids = _cmap_lookup(cmap, range(0x21, 0x7F))
    if len(gids) < 60:
        return None
    off, ln = face.tables["hmtx"]
    adv = set()
    for g in gids.values():
        idx = min(g, nh - 1)
        face.f.seek(off + 4 * idx)
        adv.add(_u16(face.f.read(2), 0))
    return sorted(adv)


def _fvar_instances(face, names_t):
    t = face.table("fvar")
    if not t:
        return []
    axoff, axcount, axsize, icount, isize = _u16(t, 4), _u16(t, 8), _u16(t, 10), _u16(t, 12), _u16(t, 14)
    base = axoff + axcount * axsize
    out = []
    for i in range(icount):
        o = base + i * isize
        sub = _u16(t, o)
        ps = _u16(t, o + 4 + 4 * axcount) if isize >= 6 + 4 * axcount else None
        out.append((names_t.get(sub), names_t.get(ps) if ps else None))
    return out


def faces_in(path):
    with open(path, "rb") as f:
        head = f.read(12)
        if head[:4] == b"ttcf":
            n = _u32(head, 8)
            offs = list(struct.unpack(">%dI" % n, f.read(4 * n)))
        else:
            offs = [0]
        for idx, base in enumerate(offs):
            face = Face(f, base)
            if not face.ok:
                continue
            names = _names(face.table("name"))
            post = face.table("post", 16)
            fixed = bool(post and len(post) >= 16 and _u32(post, 12) != 0)
            os2 = face.table("OS/2", 42)
            panose_mono = bool(os2 and len(os2) >= 42 and os2[32] == 2 and os2[35] == 9)
            adv = _ascii_advances(face)
            ascii_equal = bool(adv) and len(adv) == 1
            rec = {
                "path": path, "index": idx,
                "family": names.get(16) or names.get(1),
                "style": names.get(17) or names.get(2),
                "postscript": names.get(6),
                "full": names.get(4),
                "post_isFixedPitch": fixed, "panose_monospaced": panose_mono,
                "ascii_advances_equal": ascii_equal,
                # cell-grid verdict: printable ASCII all share one advance
                "is_monospace": ascii_equal if adv is not None else (fixed or panose_mono),
                "hidden": bool(names.get(6, "").startswith(".") or (names.get(1) or "").startswith(".")),
            }
            inst = _fvar_instances(face, names)
            if inst:
                rec["named_instances"] = [{"style": s, "postscript": p} for s, p in inst]
            yield rec


def scan(dirs=None):
    out = []
    for d in dirs or FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith(EXTS):
                continue
            p = os.path.join(d, name)
            try:
                out.extend(faces_in(p))
            except (OSError, struct.error, IndexError, ValueError) as e:
                out.append({"path": p, "error": str(e)})
    return out


# Generic CSS names and Apple names that map to the SF Mono face bundled in Terminal.app.
SF_MONO_ALIASES = {"ui-monospace", "sf mono", "sfmono", "sfmono-regular", "sf mono terminal",
                   "sfmonoterminal-regular", "-apple-system-monospace"}
GENERIC_FAMILIES = {"monospace", "ui-monospace", "system-ui", "sans-serif", "serif", "cursive", "fantasy",
                    "emoji", "math", "fangsong", "inherit", "initial", "unset"}
DEFAULT_FONT = "SFMonoTerminal-Regular"

_scan_cache = []


def _faces():
    if not _scan_cache:
        _scan_cache.append(scan())
    return _scan_cache[0]


def _regular_score(style):
    s = (style or "").lower()
    if s in ("regular", "book", "roman", "normal", "medium"):
        return 0 if s in ("regular", "book", "roman", "normal") else 1
    return 5 + len(s)


def find_postscript(name):
    """Return the installed PostScript name for a family or PostScript name, or None.
    Only monospace faces count. Regular style wins."""
    want = name.strip().strip("\"'").lower()
    best = None
    for r in _faces():
        if "error" in r or r.get("hidden") or not r.get("is_monospace"):
            continue
        cands = [(r.get("postscript"), r.get("family"), r.get("style"))]
        for inst in r.get("named_instances") or []:
            cands.append((inst.get("postscript"), r.get("family"), inst.get("style")))
        for ps, fam, style in cands:
            if not ps:
                continue
            if ps.lower() == want:
                return ps
            if (fam or "").lower() == want:
                sc = _regular_score(style)
                if best is None or sc < best[0]:
                    best = (sc, ps)
    return best[1] if best else None


def font_dirs_present():
    return any(os.path.isdir(d) for d in FONT_DIRS)


def resolve_font(requested=None, families=None):
    """Pick the Terminal font. Returns (postscript_name, note).

    requested: the --font value (a PostScript or family name), or None.
    families: monospace families from the design system, in order of preference.
    When no font folder exists (Linux), a requested name is kept as given, and design-system
    families are not used, because they cannot be checked.
    """
    have_dirs = font_dirs_present()
    if requested:
        low = requested.strip().lower()
        if low in SF_MONO_ALIASES:
            return DEFAULT_FONT, "requested %s: uses SF Mono Terminal (bundled in Terminal.app)" % requested
        if not have_dirs:
            return requested, "requested %s: kept as given (no font folders on this computer to check it)" % requested
        ps = find_postscript(requested)
        if ps:
            return ps, "requested %s: found %s" % (requested, ps)
        return DEFAULT_FONT, "requested %s: not installed as a monospace font; uses %s" % (requested, DEFAULT_FONT)
    for fam in families or []:
        low = fam.strip().strip("\"'").lower()
        if low in SF_MONO_ALIASES:
            return DEFAULT_FONT, "design system font %s: uses SF Mono Terminal" % fam
        if low in GENERIC_FAMILIES or not have_dirs:
            continue
        ps = find_postscript(fam)
        if ps:
            return ps, "design system font %s: found %s" % (fam, ps)
    return DEFAULT_FONT, "default font %s (bundled in Terminal.app)" % DEFAULT_FONT


def main(argv):
    t0 = time.perf_counter()
    recs = scan()
    dt = time.perf_counter() - t0
    show_all = "--all" in argv
    hidden = "--include-hidden" in argv
    find = argv[argv.index("--find") + 1].lower() if "--find" in argv else None
    sel = []
    for r in recs:
        if "error" in r:
            continue
        if not hidden and r["hidden"]:
            continue
        if not show_all and not r["is_monospace"]:
            continue
        if find and find not in " ".join(str(r.get(k) or "") for k in ("family", "postscript", "full")).lower():
            continue
        sel.append(r)
    if "--json" in argv:
        print(json.dumps({"seconds": dt, "faces_scanned": len(recs), "results": sel}, indent=1))
    else:
        for r in sel:
            extra = ""
            if r.get("named_instances"):
                extra = " instances=" + ",".join(str(i["postscript"]) for i in r["named_instances"][:6])
            print("%-28s %-14s %-36s mono=%-5s fixed=%-5s panose=%-5s ascii=%-5s %s%s" % (
                r["family"], r["style"], r["postscript"], r["is_monospace"], r["post_isFixedPitch"],
                r["panose_monospaced"], r["ascii_advances_equal"], os.path.basename(r["path"]), extra))
        errs = [r for r in recs if "error" in r]
        print("# scanned %d faces in %.3f s; %d shown; %d errors" % (len(recs), dt, len(sel), len(errs)))
        for e in errs:
            print("#  error", e["path"], e["error"])


if __name__ == "__main__":
    main(sys.argv[1:])
