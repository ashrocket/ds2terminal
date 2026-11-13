# Faint (SGR 2) text, measured

Date: 2026-11-12. Terminal 2.15, macOS 26.7.3.

These measurements were made once, on one Mac (Terminal 2.15, macOS 26.7.3), with the tools in `tools/measure/`. You cannot repeat them from this repository alone. The raw results of the three profile runs are in `tools/measure/results/`. The two checks on generated themes have no data file here.

## Method

- Tools: `tools/measure/drive_probe2.py` (driver) and `probe2.py` (draws pairs of full-block
  bands: one normal, one faint). `fit_faint.py` fits the model.
- The driver opens one new Terminal window. It can switch that window only to an installed profile.
  It captures the window with `screencapture -l`, converts the capture to sRGB with `sips`, reads the
  bands, and closes its own window.
- It imports nothing and writes no preference. It stops when the new tab lands in an existing window.
- Profiles: Snazzy (dark, background #2a2f3a, opaque), Novel (light, background #e0dbc4, opaque), and
  Clear Dark (translucent; used only as a check).
- Each run has 22 pairs, plus black and white cell backgrounds. The result is 44 clean samples. This repository holds 38 of them: the six rows that used a private color are not included. The numbers in this report are for the 38 samples.

## Samples

| Text color | Cell background | Faint text draws as |
|---|---|---|
| #ffffff | #000000 | #7a7a7a |
| #000000 | #ffffff | #a9a9a9 |
| #ff0000 | #2a2f3a | #8c2226 |
| #eff0eb | #2a2f3a | #858789 |

## Model

Terminal mixes the text color toward the cell background (not toward the window background). It does this
for each sRGB-encoded channel:

`faint = ((1 - DIM_BLEND) * color^DIM_POWER + DIM_BLEND * bg^DIM_POWER)^(1 / DIM_POWER)`

with `DIM_BLEND = 0.60` and `DIM_POWER = 1.26`. The code is `colorlab.faint`.

| Model | RMS error (of 255) |
|---|---|
| Fitted model above | 1.8 |
| Plain sRGB mix, best share (0.59) | 9.1 |
| Old model: 50% mix in sRGB | 17 |
| Mix in linear light | 21 |

## Consequence

Real faint text is weaker than the old model said. It is weakest for dark text on a light background.

- Faint #ffffff reaches at most about Lc 36 on a dark background.
- Faint #000000 reaches Lc 45.8 on #ffffff (42.9 on #f3f3f3).
- A faint hue color in dark mode reaches about Lc 33 at most (a pale yellow on a dark gray background).
  Most hues stay below Lc 30.
- So the old limits (faint text 45, faint hue colors 30 for every hue) cannot be reached. The old dark themes passed
  only because the model was wrong.

Reference values with the measured blend (faint text Lc; faint hue colors Lc):

| Theme | Faint text | Faint hue colors |
|---|---|---|
| Snazzy | 32 | 13-33 |
| Dracula | 34 | 12-33 |
| GitHub Dark | 30 | 15-18 |
| Tokyo Night | 24 | 15-23 |
| GitHub Light | 42 | 30-40 |
| Claude Code standard dark colors on #1e1e2e | 35 | 12-24 |

## New limits (`colorlab.GATES["faint_text"]`)

| Item | Gate | Target |
|---|---|---|
| Faint text, light mode (`fg_min_lc`) | Lc 30 | Lc 38 |
| Faint text, dark mode (`fg_min_lc_dark`) | Lc 30 | Lc 33 |
| Faint hue colors 1-6, 9-14 (`ansi_min_lc`) | Lc 15 | Lc 20 |

- Faint text has the same gate as bright black, because it has the same role (secondary text).
- Lc 15 is the APCA minimum for a visible non-text item.
- The mapper aims the light text color at its target when pure black can reach it on that background
  (`mapper.fg_floor`).
- Effect: hue floors in dark mode fall from Lc 78-98 to about Lc 51. Dark hue colors keep their chroma.
  On one generated dark theme, red was a pale pink (chroma 0.05) and is now a clear red (chroma 0.15).
  That theme had six repairs before and has none now.
- A user can raise `GATES["faint_text"]["gate"]["ansi_min_lc"]` for stronger faint colors. The cost is
  lower chroma.

## Other findings

- A profile without the key `DynamicANSIForegroundColors` (Snazzy) draws ANSI colors lighter than the
  profile says: red #ff5b52 draws as #ff8174.
- With the key false (Clear Dark), the colors are exact: blue #6d96b4 draws as #6c96b4.
- The generator writes the key as false, so generated themes draw exact colors.
- Truecolor draws exact: #808080 draws as #808080.

## Check on a generated theme

A generated dark theme (a dark navy background) was imported and measured with the same tool. This
background was not in the fit.

| Measure | Result |
|---|---|
| 12 colors (text, bold, eight ANSI colors, bright black, bright red, bright white): drawn against the theme | within 2 of 255 |
| Drawn faint colors against `colorlab.faint` | within 3 of 255 |
| Drawn faint text | Lc 32.9 (gate 30) |
| Weakest drawn faint hue color | red, Lc 16.6 (gate 15) |
| Bold text with no color | draws in `TextBoldColor` (within 1 of 255) |

A generated light theme (background #f3f3f3) gave the same result: colors within 2 of 255, faint
model within 3 of 255. Drawn faint text: #aeacac, Lc 37.4. Weakest drawn faint hue color: cyan, Lc 20.3.

The same light theme on a white background (#ffffff) gave: colors within 2 of 255, faint model within 2 of
255, drawn faint text #bab9b8, Lc 37.7, weakest drawn faint hue color cyan, Lc 21.8. On a white background
the window title bar also gives bands; the driver uses the last 12 bands.

## Background query (OSC 11)

`osc11_probe.py` asks the terminal for its background color. Terminal 2.15 answers `rgb:f3f3/f3f3/f3f3` on
the generated light theme and `rgb:1a1a/1414/3030` on the generated dark theme. Claude Code's setting `auto` uses this answer
to select the light or the dark theme.

## Not measured yet

- How Terminal draws cell backgrounds on a translucent window.

## Data

- Raw probe results: `tools/measure/results/faint-snazzy.json`, `faint-novel.json` and `faint-cleardark.json`.
  The window captures are not in the repository.
- Fit: `python3 -I tools/measure/fit_faint.py tools/measure/results/faint-snazzy.json tools/measure/results/faint-novel.json`.
- Reference themes: `python3 -I tools/measure/reference_faint.py`.
