# ds-terminal-theme design system

ds-terminal-theme is a Claude skill. It turns a design system into an Apple Terminal.app theme, and it writes `.terminal` profiles that pass contrast gates. The identity copies the look of Terminal.app's built-in "Man Page" profile, because the tool produces Terminal profiles and its own face should look like one. The landing page is the hero: it names the tool, gives its one-line purpose, and asks the reader to install the skill.

## Voice

1. Point the reader at one input. Example: "Just point it at a design system link."
2. Name the gate, not the feeling. Example: "\"Highly readable\" means code-enforced contrast gates, not taste."
3. State the output and its target. Example: "Output: a Terminal.app profile (`.terminal` file) for macOS 26 (Terminal 2.15)."
4. Say what a file does when opened. Example: "Opening a `.terminal` file imports it and opens a window."

## Colour

| Token | Value | Role | Contrast on `ground` |
|---|---|---|---|
| `ground` | #fef49c | Page and window ground (Man Page yellow) | none (ground) |
| `ink` | #1c1a10 | Primary text | 15.47:1 |
| `muted` | #57522f | Secondary text, captions | 7.02:1 |
| `rule` | #c9be62 | Non-text only: dot grid, hairlines | 1.69:1 (not for text) |
| `link-blue` | #1f4fb5 | Links, focus accent | 6.55:1 |
| `signal-red` | #b3261e | Errors | 5.80:1 |
| `signal-green` | #2d6a2e | Success | 5.80:1 |

All text pairs pass 4.5:1. `rule` is never used for text. Button label: `ground` on `link-blue`, 6.55:1.

## Type

- Family: IBM Plex Mono, weights 400 and 600. Source: Google Fonts, `https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600`.
- Stack: `"IBM Plex Mono", "SF Mono", Menlo, monospace`. The system stack keeps the same monospace cell pitch if the web font does not load.
- Scale (six styles, all in the `Text` group):

| Style | Size / line | Weight | Used for |
|---|---|---|---|
| `display` | 64px / 66px | 600 | Wordmark, hero name |
| `heading` | 28px / 34px | 600 | Hero headline |
| `lead` | 18px / 26px | 400 | Hero purpose line |
| `body` | 15px / 22px | 400 | Running text, button label |
| `small` | 13px / 18px | 400 | Taglines, captions |
| `code` | 13px / 20px | 400 | Commands, file names |

## Layout and spacing

- Phone width: 16px side gutter, no horizontal scroll.
- Cover: fixed 960px wide, 288px tall.
- Spacing steps: `space-1` 4px, `space-2` 8px, `space-3` 16px, `space-4` 32px.
- Radius: `radius-none` 0px, `radius-sm` 2px, `radius-md` 4px.
- Grid unit: one monospace cell, 9px wide by 18px tall (15px font, 0.6em advance, 18px line). The cover dot grid uses this pitch.

## Logo and wordmark

No logo exists for this project. The profile lists no logo files, and the repository holds none. The wordmark is plain type:

- Text: `ds-terminal-theme`, lower case, always.
- Type: IBM Plex Mono 600 (`display` style for large use, `heading` for small headers).
- Tracking: default. Do not add letter spacing.
- Clear space: one line height of the wordmark on all sides.
- Minimum size: 15px, the `body` size.
- Do not: set the name in capitals, colour it with a brand colour other than `ink`, add an icon, or set it in a display face other than IBM Plex Mono.

## Landing page anatomy

1. Hero (`components/Hero`): wordmark `ds-terminal-theme` in `display`, the one-line purpose in `lead` (`ink`), and one action, "Install the skill", in `body` on `link-blue`.
2. Cover (`components/Cover`): not a landing section. It is the identity card for the system: a dot grid in `rule`, one terminal-window slab in `ink`, colour blocks in `link-blue`, `signal-red` and `signal-green`, and the name and tagline.

## Status

new. No prior visual identity existed for this project. The palette, type and pattern come from the first design brief of 2026-10-18.
