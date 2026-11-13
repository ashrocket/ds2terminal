# Readability gates

Source of truth: `scripts/dsterm/colorlab.py`, `GATES` (version 1.0).
Background: APCA and WCAG limits from published guidance. The faint-text limits are measured (`docs/faint-measurement.md`).

- **Gate** = hard limit. The script repairs the theme until every gate passes. Exit code 1 when one still fails.
- **Target** = aim. A miss is listed in the report. It does not fail the theme.
- Lc = |APCA Lc| (APCA-W3 0.0.98G-4g). WCAG = WCAG 2.2 contrast ratio. dE = distance in OKLab.
- Colors 1-6 are the normal hues, 9-14 the bright hues, 0/7/8/15 the grays.
- The script adds three rules to `colorlab.GATES` (in `scripts/dsterm/gates.py`, `check`):
  - a theme with no SelectionColor or no CursorColor fails;
  - `selection`: the selection must also differ from the background in luminance (WCAG >= 1.10), because
    dE(OKLab) is inflated near black;
  - `hue_vs_text`: each hue color (1-6, 9-14) must be at least dE(OKLab) 0.06 from the text color, else
    colored text reads as plain text.
- The "reason" text under each gate is copied from `colorlab.GATES`.

## fg_contrast

- Gate: `{'min_lc': 75.0, 'min_wcag': 7.0}`
- Target: `{'min_lc': 90.0}`

Default text is body-like text at ~12-13px/400. APCA bronze: Lc 75 is the body-text minimum and Lc 90 the preferred level (and the level for 12px/400 non-body text). WCAG 2.2 SC 1.4.6 (AAA) 7:1 as the second floor.

## halation

Modes: dark.
- Gate: `{'max_lc': 104.0, 'slots': ['foreground', 'bold', 'white', 'brightWhite']}`
- Target: `{'fg_max_lc': 100.0, 'fg_max_L': 0.94, 'bg_min_L': 0.15}`

No standard sets a maximum for small text; this is a heuristic. Lc > 104 is reachable only with near-#fff text on near-#000 backgrounds (#fff on #000 = Lc -107.9), the pairing that causes halation/smear for astigmatic readers. Reference dark themes: fg L 0.65-0.98 (median 0.88), bg L 0.18-0.33.

## ansi_normal

- Gate: `{'min_lc': 45.0, 'min_wcag': 3.0}`
- Target dark: `{'min_lc': 60.0, 'min_wcag': 4.5}`
- Target light: `{'min_lc': 54.0, 'max_lc': 66.0, 'min_wcag': 3.0}`

Colored text (errors, diffs, ls, grep) must be readable. APCA Lc 45 = large/heavy text minimum, Lc 60 = content text minimum. WCAG 3:1 (SC 1.4.3 large text) floor, 4.5:1 target in dark mode. Light mode: normal slots are also BACKGROUNDS under black text (tmux, htop, macOS ls); with black ~#1b1f24 on bg ~#fafafa both constraints hold only for Lc ~54-68 (WCAG 3.0-4.4), so the light target is a band.

## ansi_bright

- Gate: `{'min_lc': 45.0, 'min_wcag': 3.0}`
- Target dark: `{'min_lc': 60.0, 'min_wcag': 4.5}`
- Target light: `{'min_lc': 66.0, 'min_wcag': 4.5}`

Bright colors are text colors too (bold-as-bright, prompts). Light mode: make bright = the darker, higher-contrast ink (as Selenized Light does), since apps rarely use 100-107 backgrounds.

## bright_relation

- Gate: `{'max_hue_diff': 30.0, 'min_chroma_ratio': 0.5, 'only_if_normal_C_at_least': 0.04}`
- Target: `{'min_dEok': 0.03, 'dark_min_dL': -0.01, 'light_min_dLc': 0.0}`

Bright N must read as the same hue as normal N (bright red is red). Bold-as-bright needs a visible step (>= 1.5 JND).

## dim_brightBlack

- Gate: `{'min_lc': 30.0, 'max_lc_vs_fg_gap': 15.0}`
- Target: `{'min_lc': 40.0, 'max_lc': 60.0, 'max_lc_vs_fg_gap': 25.0, 'min_wcag': 3.0}`

Color 8 is the de-facto 'dim' color: zsh-autosuggestions default fg=8, comments, git graph, prompt metadata. APCA Lc 30 is the absolute minimum for spot-readable text (placeholder/disabled). It must stay clearly dimmer than fg (>= Lc 15 lower).

## grays_dark

