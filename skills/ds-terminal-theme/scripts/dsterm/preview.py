"""preview.py - preview.html: each theme drawn as a terminal window with typical program output."""
import html
from typing import List

from . import claudecode as CC
from . import colorlab as cl


def _span(text: str, fg: str = None, bg: str = None, bold: bool = False, cls: str = "") -> str:
    st = []
    if fg:
        st.append("color:%s" % fg)
    if bg:
        st.append("background:%s" % bg)
    if bold:
        st.append("font-weight:700")
    c = ' class="%s"' % cls if cls else ""
    return '<span%s style="%s">%s</span>' % (c, ";".join(st), html.escape(text))


def terminal_block(rec: dict) -> str:
    s = {r["slot"]: r["hex"] for r in rec["slots"]}
    a = [s[n] for n in cl.ANSI_NAMES]
    bg, fg = s["background"], s["foreground"]
    B, R, G, Y, U, M, C, W = a[:8]
    K, BR, BG, BY, BU, BM, BC, BW = a[8:]
    lines: List[str] = []
    P = lines.append
    P(_span("ash@mac", G, bold=True) + _span(":", fg) + _span("~/project", U, bold=True) + _span(" (main)", M) + _span(" $ ", fg)
      + _span("ls -la"))
    P(_span("drwxr-xr-x  ", fg) + _span("src", U, bold=True) + _span("   ", fg) + _span("build.sh", G, bold=True)
      + _span("   ", fg) + _span("link", M) + _span("   README.md", fg) + _span("   ", fg) + _span("sticky", B, Y))
    P(_span("$ ", fg) + _span("git diff", fg))
    P(_span("diff --git a/app.py b/app.py", s["bold"], bold=True))
    P(_span("@@ -12,7 +12,8 @@ def main():", C))
    P(_span("-    total = price * qty", R))
    P(_span("+    total = round(price * qty, 2)", G))
    P(_span("commit 3f1f428 ", Y) + _span("(HEAD -> main)", fg))
    P(_span("$ ", fg) + _span("make", fg))
    P(_span("app.c:42:7: ", s["bold"], bold=True) + _span("error: ", R, bold=True) + _span("use of undeclared identifier 'x'", s["bold"], bold=True))
    P(_span("app.c:51:3: ", s["bold"], bold=True) + _span("warning: ", M, bold=True) + _span("unused variable 'tmp'", s["bold"], bold=True))
    P(_span("app.c:51:3: ", s["bold"], bold=True) + _span("note: ", C, bold=True) + _span("declared here", fg))
    P(_span("  1  [", fg) + _span("|||||||||", G) + _span("|||", R) + _span("        42.0%", fg) + _span("]", fg))
    P(_span(" PID USER      CPU%  Command ", B, G))
    P(_span(" 812 ash       12.0  python3 ", B, C) + _span(" F1", fg) + _span("Help ", B, C) + _span(" F10", fg) + _span("Quit", B, C))
    P(_span("$ ", fg) + _span("git commi", fg) + _span("t -m \"fix\"", K) + _span("   # brightBlack: suggestions, comments", K))
    P(_span("selected text on the selection color, with ", fg, s["selection"]) + _span("red", R, s["selection"])
      + _span(" ", fg, s["selection"]) + _span("green", G, s["selection"]) + _span(" ", fg, s["selection"])
      + _span("blue", U, s["selection"]))
    P(_span("bold text", s["bold"], bold=True) + _span("  normal text  ", fg) + _span("white", W) + _span("  brightWhite", BW)
      + _span("  ", fg) + _span("Y", BY) + _span("G", BG) + _span("U", BU)
      + _span("  cursor:", fg) + _span(" ", bg, s["cursor"]))
    def fa(c):
        return cl.faint(c, bg)

    P(_span("faint (SGR 2): ", fa(fg)) + _span("text ", fa(fg)) + _span("red ", fa(R)) + _span("green ", fa(G))
      + _span("yellow ", fa(Y)) + _span("blue ", fa(U)) + _span("magenta ", fa(M)) + _span("cyan ", fa(C))
      + _span("brightRed ", fa(BR)) + _span("brightBlue", fa(BU)))
    for kind in ("ansi", "standard"):
        lines.append("")
        lines.extend(CC.preview_lines(rec, kind, _span))
    sw = []
    for row in (range(0, 8), range(8, 16)):
        cells = []
        for i in row:
            r = rec["slots"][5 + i]
            tc = "#000" if cl.lc_abs("#000000", r["hex"]) > cl.lc_abs("#ffffff", r["hex"]) else "#fff"
            cells.append('<div class="sw" style="background:%s;color:%s" title="%s %s">%d<br>%s</div>'
                         % (r["hex"], tc, html.escape(r["slot"]), html.escape(r["source"]), i, r["hex"]))
        sw.append('<div class="swrow">%s</div>' % "".join(cells))
    status = "all hard gates pass" if rec["pass"] else "FAIL: " + ", ".join(rec["failed_gates"])
    return ('<section><h2>%s <small>%s%s, %s</small></h2>'
            '<pre class="term" style="background:%s;color:%s">%s</pre>%s</section>'
            % (html.escape(rec["file"]), rec["mode"], " (derived)" if rec["derived"] else "", html.escape(status),
               bg, fg, "\n".join(lines), "".join(sw)))


def render(data: dict) -> str:
    body = "".join(terminal_block(t) for t in data["themes"])
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s Terminal Preview</title>
<style>
:root { --page:#f4f4f5; --ink:#18181b; }
@media (prefers-color-scheme: dark) { :root { --page:#18181b; --ink:#f4f4f5; } }
body { margin:0; padding:16px; background:var(--page); color:var(--ink);
       font:14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
section { max-width:900px; margin:0 auto 32px; }
h1 { max-width:900px; margin:0 auto 16px; font-size:20px; }
h2 { font-size:16px; } small { font-weight:400; opacity:.75; }
.term { font:13px/1.35 "SF Mono", ui-monospace, Menlo, monospace; padding:12px 14px; border-radius:8px;
        overflow-x:auto; white-space:pre; border:1px solid rgba(128,128,128,.45); }
.swrow { display:flex; flex-wrap:wrap; gap:4px; margin-top:4px; }
.sw { flex:1 1 90px; min-width:70px; padding:6px; border-radius:4px; font:11px/1.3 ui-monospace, Menlo, monospace; }
</style></head><body>
<h1>%s: Terminal themes</h1>
%s
<p style="max-width:900px;margin:0 auto 8px">Faint (SGR 2) samples use the measured Terminal blend (<code>colorlab.DIM_BLEND</code>, <code>colorlab.DIM_POWER</code>). The two Claude Code samples use the theme tables of Claude Code 2.1.323. The ANSI theme draws the text color on ANSI green and red cells for diff lines. The standard theme uses its own colors on the background of this theme. The report gives the contrast of each pair and the theme to use.</p>
<p style="max-width:900px;margin:0 auto">The browser draws this preview; Terminal.app can render text a little differently.
Run <code>scripts/demo.py</code> in a Terminal window that uses the theme to see the real colors.</p>
</body></html>
""" % (html.escape(data["name"]), html.escape(data["name"]), body)
