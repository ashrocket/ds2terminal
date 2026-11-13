#!/usr/bin/env python3
"""ds2terminal.py - convert a design system into Apple Terminal (.terminal) themes.

Usage:
  python3 -I ds2terminal.py SOURCE [SOURCE ...] [--name NAME] [--modes auto|light|dark|both]
         [--out DIR] [--font NAME] [--font-size 13] [--cursor block|underline|bar] [--cursor-blink]
         [--set ROLE=HEX ...] [--prefer-token ROLE=TOKEN ...] [--all-tokens] [--source-mode ID]
         [--no-chroma-floor] [--translucent ALPHA] [--report json|md|both] [--no-preview] [--columns N] [--rows N]
         [--cache DIR] [--timeout S] [--quiet]

SOURCE is a local file or folder (tokens.json, tokens.css, DTCG, Style Dictionary, Tokens Studio,
Figma variables export, CSS, SCSS, ...) or a public URL (GitHub, npm, unpkg, jsDelivr, a raw file,
or a docs page with linked CSS). Links that need a sign-in (claude.ai, Figma, Pidgin) stop with
exit code 2 and say which tool fetches the files.

Writes to DIR (default ./out/<name>): "<Name> Light.terminal", "<Name> Dark.terminal",
report.md, report.json and preview.html.

Exit codes: 0 every hard gate passes; 1 a gate still fails after repair; 2 bad input.
Stdlib only, Python 3.9 or later. Run it with -I.
"""
import argparse
import os
import re
import sys
import urllib.parse

# `python3 -I` does not put the script folder on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dsterm import __version__  # noqa: E402
from dsterm import fetch as F  # noqa: E402
from dsterm import fonts as FONTS  # noqa: E402
from dsterm import normalize as N  # noqa: E402
from dsterm import preview as PV  # noqa: E402
from dsterm import report as RP  # noqa: E402
from dsterm import roles as R  # noqa: E402
from dsterm import terminal as TERM  # noqa: E402
from dsterm import theme as TH  # noqa: E402


class InputError(Exception):
    pass


def collect_sources(sources, cache, timeout, log):
    """Return (paths, displays, names, notes) for normalize. URLs go through fetch.discover."""
    paths, displays, names, notes = [], {}, [], []
    for i, src in enumerate(sources):
        if os.path.exists(src):
            p = os.path.abspath(src)
            if os.path.isfile(p):
                paths.append(p)
                displays[p] = os.path.basename(p)
                names.append(re.sub(r"(\.tokens)?\.(json5?|css|scss|less|js|ts|xml)$", "", os.path.basename(p), flags=re.I))
                continue
            if os.path.isdir(p):
                # normalize walks the folder. It keeps the path of each file below the folder, because a
                # folder name can be a mode (themes/g10/theme.json, themes/g100/theme.json).
                if not any(True for _x in N.iter_inputs([p])):
                    raise InputError("%s: no token files in this folder" % src)
                paths.append(p)
                stem = os.path.basename(p.rstrip(os.sep))
                if stem and stem.lower() not in ("tokens", "design-system", "project", "src", "dist", "files"):
                    names.append(stem)
                continue
        if "://" not in src and not src.startswith("npm:") and (src.startswith(("/", ".", "~")) or os.sep in src):
            raise InputError("%s: file or folder not found" % src)
        cls = F.classify(src)
        if cls.get("needs_tool"):
            raise InputError("%s needs a signed-in tool (%s). Fetch the files with: %s. Then pass the local folder."
                             % (src, cls["class"], cls["needs_tool"]))
        outdir = os.path.join(cache, "src%d" % i)
        log("fetching %s ..." % src)
        man = F.discover(src, outdir, timeout=timeout)
        if man.get("errors"):
            notes.extend("%s: %s" % (src, e) for e in man["errors"])
        chosen = [c for c in man.get("chosen", []) if c.get("local")]
        if not chosen:
            raise InputError("%s: no color token files found (%s)" % (src, "; ".join(man.get("errors") or ["empty"])))
        for c in chosen:
            paths.append(c["local"])
            disp = c.get("display") or os.path.basename(c["local"])
            if "/" not in disp and str(c.get("url", "")).startswith("http"):
                # keep the folder names of a raw file URL: normalize reads modes from them (themes/g100/x.json)
                disp = urllib.parse.urlparse(c["url"]).path.lstrip("/")
            displays[c["local"]] = disp
        if man.get("name"):
            names.append(str(man["name"]).split("/")[-1])
        else:
            stem = os.path.basename(urllib.parse.urlparse(src).path.rstrip("/"))
            stem = re.sub(r"(\.tokens)?\.(json5?|css|scss|less|js|ts|xml|html?)$", "", stem, flags=re.I)
            if stem and stem.lower() not in ("tokens", "index", "colors", "theme", "palette"):
                names.append(stem)
            elif urllib.parse.urlparse(src).hostname:
                names.append(urllib.parse.urlparse(src).hostname.split(".")[-2] if "." in urllib.parse.urlparse(src).hostname else urllib.parse.urlparse(src).hostname)
        notes.append("%s: used %s" % (src, ", ".join(c.get("display") or c["local"] for c in chosen)))
    return paths, displays, names, notes