Modes: dark.
- Gate: `{'white_min_lc': 60.0, 'brightWhite_min_lc': 60.0}`
- Target: `{'white_min_lc': 75.0, 'brightWhite_ge_white': True, 'black_min_dEok_vs_bg': 0.03, 'black_max_dL_vs_bg': 0.15}`

Dark mode: 7/15 are text colors. 0 is a background/surface color and the text color on colored bars (htop, tmux, macOS ls), so it stays dark; black-as-text on the default background is not supported (11/14 reference dark themes have |Lc| < 15 for it).

## inks_light

Modes: light.
- Gate: `{'black_min_lc': 75.0, 'white_min_lc': 30.0, 'brightWhite_min_lc': 30.0}`
- Target: `{'black_ge_fg': True, 'white_lc_range': [45.0, 60.0], 'brightWhite_lighter_than_white': True}`

Light mode: the classic trap is white (7/15) text vanishing on a light background; many tools emit 37/97 assuming a dark terminal (git blame default 'white', CLI headings). Keep 7/15 light but spot-readable (Lc >= 30, e.g. ~#c7c7c7 on #fff), 15 lighter than 7 so they still work as light backgrounds. 0 must be a full-strength ink.

## separation

- Gate: `{'min_dEok': 0.06}`
- Target: `{'min_dEok': 0.1, 'min_hue_diff': 25.0, 'hue_needs_C': 0.05}`

Each of the six hues is a separate category; 0.06 = 3x the OKLab JND (0.02). Text glyphs are small fields, which need more than 1 JND.

## cvd

- Gate: `{'red/green': 0.06, 'red/yellow': 0.05, 'red/magenta': 0.05}`
- Target: `{'red/green': 0.1, 'red_green_min_dL': 0.05, 'tritan_all_pairs': 0.05}`
- Pairs: `{'red/green': [1, 2], 'red/yellow': [1, 3], 'red/magenta': [1, 5]}`

Machado 2009 severity 1.0 dichromat simulation. red/green = git diff and git status; red/yellow = rustc/cargo error vs warning; red/magenta = gcc/clang error vs warning. Gate covers protan+deutan (~6% of men, per Machado/colorspacious notes); tritan (<0.01%) is a target only. A lightness gap survives every CVD type. Reference: GitHub Colorblind themes reach 0.27-0.31 for red/green; the median reference theme is ~0.10.

## selection

- Gate: `{'fg_min_wcag': 4.5, 'fg_min_lc': 60.0, 'sel_min_dEok_vs_bg': 0.05, 'ansi_min_lc': 30.0}`
- Target: `{'fg_min_lc': 75.0, 'sel_dEok_vs_bg_range': [0.06, 0.2], 'ansi_min_lc': 45.0}`

Terminal.app has no selection-text color key (SelectionColor only), so selected text keeps its own color over SelectionColor: fg and every chromatic ANSI color must stay readable on it, and the highlight must be visible against bg. APCA clips |Lc| < ~7 to 0, so selection-vs-bg uses dEok.

## cursor

- Gate: `{'min_wcag': 3.0}`
- Target: `{'min_wcag': 4.5, 'min_lc': 45.0}`

WCAG 2.2 SC 1.4.11 non-text contrast 3:1 (and SC 2.4.13 AAA focus 3:1). Target 4.5:1 so a glyph drawn in bg color on a block cursor stays readable (Terminal.app has no cursor-text color key).

## bold

- Gate: `{'max_lc_drop_vs_fg': 2.0}`
- Target: `{'max_dEok_vs_fg': 0.1}`

TextBoldColor must not be dimmer than fg, and should read as the same color.

## text_on_color

- Gate: `{'black_on': [2, 3, 6], 'min_lc': 30.0}`
- Target: `{'best_of_black_white_min_lc': {'dark': 45.0, 'light': 35.0}, 'black_on_red_min_lc': 30.0}`

ANSI colors are used as BACKGROUNDS with black text: tmux status-style bg=green,fg=black; htop function bar and selection black-on-cyan, headers black-on-green/yellow; macOS ls LSCOLORS default exfxcxdxbxegedabagacadah (black on red/cyan/green/brown). In light mode the best-of target is 35, because ANSI >= WCAG 3:1 on a light bg caps black-on-color at ~Lc 30-45 (verified with the solver).

## faint_text

- Gate: `{'fg_min_lc': 30.0, 'fg_min_lc_dark': 30.0, 'ansi_min_lc': 15.0}`
- Target: `{'fg_min_lc': 38.0, 'fg_min_lc_dark': 33.0, 'ansi_min_lc': 20.0}`
- Model: `faint = ((1 - DIM_BLEND) * color^DIM_POWER + DIM_BLEND * bg^DIM_POWER)^(1 / DIM_POWER)` for each
  sRGB-encoded channel. `DIM_BLEND = 0.60`, `DIM_POWER = 1.26` (`colorlab.faint`). Terminal mixes toward the
  cell background. The fit to 38 measured samples has RMS 1.8 of 255. Report: `docs/faint-measurement.md`.

Claude Code draws collapsed previews and secondary text with SGR 2 (faint). The gate checks the faint text
color and the faint forms of colors 1-6 and 9-14 on the background.

- Faint text Lc >= 30 in both modes. This is the limit of bright black, because faint text has the same
  role (secondary text). It is also the APCA minimum for spot text.
- Faint colors 1-6 and 9-14: Lc >= 15, the APCA minimum for a visible non-text item.
- The old limits (faint text 45 in light mode, 30 in dark mode; faint hue colors 30) came from a model
  with a 50% mix in sRGB. The measurement shows that they cannot be reached. Faint `#ffffff` reaches Lc 36
  at most on a dark background. Faint `#000000` reaches Lc 45.8 on `#ffffff` (42.9 on `#f3f3f3`). A faint hue
  color in dark mode reaches about Lc 33 at most (a pale yellow on a dark gray background). Most hues stay
  below Lc 30.
- When the gate fails, the repair makes the text or the color stronger. It never changes the blend.
- Effect on the palette: the mapper puts each hue color at or above its "faint floor" (`mapper.hue_floor`).
  In dark mode the floor is about Lc 51. Dark hue colors keep their chroma. The light text color aims at the
  target (38) when pure black can reach it on that background (`mapper.fg_floor`).
- Reference values (faint text Lc; faint hue colors Lc): Snazzy 32; 13-33. Dracula 34; 12-33.
  GitHub Dark 30; 15-18. Tokyo Night 24; 15-23. GitHub Light 42; 30-40.
- A user can raise `GATES["faint_text"]["gate"]["ansi_min_lc"]` for stronger faint colors. The cost is
  lower chroma in dark mode.
- A dark background whose faint floor is too high (for example `#000000`) cannot hold six separate faint
  hues. The script then replaces it with a standard dark background and says so in the report.

## translucency

- Gate: `{'desktops': ['#000000', '#ffffff']}`

The script writes an opaque background (alpha 1, `BackgroundBlur` 0). `--translucent ALPHA` writes a
background alpha below 1. Then the script composites the background over a black and a white desktop.
Every gate must pass on the background and on both composites. The report shows the worst case for each
desktop. The gate does not model blur, or text and pictures on the desktop. An opaque background is the
safe choice.

Light themes have little room. Over a black desktop the background becomes darker, so the faint hue colors
must be darker. Black text on green, yellow and cyan needs these colors light. On `#fafafa` the two limits
meet at about alpha 0.93; on `#ffffff` at about 0.91. These limits are necessary, not sufficient: with the
test fixtures, light themes passed at 0.93 and failed at 0.91 and 0.92. Dark themes can go lower (0.76 on
a dark navy background). When a translucent theme fails, the script builds the theme again at higher alpha values and
writes the lowest alpha that passed to the report. A light gray page background needs more: `#f3f3f3` needs
0.96, `#eeeeee` 0.98. Below that, the script replaces the background with `#ffffff`.

## Targets that the mapper uses

| Mode | Text | Normal hues (red, green, yellow, blue, magenta, cyan) | Brights | 0 | 7 | 8 | 15 |
|---|---|---|---|---|---|---|---|
| dark | Lc 90 (keep a token at 85-100) | 58, 85, 80, 62, 66, 74 (keep a token at 55-96) | normal + 8, at least 70 | bg L - 0.07 (or + 0.06 on a very dark bg) | 78 | 45 | 92-100 |
| light | Lc 95 (keep a token at 85-108) | 55, 66, 64, 60, 57, 62 (keep a token at 52-68) | 70, 80, 78, 74, 72, 76 | Lc 100 | 48 | 55 | 32 |

Both bands pass every gate. Each hue value is raised to the
faint floor (see `faint_text`) when the floor is higher. Dark-mode hue values have a low edge
(`TARGETS["dark"]["normal_lo"]`: red 50, green 72, yellow 62, blue 55, magenta 55, cyan 60). The light band is narrow:
the hues must be dark enough for WCAG 3 and light enough for black text on them (Lc 30).
