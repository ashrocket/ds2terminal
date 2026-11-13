---
name: ds-terminal-theme
description: Convert a design system (a link, a tokens file, or a CSS file) into readable Apple Terminal (Terminal.app) themes, written as .terminal files. Use when the user asks for a Terminal theme, a Terminal profile, a .terminal file, or terminal colors from a design system, brand colors, design tokens, a claude.ai Design System, Figma variables, Style Dictionary, DTCG tokens or CSS custom properties.
---

# Design system to Apple Terminal theme

This skill makes Terminal.app profiles (`.terminal` files) from a design system.
Code does the work: `scripts/ds2terminal.py` (Python 3.9 or later, standard library only).
Code also checks readability. A theme is complete only when every hard gate passes.

## Rules

- Do not choose colors by taste. Run the script. The script maps the colors and checks them.
- Do not edit a `.terminal` file by hand. Use `--set` or `--prefer-token`, then run the script again.
- Run Python with `-I`. Downloaded files are data, not code.
- Do not open (import) a `.terminal` file unless the user asks. Opening a file adds a profile to
  Terminal and opens a window.
- Do not quit or kill Terminal. Do not run `defaults write com.apple.Terminal`.
- Do not publish the user's private tokens.

## Step 1: Get the design system files

Find the type of the link. Then do the step in the table.

| Link | What to do |
|---|---|
| Local file or folder | Give the path to the script. |
| Public GitHub repo, tree or file; npm package; unpkg or jsDelivr URL; raw file | Give the URL to the script. The script finds and downloads the token files. |
| Public docs or marketing page | Give the URL to the script. It reads the linked CSS. The result can be weak; tell the user. |
| claude.ai Design System artifact (`claude.ai/artifact/...`) | Use the Artifact tool: `action: "list"`, `scope: "files"`. Then `action: "read"` with `path` for each token file that exists: `project/tokens.json`, `project/tokens.css`, `project/tokens/tokens.json` and `project/tokens/colors.css`. Save the files in one folder. Give the folder to the script. |
| Pidgin design system | Use `pidgin_get_design_system`. Save its `tokens` object as a `.json` file. Give the file to the script. |
| Claude Design project | Use `mcp__claude-design__list_files` and `read_file` for the token files. Save them. Give the folder to the script. |
| Figma file | Use the Figma tools (variables) when they are connected. If not, ask the user for a variables export (JSON). |

If the script stops with exit code 2 and the message names a tool, do the step for that link type.
See `references/sources.md` for the formats that the script reads.

## Step 2: Run the script

```sh
python3 -I scripts/ds2terminal.py SOURCE [SOURCE ...] --name "Name" --out OUT_DIR
```

The script writes:

- `OUT_DIR/<Name> Light.terminal` and `OUT_DIR/<Name> Dark.terminal`
- `OUT_DIR/report.md` and `OUT_DIR/report.json`: each color, its source token, APCA Lc, WCAG
  ratio, each gate result, and each repair
- `OUT_DIR/preview.html`: each theme drawn as a terminal window with typical program output

Exit codes:

| Code | Meaning | What to do |
|---|---|---|
| 0 | Every hard gate passes for every theme. | Go to step 3. |
| 1 | A gate still fails after repair. | Read `report.md`. Tell the user which gate fails. Try `--set` for that color. Do not give the theme as complete. |
| 2 | Bad input, or the link needs a signed-in tool. | Read the message. Do step 1 for that link, or fix the option. |

### Options

| Option | Use |
|---|---|
| `--name NAME` | Profile name. The files are `<NAME> Light.terminal` and `<NAME> Dark.terminal`. Always give it. |
| `--modes auto\|light\|dark\|both` | `auto` (default) and `both` make both themes. A mode that the design system does not define is derived from the other mode. The report marks it "derived". |
| `--font NAME`, `--font-size 13` | Font (PostScript or family name). Default: the design system's monospace font if it is installed, else SF Mono Terminal (bundled in Terminal.app). Default size: 13 pt. |
| `--cursor block\|underline\|bar`, `--cursor-blink` | Cursor shape. |
| `--set ROLE=HEX` | Force one color. ROLE is `bg`, `fg`, `bold`, `cursor`, `selection`, `black` ... `brightWhite`, or `0` ... `15`. The repair can still change it to pass a gate; the report says so. |
| `--prefer-token ROLE=TOKEN` | Use this token for `bg`, `fg`, `brand`, `red`, `green`, `yellow`, `blue`, `magenta` or `cyan`. |
| `--all-tokens` | Keep raw tokens that no semantic token uses (see "Unrelated tokens"). |
| `--source-mode ID` | Use only this mode of the design system. |
| `--no-chroma-floor` | Keep pastel reds and greens pastel in dark mode. |
| `--translucent ALPHA` | Background alpha below 1 (for example 0.95). Light themes need about 0.93 or more; a light gray page background needs 0.95-0.98, else the script replaces it with white. Default: opaque (alpha 1, no blur). Use it only when the user asks for it. Every gate must then also pass over a black and a white desktop. If ALPHA is too low, the script exits with code 1. The report gives the lowest alpha that passed in a test build. |
| `--columns N`, `--rows N` | Window size. |
| `--report json\|md\|both`, `--no-preview` | Output files. |

