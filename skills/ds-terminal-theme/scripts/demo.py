#!/usr/bin/env python3
"""demo.py - print sample terminal output in the 16 ANSI colors.

Run it in a Terminal window that uses a theme:  python3 -I demo.py
It only prints text. It uses the theme's palette (SGR 30-37, 40-47, 90-97), not 24-bit color.
"""
import sys

NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")
E = "\033["


def c(code, text):
    return "%s%sm%s%s0m" % (E, code, text, E)


def main():
    out = []
    P = out.append
    P(c("1", "16 ANSI colors as text (normal, then bright) and as backgrounds"))
    P(" ".join(c(str(30 + i), "%-8s" % n) for i, n in enumerate(NAMES)))
    P(" ".join(c(str(90 + i), "%-8s" % n) for i, n in enumerate(NAMES)))
    P(" ".join(c("30;%d" % (40 + i), " %-7s" % n) for i, n in enumerate(NAMES)))
    P(" ".join(c("97;%d" % (40 + i), " %-7s" % n) for i, n in enumerate(NAMES)))
    P("")
    P(c("1;32", "ash@mac") + ":" + c("1;34", "~/project") + c("35", " (main)") + " $ ls -la")
    P("drwxr-xr-x  " + c("1;34", "src") + "   " + c("1;32", "build.sh") + "   " + c("35", "link") + "   README.md   "
      + c("30;43", "sticky") + "   " + c("30;42", "other-writable"))
    P("$ git diff")
    P(c("1", "diff --git a/app.py b/app.py"))
    P(c("36", "@@ -12,7 +12,8 @@ def main():"))
    P(c("31", "-    total = price * qty"))
    P(c("32", "+    total = round(price * qty, 2)") + c("41", "  "))
    P(c("33", "commit 3f1f428") + " (HEAD -> main)")
    P("$ make")
    P(c("1", "app.c:42:7: ") + c("1;31", "error: ") + c("1", "use of undeclared identifier 'x'"))
    P(c("1", "app.c:51:3: ") + c("1;35", "warning: ") + c("1", "unused variable 'tmp'"))
    P(c("1", "app.c:51:3: ") + c("1;36", "note: ") + "declared here")
    P("  1  [" + c("32", "|||||||||") + c("31", "|||") + "        42.0%]")
    P(c("30;42", " PID USER      CPU%  Command          "))
    P(c("30;46", " 812 ash       12.0  python3          "))
    P("F1" + c("30;46", "Help  ") + "F10" + c("30;46", "Quit  "))
    P("$ git commi" + c("90", "t -m \"fix\"") + c("90", "    # color 8: suggestions and comments"))
    P(c("1", "bold text") + "  normal text  " + c("37", "white text") + "  " + c("97", "bright white text")
      + "  " + c("2", "dim text"))
    P(c("2", "faint (SGR 2):") + " " + " ".join(c("2;%d" % (30 + i), n) for i, n in enumerate(NAMES[1:7], 1))
      + " " + " ".join(c("2;%d" % (90 + i), n) for i, n in enumerate(NAMES[1:7], 1)))
    P(c("2", "  >  collapsed preview in faint text: import sys, time  # Claude Code draws this with SGR 2"))
    P(c("4", "underlined") + "  " + c("7", " reverse video ") + "  select this line with the mouse to see the selection color")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
