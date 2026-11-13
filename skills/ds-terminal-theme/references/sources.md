# Sources: how the script gets design tokens

## Link types

| Link | Class | Who fetches |
|---|---|---|
| Local file or folder | local | the script reads it |
| `github.com/OWNER/REPO`, `/tree/REF/PATH`, `/blob/REF/PATH` | github | the script (GitHub API listing, then raw files) |
| `raw.githubusercontent.com/...` | file | the script |
| `npmjs.com/package/NAME`, `npm:NAME`, `unpkg.com/NAME`, `cdn.jsdelivr.net/npm/NAME` | npm | the script (package listing, then files) |
| `cdn.jsdelivr.net/gh/OWNER/REPO` | github | the script |
| A URL that ends in `.json`, `.css`, `.scss`, `.less`, `.js`, `.ts`, `.xml` | file | the script |
| Any other web page | web | the script: HTML, then linked CSS, then `@import`, then same-site JS; it follows a linked GitHub or npm source when the page gives few colors |
| `claude.ai/artifact/...` | claude-artifact | Claude, with the Artifact tool (sign-in) |
| Pidgin | pidgin | Claude, with the Pidgin MCP tools |
| `figma.com/...` | figma | Claude, with the Figma tools, or the user (variables export) |

When the script cannot fetch a link, it stops with exit code 2 and names the tool.

## claude.ai Design System artifact

1. `Artifact` with `action: "list"`, `scope: "files"`, `url: <link>`.
2. `Artifact` with `action: "read"` and `path` for each of these files that exists:
   `project/tokens.json`, `project/tokens.css`, `project/tokens/tokens.json`.
3. Save the files in one empty folder. Give the folder (or the files) to the script.

Do not read `project/design-system.json` for colors. It is a table, not tokens.

The claude.ai format calls its entries in `color.themes` "themes". They can be screen-size
breakpoints (for example `root-tablet`, `root-mobile`), not color modes. The script finds light and
dark modes from the background lightness only.

## Formats that the script reads

- claude.ai Design System `tokens.json` and `tokens.css`
- W3C DTCG (`$value`, `$type`, aliases `{a.b}`, `$extensions` modes, root `$extensions.<vendor>.dark`
  trees, DTCG 2025 structured colors)
- Style Dictionary (nested, flat, `raw.json`), Tokens Studio (`$themes`, `$metadata`), Figma Variables
  REST JSON, Material Theme Builder, Adobe Spectrum `sets`, Atlassian Figma export
- CSS custom properties: `var()` chains with fallbacks, `light-dark()`, `color-mix()`,
  `@media (prefers-color-scheme)`, `[data-theme]`, `.dark`, Tailwind v4 `@theme`
- SCSS and LESS variables and maps; JS and TS object literals; HTML inline styles; Android XML
- Color syntax: hex, `rgb()`, `hsl()`, `hwb()`, `lab()`, `lch()`, `oklab()`, `oklch()`, `color()`
  (Display P3 is gamut-mapped to sRGB)

Not read: YAML, Stylus, CSS relative color syntax (`oklch(from ...)`), `calc()` in colors.

## Several sources

Give all files of one design system in one run. Files with the same name in sibling folders
(`themes/light/x.json`, `themes/dark/x.json`) become modes. Do not give two different design
systems in one run.