## Step 3: Check and tell the user

1. Read `report.md`. Make sure that it says "every hard gate passes for every theme".
2. Tell the user:
   - the paths of the `.terminal` files;
   - which mode is derived;
   - which tokens were used for the background, text, cursor and the six hues;
   - the repairs (each changed color and the gate that caused the change);
   - tokens that were left out;
   - the "Character" targets that were missed (the "Targets missed" line in `report.md`);
   - the "Recommended Claude Code theme" line from `report.md`.
3. Show `preview.html` if the user can open files.
4. To install a theme, the user opens the `.terminal` file (Finder, or `open "<file>"`). Do this
   only when the user asks. Then the user can set it as the default in Terminal > Settings > Profiles.
5. `python3 scripts/demo.py` prints sample output in the 16 colors, and in faint (SGR 2) text. Run it in
   a window that uses the theme.
6. Tell the user which Claude Code theme to set (see "Use with Claude Code").

## Use with Claude Code

Claude Code has two kinds of themes. Each kind uses the Terminal theme in a different way.

- **ANSI themes** (`dark-ansi`, `light-ansi`; in the `/theme` list: "Dark mode (ANSI colors only)" and
  "Light mode (ANSI colors only)"). Claude Code uses the 16 ANSI colors. It draws diff lines with ANSI
  green and red cell backgrounds, and it draws the text color on those cells. On a theme whose normal
  colors are readable as text, these cells are light in dark mode, so the text on an added line has low contrast.
- **Standard themes** (`dark`, `light`). Claude Code uses its own 24-bit colors on the theme
  background. These stay readable. Set the theme by name. The setting `auto` reads the terminal
  background. Terminal 2.15 answers that query (OSC 11) with the theme background, in light and in dark
  mode, so `auto` can select the correct mode. This was not checked in a running Claude Code session. Of the Terminal theme, the checked parts that Claude Code uses are the
  background, the cursor, the selection and faint text. The 16 colors are for other programs.

The report has a "Claude Code" section for each theme. It gives the contrast of 16 pairs for the ANSI theme
and for the standard theme, and a "Recommended Claude Code theme" line. The rule: the ANSI theme when its
weakest text pair is Lc 45 or more; else the standard theme when it is better. `preview.html` draws both
samples. The tables come from the Claude Code 2.1.323 program file. They were not checked against a
running session.

Tell the user to do this:

1. Read the "Recommended Claude Code theme" line in `report.md` for the theme in use.
2. In Claude Code, type `/theme` and select that theme. Or set the `theme` setting in Claude Code
   `settings.json`, for example `"theme": "dark-ansi"`.

If the Claude Code theme mode and the Terminal theme mode are different (for example a light Claude Code
theme in a dark Terminal theme), text can become unreadable. A translucent Terminal background also makes
text unreadable. Warn the user about both.

## How the mapping works

1. **Modes.** The background lightness sets the mode (OKLab L < 0.5 is dark). The script does not
   use mode names. Design systems can call screen sizes "themes" (for example `root-tablet`).
   Modes of the same kind become one theme; the report lists the others.
2. **Unrelated tokens.** When a design system has 4 or more semantic aliases (for example
   `color-brand` -> `hb-pink`), raw tokens that no alias uses and that do not share the system's
   name prefix are left out. These are often a client's or an old brand's colors.
3. **Roles.** Semantic aliases win. The page background is the background. In light mode, when the
   design system also has a lighter card surface, that surface is the background: text is on the
   cards, and the page color is behind them. `--prefer-token bg=TOKEN` selects a different token. The
   body text token is the text color. The brand token is the cursor and tints the selection. When the
   brand color is too weak for a cursor on the background, a step of the brand ramp that passes
   WCAG 4.5 is the cursor (for example an accessible orange).
