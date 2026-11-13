#!/bin/sh
# Rebuild every theme in themes/ from the repo root, from the saved design-system folders (no network).
# Set PNG=1 to also render themes/*/preview.png with headless Chrome.
# This script does not open any file in Terminal.
set -eu
cd "$(dirname "$0")/.."
PY="${PYTHON:-/usr/bin/python3}"
TOOL=skills/ds-terminal-theme/scripts/ds2terminal.py
run() { "$PY" -I "$TOOL" "$@"; }
SCR="$(mktemp -d)"
trap 'rm -rf "$SCR"' EXIT

# Optional: REFRESH=1 downloads the upstream files again (head of the default branch) into
# themes/<dir>/design-system and updates the commit and date in themes/<dir>/SOURCE.md.
# The default path uses the saved copies only and needs no network.
refresh() { # dir owner/repo
  sha="$(git ls-remote "https://github.com/$2" HEAD | cut -f1)"
  [ -n "$sha" ] || { echo "cannot resolve $2" >&2; exit 1; }
  ( cd "themes/$1/design-system" && find . -type f | sed 's|^\./||' | while read -r f; do
      curl -fsSL "https://raw.githubusercontent.com/$2/$sha/$f" -o "$f"
    done )
  sed "s|^- Commit: .*|- Commit: $sha|; s|^- Fetched: .*|- Fetched: $(date +%F)|" "themes/$1/SOURCE.md" > "$SCR/SOURCE.md"
  cp "$SCR/SOURCE.md" "themes/$1/SOURCE.md"
}
if [ "${REFRESH:-0}" = 1 ]; then
  refresh primer primer/primitives
  refresh carbon carbon-design-system/carbon
  refresh catppuccin catppuccin/palette
fi
# The project's own theme: light and dark in one run. The brand color is the yellow ground.
run design-system/tokens.json --name ds2terminal --modes both --prefer-token brand=ground --out themes/ds2terminal

# Public design systems, one run each, from the saved design-system folders.
run themes/primer/design-system --name Primer --out themes/primer
run themes/carbon/design-system --name Carbon --out themes/carbon

# Catppuccin: the source has four flavors and the tool uses one mode per run.
# Latte (light) and Mocha (dark) are built in two runs, then merged.
run themes/catppuccin/design-system --name Catppuccin --modes light --source-mode latte --out "$SCR/latte"
run themes/catppuccin/design-system --name Catppuccin --modes dark --source-mode mocha --out "$SCR/mocha"
mkdir -p themes/catppuccin
cp "$SCR/latte/Catppuccin Light.terminal" "$SCR/mocha/Catppuccin Dark.terminal" themes/catppuccin/
"$PY" -I - "$SCR" themes/catppuccin <<'PYEOF'
import json, sys
scr, out = sys.argv[1], sys.argv[2]
def rd(p):
    with open(p, encoding="utf-8") as f:
        return f.read()
# report.md: Latte report, plus the Mocha table row and the Mocha theme section.
la, mo = rd(scr + "/latte/report.md"), rd(scr + "/mocha/report.md")
row = [l for l in mo.splitlines() if l.startswith("| Catppuccin Dark.terminal")][0]
la_lines = la.splitlines()
i = max(n for n, l in enumerate(la_lines) if l.startswith("| Catppuccin Light.terminal"))
la_lines.insert(i + 1, row)
la = "\n".join(la_lines) + "\n"
head, tail = la.split("## How to read this report", 1)
dark = mo[mo.index("## Catppuccin Dark.terminal"):mo.index("## How to read this report")]
note = ("Built in two runs because the tool reads one source mode per run: "
        "Light from `latte`, Dark from `mocha`.\n\n")
head = head.replace("## Notes", note + "## Notes", 1)
with open(out + "/report.md", "w", encoding="utf-8") as f:
    f.write(head + dark + "## How to read this report" + tail)
# report.json: Latte theme, then Mocha theme.
a, b = json.loads(rd(scr + "/latte/report.json")), json.loads(rd(scr + "/mocha/report.json"))
a["themes"] += b["themes"]
with open(out + "/report.json", "w", encoding="utf-8") as f:
    json.dump(a, f, indent=1)
    f.write("\n")
# preview.html: add the Mocha section after the Latte section.
pa, pb = rd(scr + "/latte/preview.html"), rd(scr + "/mocha/preview.html")
sec = pb[pb.index("<section>"):pb.index("</section>") + len("</section>")]
mark = pa.index("</section>") + len("</section>")
with open(out + "/preview.html", "w", encoding="utf-8") as f:
    f.write(pa[:mark] + "\n" + sec + pa[mark:])
PYEOF

# Optional: preview.png with headless Chrome (PNG=1).
if [ "${PNG:-0}" = 1 ]; then
  CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
  ROOT="$(pwd)"
  for d in ds2terminal primer carbon catppuccin; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1300,"${HEIGHT:-1950}" \
      --screenshot="$ROOT/themes/$d/preview.png" "file://$ROOT/themes/$d/preview.html" \
      >/dev/null 2>&1 || echo "no PNG for $d"
  done
fi

# The tool keeps a cache of the fetched source files in each output folder. Do not keep it in the gallery.
rm -rf themes/*/.fetch
