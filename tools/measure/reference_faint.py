"""reference_faint.py - faint (SGR 2) contrast of well-known themes with the measured Terminal blend.

usage: python3 -I reference_faint.py
For each theme: |APCA Lc| of the text, of faint text, of the six hue colors and of the faint hue colors.
The palettes are the published colors of each theme (background, text, red, green, yellow, blue,
magenta, cyan). The last rows are the standard Claude Code 2.1.323 colors on a dark and a light background.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                "skills", "ds-terminal-theme", "scripts"))
from dsterm import colorlab as cl  # noqa: E402

THEMES = (
    ("Snazzy", "#2b2f3a", "#eff0eb", ("#ff5c57", "#5af78e", "#f3f99d", "#57c7ff", "#ff6ac1", "#9aedfe")),
    ("Dracula", "#282a36", "#f8f8f2", ("#ff5555", "#50fa7b", "#f1fa8c", "#bd93f9", "#ff79c6", "#8be9fd")),
    ("Catppuccin Mocha", "#1e1e2e", "#cdd6f4", ("#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5")),
    ("GitHub Dark", "#0d1117", "#e6edf3", ("#ff7b72", "#3fb950", "#d29922", "#58a6ff", "#bc8cff", "#39c5cf")),
    ("Solarized Dark", "#002b36", "#839496", ("#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198")),
    ("One Dark", "#282c34", "#abb2bf", ("#e06c75", "#98c379", "#e5c07b", "#61afef", "#c678dd", "#56b6c2")),
    ("Tokyo Night", "#1a1b26", "#c0caf5", ("#f7768e", "#9ece6a", "#e0af68", "#7aa2f7", "#bb9af7", "#7dcfff")),
    ("Solarized Light", "#fdf6e3", "#657b83", ("#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198")),
    ("GitHub Light", "#ffffff", "#1f2328", ("#cf222e", "#116329", "#4d2d00", "#0969da", "#8250df", "#1b7c83")),
    ("Catppuccin Latte", "#eff1f5", "#4c4f69", ("#d20f39", "#40a02b", "#df8e1d", "#1e66f5", "#ea76cb", "#179299")),
    # Claude Code standard theme: error, success, warning, permission, Claude color, plan mode
    ("Claude Code dark on #1e1e2e", "#1e1e2e", "#ffffff",
     ("#ff6b80", "#4eba65", "#ffc107", "#b1b9f9", "#d77757", "#48968c")),
    ("Claude Code light on #ffffff", "#ffffff", "#000000",
     ("#ab2b3f", "#2c7a39", "#966c1e", "#5769f7", "#d77757", "#006666")),
)


def main():
    print("%-30s %6s %6s  %-24s %s" % ("theme", "text", "faint", "hue colors", "faint hue colors"))
    for name, bg, fg, hues in THEMES:
        print("%-30s %6.1f %6.1f  %-24s %s" % (
            name, cl.lc_abs(fg, bg), cl.lc_abs(cl.faint(fg, bg), bg),
            " ".join("%2.0f" % cl.lc_abs(h, bg) for h in hues),
            " ".join("%2.0f" % cl.lc_abs(cl.faint(h, bg), bg) for h in hues)))


if __name__ == "__main__":
    main()