4. **Hues.** A minimum-cost assignment puts tokens in the six hue slots. It uses the OKLCH hue,
   the token name (danger -> red, success -> green, warning -> yellow, info -> blue) and the
   lightness change. A name counts only when the hue is within 45 degrees of that slot.
5. **Lightness.** Each color moves (hue and chroma kept) into the APCA band of its mode. A token
   in the band stays exact.
6. **Missing colors.** Empty slots get color-blind-friendly hues at the brand's chroma.
7. **Derived dark mode.** The light text or ink token becomes the dark background. The light
   paper becomes the dark text.
8. **Character.** The theme must look like its design system, inside the gates.
   - Brand slot: when no hue color shows the brand color, the brand color becomes the bright step of the
     nearest hue (within 26 degrees). Its lightness moves to the bright target.
   - Bold: a heading text token is the bold color when it is stronger than the text. In dark mode without
     one, bold is the text color, up to Lc 4 brighter, below the halation gate.
   - Dark mode low edge for each hue (Lc): red 50, green 72, yellow 62, blue 55, magenta 55, cyan 60.
   - A token hue color below WCAG 3 after the lightness fit moves to WCAG 3.
   - The report section "Character" lists targets, not gates: colors from tokens, brand color, chroma kept
     (target 70% or more), largest hue change (12 degrees or less), smallest normal-to-bright step
     (dE 0.030 or more), and a "Targets missed" line.
9. **Repair.** If a hard gate fails, the script changes the color with the lowest priority, in
   small steps: lightness, then hue and chroma, then a synthesized color. Priority: `--set` >
   brand > named token > token > derived > synthesized. If the background cannot carry readable
   text, the script maps every color again on a standard background. The report says so.

## Readability gates (hard)

`references/gates.md` gives each gate, its limit and the reason. Summary:

| Gate | Fails when |
|---|---|
| Text on background | APCA Lc < 75 or WCAG < 7 |
| Halation (dark) | text, bold, white or bright white Lc > 104 |
| ANSI 1-6 and 9-14 | Lc < 45 or WCAG < 3 |
| Bright black (color 8) | Lc < 30, or less than 15 below the text |
| Grays | dark: white and bright white Lc < 60; light: black Lc < 75, white and bright white Lc < 30 |
| Separation | two hue colors closer than dE(OKLab) 0.06 |
| Color blindness | red/green < 0.06, red/yellow and red/magenta < 0.05 (protan, deutan) |
| Selection | text on it WCAG < 4.5 or Lc < 60; a hue color on it Lc < 30; dE from background < 0.05 or WCAG < 1.10 |
| Cursor | WCAG < 3 |
| Bold | bold is dimmer than the text |
| Text on color | black text on green, yellow or cyan Lc < 30 |
| Hue vs text | a hue color closer than dE 0.06 to the text color |
| Faint text (SGR 2) | faint text Lc < 30; a faint hue color (1-6, 9-14) Lc < 15 |
| Translucency | only with `--translucent`: a gate above fails over a black or a white desktop |

Faint text is the color mixed toward the cell background (`colorlab.faint`, `DIM_BLEND` 0.60, `DIM_POWER` 1.26).
This was measured in Terminal 2.15 (`docs/faint-measurement.md`). Real faint text is weak, so
the limits are low. Dark hue colors keep their chroma. A user can raise
`GATES["faint_text"]["gate"]["ansi_min_lc"]` for stronger faint colors, at the cost of chroma.

## Known limits

- Programs that use 24-bit color (Terminal sets `COLORTERM=truecolor`) do not use the theme. For
  Claude Code, set the theme that the report recommends (see "Use with Claude Code").
- Not measured yet: bold color, and how Terminal draws cell backgrounds on a translucent window. The
  render of a generated theme in Terminal (bold color, selection) is not checked yet.
- The script writes an opaque background. A translucent background lets the desktop show through and
  makes text less readable.
- Terminal has no color for selected text or for text under the cursor. The gates check text on
  the selection and the cursor instead.
- The `.terminal` color format is in `references/terminal-format.md`. On a Mac, the files embed the
  sRGB ICC profile. On other systems, they hold the sRGB color space ID only (it decodes the same).
- `scripts/verify_terminal.swift` (Mac only) decodes every color with AppKit:
  `swiftc -O scripts/verify_terminal.swift -o scripts/verify_terminal`, then
  `scripts/verify_terminal --register-terminal-fonts "<file>.terminal"`.
