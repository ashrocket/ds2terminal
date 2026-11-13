# ds2terminal

ds2terminal turns a design system into Apple Terminal.app themes. It checks each theme with readability gates that run in code. It is a Claude skill with a Python command-line tool. The tool needs Python 3.9 or later and no packages.

It is for designers and developers who want their terminal to match a brand or a design system, and who want text that stays readable.

Give it a tokens file (JSON), a CSS file with custom properties, or a link. It writes:

- `<Name> Light.terminal` and `<Name> Dark.terminal`, ready to open in Terminal.app
- `report.md` and `report.json`: each color, its source token, its contrast, each gate result and each repair
- `preview.html`: each theme drawn as a terminal window

The `themes/` folder holds a gallery of generated themes.

## Example

```sh
python3 -I skills/ds-terminal-theme/scripts/ds2terminal.py design-system/tokens.json --name Guard --out out
```

```text
Guard Light.terminal: all hard gates pass
Guard Dark.terminal: all hard gates pass (derived)
wrote /path/to/out
```

The design system in `design-system/` defines a yellow page color and dark ink, and no dark mode. The tool maps the page color and ink to the light theme. It derives the dark theme from the ink. In `report.md`, the light theme's text row reads:

```text
| foreground | `#1c1a10` | token:ink | 96.2 | 15.47 | exact (Lc 96.2) |
```

## Install as a Claude skill

Copy or link the skill folder into your Claude skills folder:

```sh
ln -s "$PWD/skills/ds-terminal-theme" ~/.claude/skills/ds-terminal-theme
```

Then ask Claude for a Terminal theme from a design system. Claude reads `SKILL.md` and gets the token files. It can read claude.ai Design System artifacts and Figma variables through their tools. Then it runs the script and reports the result.

## Use the tool without Claude

```sh
python3 -I skills/ds-terminal-theme/scripts/ds2terminal.py SOURCE --name NAME --out DIR
```

`SOURCE` is a file, a folder, or a link (public GitHub repo, npm package, unpkg or jsDelivr URL, raw file). You can give more than one. Main options:

| Option | Use |
|---|---|
| `--name NAME` | Profile name. The files are `<NAME> Light.terminal` and `<NAME> Dark.terminal`. |
| `--modes auto\|light\|dark\|both` | Which themes to make. A mode that the design system lacks is derived from the other one. |
| `--font NAME`, `--font-size N` | Font and size. Default: the design system's monospace font if installed, else SF Mono Terminal, 13 pt. |
| `--cursor block\|underline\|bar` | Cursor shape. |
| `--set ROLE=HEX` | Force one color. The repair can still change it to pass a gate. |
| `--prefer-token ROLE=TOKEN` | Use this token for `bg`, `fg`, `brand` or a hue. |
| `--translucent ALPHA` | Translucent background. Every gate must also pass over a black and a white desktop. |
| `--no-preview` | Skip `preview.html`. |

Exit code 0 means every hard gate passes. Code 1 means a gate still fails after repair. Code 2 means bad input. See `skills/ds-terminal-theme/SKILL.md` for all options and `skills/ds-terminal-theme/references/sources.md` for the formats the tool reads.

## What "readable" means

The tool does not choose colors by taste. It moves each color into a contrast band and fails the build when a gate fails. Contrast uses APCA (Lc) and WCAG ratios. Main gates:

| Gate | Fails when |
|---|---|
| Text on background | APCA Lc < 75 or WCAG < 7 |
| Halation (dark) | text, bold, white or bright white Lc > 104 |
| ANSI 1-6 and 9-14 | Lc < 45 or WCAG < 3 |
| Bright black | Lc < 30, or less than 15 below the text |
| Separation | two hue colors closer than dE(OKLab) 0.06 |
| Color blindness | red and green, red and yellow, or red and magenta too close (protan, deutan) |
| Selection | text on it WCAG < 4.5 or Lc < 60 |
| Cursor | WCAG < 3 |
| Faint text (SGR 2) | faint text Lc < 30; a faint hue color Lc < 15 |

`skills/ds-terminal-theme/references/gates.md` lists every gate, its limit and its reason.

## Faint text

Many programs draw secondary text with SGR 2 (faint). We measured how Terminal 2.15 draws it: it mixes the text color toward the cell background, and the mix follows a power curve (exponent 1.26). Over 44 samples, the fitted model has an RMS error of 1.8 of 255. A plain 50% mix in sRGB has 17. A mix in linear light has 21. Real faint text is weak: faint white reaches at most about Lc 36 on a dark background, and faint black reaches Lc 45.8 on white. So the faint gates use low limits, and the tool never changes the blend. See [docs/faint-measurement.md](docs/faint-measurement.md).

## Report sections

- **Character.** The theme must still look like its design system. This section lists targets, not gates. The targets are: colors that come from tokens, whether the brand color shows, chroma kept (70% or more), largest hue change (12 degrees or less) and the smallest step from a normal to a bright color. A "Targets missed" line shows the cost of a gate.
- **Claude Code.** Claude Code draws on the theme in two ways. ANSI themes use the 16 colors. Standard themes use Claude Code's own colors on the theme background. The section gives the contrast of 16 pairs for both, and a "Recommended Claude Code theme" line. The tables come from the Claude Code 2.1.323 program file. We did not check them against a running session.

## Install and remove a theme

1. Open the `.terminal` file (double-click it, or `open "<file>"`). Terminal adds the profile and opens a window.
2. To use it for new windows, select it in Terminal > Settings > Profiles and click Default.
3. To remove it, select the profile in Terminal > Settings > Profiles and click the minus button.

The tool never opens a file or changes Terminal settings by itself.

## Known limits

- Programs that use 24-bit color do not use the theme. For Claude Code, set the theme that the report recommends.
- We did not measure how Terminal draws bold color or cell backgrounds on a translucent window.
- The tool writes an opaque background unless you pass `--translucent`. A translucent background makes text less readable.
- Terminal has no color for selected text or for text under the cursor. The gates check text on the selection and the cursor instead.
- A link to a public docs or marketing page can give a weak result.

## Tests

```sh
python3 -I -m unittest discover -s tests
```

## Measuring tools

`tools/measure/` holds the scripts that measured faint text. They run on a Mac only. `drive_probe2.py` and `osc11_probe.py` open one Terminal window and close it. They import no profile and write no preference. `fit_faint.py` and `reference_faint.py` run anywhere. Raw results are in `tools/measure/results/`.

## License

MIT. See [LICENSE](LICENSE).