def nice_name(s):
    s = re.sub(r"[-_.]+", " ", str(s)).strip()
    return s[:1].upper() + s[1:] if s else "Design System"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert a design system into Apple Terminal themes.")
    ap.add_argument("sources", nargs="+", metavar="SOURCE")
    ap.add_argument("--name")
    ap.add_argument("--modes", choices=("auto", "light", "dark", "both"), default="auto")
    ap.add_argument("--out")
    ap.add_argument("--font", help="PostScript or family name (default: the design system's mono font, else SF Mono Terminal)")
    ap.add_argument("--font-size", type=float, default=13.0)
    ap.add_argument("--cursor", choices=("block", "underline", "bar"), default="block")
    ap.add_argument("--cursor-blink", action="store_true")
    ap.add_argument("--set", action="append", metavar="ROLE=HEX", default=[],
                    help="force a color: bg, fg, bold, cursor, selection, black..brightWhite or 0..15")
    ap.add_argument("--prefer-token", action="append", metavar="ROLE=TOKEN", default=[],
                    help="use this token for bg, fg, brand, red, green, yellow, blue, magenta or cyan")
    ap.add_argument("--all-tokens", action="store_true", help="keep raw tokens that no semantic token uses")
    ap.add_argument("--source-mode", help="use only this mode id of the design system")
    ap.add_argument("--no-chroma-floor", action="store_true", help="keep pastel reds/greens pastel in dark mode")
    ap.add_argument("--translucent", type=float, metavar="ALPHA",
                    help="background alpha below 1 (default: opaque). Every gate must then pass over a black and a white desktop")
    ap.add_argument("--report", choices=("json", "md", "both"), default="both")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--columns", type=int)
    ap.add_argument("--rows", type=int)
    ap.add_argument("--cache", help="folder for fetched files (default: OUT/.fetch)")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    def log(msg):
        if not a.quiet:
            print(msg, file=sys.stderr)

    try:
        sets = TH.parse_pairs(a.set, "--set")
        for role, val in sets:
            TH.slot_key(role)
            TH.parse_hex(val)
        prefer_pairs = TH.parse_pairs(a.prefer_token, "--prefer-token")
        if not (6 <= a.font_size <= 72):
            raise InputError("--font-size must be between 6 and 72")
        if a.columns is not None and not (20 <= a.columns <= 1000):
            raise InputError("--columns must be between 20 and 1000")
        if a.rows is not None and not (5 <= a.rows <= 500):
            raise InputError("--rows must be between 5 and 500")
        alpha = 1.0 if a.translucent is None else a.translucent
        if not (0.05 <= alpha <= 1.0):
            raise InputError("--translucent must be between 0.05 and 1")
        dup = sorted(set(str(TH.slot_key(r)) for r, _ in sets if [str(TH.slot_key(x)) for x, _ in sets].count(str(TH.slot_key(r))) > 1))
        out = a.out or os.path.join("out", re.sub(r"[^A-Za-z0-9._-]+", "-", a.name or "theme").strip("-").lower() or "theme")
        cache = a.cache or os.path.join(out, ".fetch")
        os.makedirs(out, exist_ok=True)
        paths, displays, names, notes = collect_sources(a.sources, cache, a.timeout, log)
        ir = N.normalize_paths(paths, source={"input": a.sources}, name=a.name, displays=displays)
        name = a.name or ir.get("name") or (names[0] if names else "Design System")
        if not a.name:
            name = nice_name(name)
        name = TERM.cap_name(name)
        pals, pnotes = R.extract(ir, keep_all=a.all_tokens, source_mode=a.source_mode)
        notes += pnotes + list(ir.get("notes") or []) + list(ir.get("warnings") or [])
        if dup:
            notes.append("warning: --set gives %s more than once; the last value is used" % ", ".join(dup))
        if not pals:
            raise InputError("no usable color tokens in %s: %s" % (", ".join(a.sources), "; ".join(pnotes)))
        all_tokens = []
        for p in pals.values():
            all_tokens += p.tokens + p.ignored
        kinds = ["light", "dark"] if a.modes in ("auto", "both") else [a.modes]
        font_ps, font_note = FONTS.resolve_font(a.font, (ir.get("fonts") or {}).get("mono"))
        themes = []
        any_fail = False
        for kind in kinds:
            derived = kind not in pals
            pal = pals.get(kind) or pals.get("light") or pals.get("dark")
            prefer = TH.resolve_prefer(pal, prefer_pairs, all_tokens)
            th = TH.build(pal, kind, derived, prefer=prefer, sets=sets, chroma_floor=not a.no_chroma_floor,
                          alpha=alpha)
            pname = "%s %s" % (name, kind.capitalize())
            fname = TERM.safe_filename(pname)
            prof = TERM.build_profile(pname, TH.terminal_colors(th["slots"]), font=(font_ps, a.font_size),
                                      cursor=a.cursor, cursor_blink=a.cursor_blink, columns=a.columns, rows=a.rows,
                                      background_alpha=alpha)
            TERM.write_profile(os.path.join(out, fname), prof)
            rec = RP.theme_record(pname, fname, th)
            rec["source_mode"] = pal.source_mode
            themes.append(rec)
            any_fail = any_fail or not rec["pass"]
            log("%s: %s%s" % (fname, "all hard gates pass" if rec["pass"] else "FAIL " + ", ".join(rec["failed_gates"]),
                              " (derived)" if derived else ""))
        ignored = sorted(set(t.name for p in pals.values() for t in p.ignored))
        data = {"name": name, "version": __version__, "sources": list(a.sources), "themes": themes,
                "font": {"postscript": font_ps, "size": a.font_size, "note": font_note},
                "notes": notes, "ignored_tokens": ignored,
                "icc": "embedded" if TERM.srgb_icc_bytes() else "not embedded (no sRGB Profile.icc on this computer; NSID 7 only)"}
        if a.report in ("json", "both"):
            RP.write_json(os.path.join(out, "report.json"), data)
        if a.report in ("md", "both"):
            with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
                f.write(RP.to_markdown(data))
        if not a.no_preview:
            with open(os.path.join(out, "preview.html"), "w", encoding="utf-8") as f:
                f.write(PV.render(data))
        log("wrote %s" % os.path.abspath(out))
        return 1 if any_fail else 0
    except (InputError, TH.OverrideError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 2
    except (OSError, UnicodeError, RecursionError) as ex:
        print("error: %s: %s" % (type(ex).__name__, ex), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
