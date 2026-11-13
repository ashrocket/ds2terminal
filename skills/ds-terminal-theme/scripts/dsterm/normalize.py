#!/usr/bin/env python3
"""normalize.py - parse design-token sources into one intermediate JSON ("ds2terminal IR v1").

Stdlib only, Python >= 3.9.  Run as:  /usr/bin/python3 -I normalize.py [-o out.json] [--name N]
                                       [--source URL] [--manifest manifest.json] FILE_OR_DIR ...

Input formats (auto-detected per file):
  JSON  : claude.ai Design System tokens.json, Style-Dictionary-like {tokens:{..}}, W3C DTCG ($value/$type,
          groups, {alias}, $extensions modes incl. carbon.themes / org.primer.overrides / mode),
          DTCG 2025 structured colors {colorSpace, components, alpha, hex}, Style Dictionary (value/type,
          nested or flat, raw.json), Tokens Studio ($themes/$metadata sets, studio.tokens modify),
          Figma Variables REST (meta.variables/variableCollections), Material Theme Builder (schemes),
          Atlassian figma export ({name, tokens:{"Light/x": {value}}}), Adobe Spectrum ("sets"),
          flat {name: color} maps, nested palettes ({hex: ...}).  JSON5 accepted (comments, single
          quotes, unquoted keys, trailing commas).
  CSS   : custom properties, var() chains with fallbacks, light-dark(), color-mix(), @media
          (prefers-color-scheme), [data-theme|data-color-mode|data-*-theme], .dark/.theme-dark/...,
          :root/html/body/:host, Tailwind v4 @theme, p3 overrides under @media (color-gamut: p3) kept
          as alternates, html/body background/color, inline /** descriptions */.
  SCSS / LESS : $var / @var, Sass maps (nested), module refs ns.$x, map.get(), rgba($c, a).
  JS/TS : object literals with string colors, ident[key] / ident.key references, arrays; large
          minified bundles are regex-scanned for CSS-in-JS custom properties and color literals.
  HTML  : inline <style>, style="" custom props, <meta name=theme-color>.
  Android XML <color name=..>.
Unsupported (reported as warnings): YAML, Stylus, relative color syntax, calc() inside colors.
"""
import argparse
import json
import os
import re
import sys
import time

from . import colormath as cm

IR_VERSION = 1

# ---------------------------------------------------------------- naming helpers
FLAVORS = {"latte", "frappe", "macchiato", "mocha"}
DARKISH = {"dark", "night", "dim", "dimmed", "midnight", "mocha", "macchiato", "frappe", "g90", "g100", "oled"}
LIGHTISH = {"light", "day", "latte", "white", "g10", "dawn"}
GENERIC_TAIL = {"color", "colors", "colour", "colours", "theme", "themes", "tokens", "token", "palette",
                "alpha", "vars", "variables", "scheme", "mode", "css", "scss", "min", "values", "meta", "resolved"}
VARIANT_PENALTY = ("high", "contrast", "colorblind", "tritanopia", "protanopia", "deuteranopia", "dimmed",
                   "dim", "wireframe", "legacy", "increased", "future", "test", "unsafe", "experimental",
                   "finesse", "brand", "refresh", "mobile", "alpha", "switch", "medium", "teams", "inverse")
COLORISH = re.compile(r"(colou?r|bg|fg|background|foreground|text|border|primary|secondary|accent|surface|"
                      r"rgb|ring|muted|destructive|card|popover|input|brand|canvas|fill|stroke|ink|tint|shade)",
                      re.I)
NON_COLOR_TYPES = re.compile(r"^(dimension|font|fontfamily|fontweight|fontsize|duration|cubicbezier|number|"
                             r"shadow|boxshadow|border|borderradius|borderwidth|typography|gradient|transition|"
                             r"strokestyle|spacing|sizing|opacity|lineheight|letterspacing|paragraphspacing|"
                             r"textcase|textdecoration|composition|asset|other|string|boolean|radius|size|"
                             r"space|zindex|breakpoint|motion|easing|time|elevation|blur)", re.I)


def camel_split(s):
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)


def norm_mode(m):
    m = camel_split(str(m)).strip().lower()
    m = re.sub(r"[\s_./]+", "-", m)
    return re.sub(r"-+", "-", m).strip("-") or "default"


def normkey(k):
    return re.sub(r"[^a-z0-9]+", "-", camel_split(str(k)).lower()).strip("-")


def mode_kind_from_name(name):
    segs = [s for s in re.split(r"[-_. /]+", camel_split(str(name)).lower()) if s]
    if any(s in DARKISH for s in segs):
        return "dark"
    if any(s in LIGHTISH for s in segs):
        return "light"
    return None


def is_mode_key(k):
    kl = norm_mode(k)
    return bool(re.match(r"^(light|dark)(-|$)", kl)) or kl in FLAVORS


def mode_from_filename(path):
    stem = os.path.basename(path)
    stem = re.sub(r"(\.(json5?|css|scss|sass|less|js|mjs|cjs|ts|tsx|jsx|html?|xml|ya?ml|tokens))+$", "", stem, flags=re.I)
    segs = [x for x in re.split(r"[-_. ]+", camel_split(stem).lower()) if x]
    idx = None
    for i, s in enumerate(segs):
        if s in ("light", "dark") or s in FLAVORS:
            idx = i
            break
    if idx is None:
        return None
    rest = segs[idx:]
    while len(rest) > 1 and rest[-1] in GENERIC_TAIL:
        rest.pop()
    return "-".join(rest)


# ---------------------------------------------------------------- store
class Store(object):
    def __init__(self):
        self.base = {}
        self.over = {}
        self.fonts = []
        self.names = []
        self.formats = []
        self.warnings = []
        self.mode_display = {}
        self.notes = []
        self._idx = {}
        self._suffix = None
        self._roots = None
        self.scoped = {}  # css fallback: selector -> list of (name, raw, file)
        self.literals = []  # css fallback: (mode, selector, property, color literal)

    def add(self, key, raw, mode=None, name=None, path=None, desc=None, file=None, alpha_mul=None,
            typ=None, modify=None, p3=False, fmt=None):
        if key is None or raw is None:
            return
        key = str(key)
        k = key.lstrip("-$@") if key.startswith(("--", "$", "@")) else key
        e = {"key": k, "name": name or k, "path": path or re.split(r"[./]", k), "raw": raw,
             "desc": desc, "file": file, "alpha_mul": alpha_mul, "typ": typ, "modify": modify, "fmt": fmt}
        table = self.base
        if mode:
            m = norm_mode(mode)
            table = self.over.setdefault(m, {})
        if p3:
            prev = table.get(k)
            if prev is not None:
                prev["p3"] = raw
                return
            e["p3"] = raw
        table[k] = e
        self._idx = {}
        self._suffix = None
        self._roots = None

    def ensure_mode(self, m):
        self.over.setdefault(norm_mode(m), {})

    def warn(self, msg):
        if len(self.warnings) < 200:
            self.warnings.append(msg)

    # -------------------------------------------------- lookup
    def _norm_index(self, table):
        idx = self._idx.get(id(table))
        if idx is None:
            idx = {}
            for k, e in table.items():
                idx.setdefault(normkey(k), e)
            self._idx[id(table)] = idx
        return idx

    def _tables(self, mode):
        t = []
        if mode and mode in self.over:
            t.append(self.over[mode])
        if mode and "-" in mode:
            # variant modes inherit from their family: 'dark-dimmed-high-contrast' -> 'dark-dimmed' -> 'dark'
            parts = mode.split("-")
            for i in range(len(parts) - 1, 0, -1):
                parent = "-".join(parts[:i])
                if parent in self.over:
                    t.append(self.over[parent])
        t.append(self.base)
        return t

    def lookup(self, key, mode):
        key = key.strip()
        if key.endswith(".value"):
            key = key[:-6]
        key = key.lstrip("!")
        tables = self._tables(mode)
        for t in tables:
            if key in t:
                return t[key]
        nk = normkey(key)
        for t in tables:
            idx = self._norm_index(t)
            if nk in idx:
                return idx[nk]
        if key.startswith("*."):
            suf = "." + key[2:]
            for t in tables:
                for k, e in t.items():
                    if k.endswith(suf):
                        return e
            return None
        if "." in key:
            root, rest = key.split(".", 1)
            for t in tables:
                for k, e in t.items():
                    if "." in k:
                        r2, rest2 = k.split(".", 1)
                        if rest2 == rest and r2.lower().startswith(root.lower()):
                            return e
            # suffix match on path (e.g. reference written relative to a container)
            suf = "." + key
            for t in tables:
                for k, e in t.items():
                    if k.endswith(suf):
                        return e
        return None

    # -------------------------------------------------- resolution
    def kind_of(self, mode):
        if not mode:
            return "light"
        return mode_kind_from_name(mode) or "light"

    def resolve_key(self, key, mode, stack, memo):
        e = self.lookup(key, mode)
        if e is None:
            return None, None, "unresolved-ref:" + key
        mk = (mode, id(e))
        if mk in memo:
            c, t, r = memo[mk]
            return c, t, r
        if id(e) in stack:
            return None, None, "cycle:" + key
        if len(stack) > 32:
            return None, None, "depth"
        c, t, _alias, r = self.resolve_entry(e, mode, stack + (id(e),), memo)
        memo[mk] = (c, t, r)
        return c, t, r

    def resolve_entry(self, e, mode, stack, memo):
        c, t, alias, r = self.resolve_value(e["raw"], mode, stack, memo, e)
        if c is not None and (e.get("alpha_mul") is not None or e.get("modify")):
            c = dict(c)
            if e.get("alpha_mul") is not None:
                try:
                    c["alpha"] = round(c["alpha"] * float(e["alpha_mul"]), 4)
                except (TypeError, ValueError):
                    pass
            if e.get("modify"):
                c = apply_modify(c, e["modify"], self, mode, stack, memo)
            t = rgba_text(c)
        return c, t, alias, r

    def resolve_value(self, raw, mode, stack, memo, entry=None):
        if isinstance(raw, dict):
            c = cm.parse_structured(raw)
            if c is not None:
                return c, rgba_text(c), None, None
            return None, None, None, "not-a-color(object)"
        if isinstance(raw, bool) or raw is None:
            return None, None, None, "not-a-color"
        if isinstance(raw, (int, float)):
            return None, str(raw), None, "not-a-color(number)"
        if isinstance(raw, list):
            return None, ", ".join(str(x) for x in raw), None, "not-a-color(list)"
        s = str(raw).strip()
        s = re.sub(r"\s*!(important|default|global)\s*$", "", s, flags=re.I).strip()
        if not s:
            return None, None, None, "empty"
        ld = re.match(r"^light-dark\((.*)\)$", s, re.S | re.I)
        if ld:
            parts = cm.split_top(ld.group(1))
            if len(parts) == 2:
                s = parts[1] if self.kind_of(mode) == "dark" else parts[0]
        target, fallback = pure_ref(s)
        if target is not None:
            c, t, r = self.resolve_key(target, mode, stack, memo)
            if (c is None and t is None) and fallback is not None:
                c2, t2, _a, r2 = self.resolve_value(fallback, mode, stack, memo, entry)
                return c2, t2, None, r2
            return c, t, target, r
        if re.search(r"var\(|\{[^{}]+\}|\$[\w-]|js:|map[.-]get\(", s) or (entry and entry.get("fmt") == "less" and "@" in s):
            s2, err = self.substitute(s, mode, stack, memo, less=bool(entry and entry.get("fmt") == "less"))
            if err:
                return None, None, None, err
            s = s2
        allow = "both" if (entry is not None and COLORISH.search(entry.get("name") or "")) else "hsl"
        c = cm.parse_color(s, allow_bare=allow)
        if c is None:
            return None, s, None, "not-a-color"
        return c, s, None, None

    def substitute(self, s, mode, stack, memo, less=False):
        err = [None]

        def text_of(key, fb=None):
            c, t, r = self.resolve_key(key, mode, stack, memo)
            if c is None and t is None:
                if fb is not None:
                    c2, t2, _a, r2 = self.resolve_value(fb, mode, stack, memo)
                    if c2 is not None or t2 is not None:
                        return t2 if t2 is not None else rgba_text(c2)
                err[0] = r or ("unresolved-ref:" + key)
                return ""
            if t is not None:
                return t
            return rgba_text(c)

        # var(--x, fallback) with balanced parens
        out, i = [], 0
        while True:
            j = s.find("var(", i)
            if j < 0:
                out.append(s[i:])
                break
            out.append(s[i:j])
            depth, k = 0, j + 3
            while k < len(s):
                if s[k] == "(":
                    depth += 1
                elif s[k] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            inner = s[j + 4:k]
            parts = cm.split_top(inner)
            name = parts[0].strip()
            fb = ",".join(parts[1:]).strip() if len(parts) > 1 else None
            out.append(text_of(name.lstrip("-"), fb))
            i = k + 1
        s = "".join(out)
        s = re.sub(r"\{\s*!?([^{}]+?)\s*\}", lambda m: text_of(m.group(1)), s)
        s = re.sub(r"map[.-]get\(\s*\$([\w-]+)\s*,([^)]*)\)",
                   lambda m: text_of(m.group(1) + "." + ".".join(a.strip().strip("\"'") for a in m.group(2).split(","))), s)
        s = re.sub(r"(?:[A-Za-z_][\w-]*\.)?\$([\w-]+)", lambda m: text_of(m.group(1)), s)
        s = re.sub(r"js:([\w$.\-]+)", lambda m: text_of(m.group(1)), s)
        if less:
            s = re.sub(r"@([\w-]+)", lambda m: text_of(m.group(1)), s)
        return s, err[0]

    # -------------------------------------------------- output
    def resolve_mode(self, mode):
        memo = {}
        keys, seen = [], set()
        for t in reversed(self._tables(mode)):
            for k in t.keys():
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        toks, fails = [], {}
        for k in keys:
            e = self.lookup_exact(k, mode)
            typ = (e.get("typ") or "")
            if typ and NON_COLOR_TYPES.match(typ.replace("-", "").replace("_", "")) and "color" not in typ.lower():
                continue
            if re.match(r"^-*tw-", k):
                continue
            c, t, alias, r = self.resolve_entry(e, mode, (id(e),), memo)
            if c is None:
                reason = (r or "unknown").split(":")[0]
                fails[reason] = fails.get(reason, 0) + 1
                continue
            tok = {"name": e["name"], "path": e["path"], "raw": e["raw"] if isinstance(e["raw"], str) else json.dumps(e["raw"]),
                   "value_srgb": c["hex"], "alpha": c["alpha"]}
            if alias:
                tok["aliasOf"] = alias
            if e.get("desc"):
                tok["description"] = str(e["desc"])[:300]
            if c.get("space") and c["space"] not in ("srgb",):
                tok["space"] = c["space"]
            if c.get("mapped"):
                tok["gamut_mapped"] = True
            if c.get("hex_declared") and c["hex_declared"][:7] != c["hex"]:
                tok["hex_declared"] = c["hex_declared"]
            if e.get("p3"):
                pc = cm.parse_color(e["p3"]) if isinstance(e["p3"], str) else None
                tok["p3_raw"] = e["p3"]
                if pc:
                    tok["p3_srgb"] = pc["hex"]
            if e.get("file"):
                tok["file"] = e["file"]
            toks.append(tok)
        return toks, fails

    def lookup_exact(self, k, mode):
        for t in self._tables(mode):
            if k in t:
                return t[k]
        return None


def rgba_text(c):
    r, g, b = (int(round(v * 255)) for v in c["rgb"])
    if c["alpha"] >= 1:
        return "rgb(%d %d %d)" % (r, g, b)
    return "rgb(%d %d %d / %s)" % (r, g, b, ("%.4f" % c["alpha"]).rstrip("0").rstrip("."))


_PURE = [
    (re.compile(r"^\{\s*!?([^{}]+?)\s*\}$"), None),
    (re.compile(r"^var\(\s*--([\w-]+)\s*(?:,\s*(.*))?\)$", re.S), 2),
    (re.compile(r"^(?:[A-Za-z_][\w-]*\.)?\$([\w-]+)$"), None),
    (re.compile(r"^@([\w-]+)$"), None),
    (re.compile(r"^js:([\w$.\-]+)$"), None),
]


def pure_ref(s):
    for rx, fb in _PURE:
        m = rx.match(s)
        if m:
            if fb and m.group(fb) is not None and "var(" in s[4:] and s.count("(") > 1:
                # fallback may itself contain var(); keep as fallback text
                return m.group(1), m.group(fb)
            return m.group(1), (m.group(fb) if fb else None)
    m = re.match(r"^map[.-]get\(\s*\$([\w-]+)\s*,(.*)\)$", s)
    if m:
        return m.group(1) + "." + ".".join(a.strip().strip("\"'") for a in m.group(2).split(",")), None
    return None, None


def apply_modify(c, mod, store, mode, stack, memo):
    """Tokens Studio $extensions['studio.tokens'].modify (approximation; documented)."""
    try:
        typ = mod.get("type")
        val = float(str(mod.get("value", "0")).strip("%")) / (100.0 if "%" in str(mod.get("value", "")) else 1.0)
        space = (mod.get("space") or "srgb").lower()
        space = {"lch": "oklch", "p3": "display-p3", "hsl": "hsl"}.get(space, space)
        base = cm.to_hex(c["rgb"])
        if typ == "alpha":
            c = dict(c)
            c["alpha"] = round(val, 4)
            return c
        other = None
        if typ == "lighten":
            other = "#ffffff"
        elif typ == "darken":
            other = "#000000"
        elif typ == "mix":
            oc, _t, _a, _r = store.resolve_value(mod.get("color"), mode, stack, memo)
            other = cm.to_hex(oc["rgb"]) if oc else None
        if other:
            mixed = cm.parse_color("color-mix(in %s, %s %s%%, %s)" % (space if space != "display-p3" else "srgb", base, (1 - val) * 100, other))
            if mixed:
                mixed = dict(mixed)
                mixed["alpha"] = c["alpha"]
                return mixed
    except Exception:  # noqa: BLE001 - modifier is best-effort
        pass
    return c


# ---------------------------------------------------------------- JSON family
def json5_to_json(text):
    tok_re = re.compile(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(//[^\n]*|/\*.*?\*/)|([A-Za-z_$][\w$]*)|(\s+)|(.)''', re.S)
    toks = []
    for m in tok_re.finditer(text):
        s, c, ident, ws, o = m.groups()
        if c is not None or ws is not None:
            continue
        if s is not None:
            if s[0] == "'":
                body, out, i = s[1:-1], [], 0
                while i < len(body):
                    ch = body[i]
                    if ch == "\\" and i + 1 < len(body):
                        out.append("'" if body[i + 1] == "'" else body[i:i + 2])
                        i += 2
                        continue
                    out.append('\\"' if ch == '"' else ch)
                    i += 1
                s = '"' + "".join(out) + '"'
            toks.append(("s", s))
        elif ident is not None:
            toks.append(("id", ident))
        else:
            toks.append(("o", o))
    out = []
    for i, (t, v) in enumerate(toks):
        nxt = toks[i + 1][1] if i + 1 < len(toks) else None
        if t == "id":
            if nxt == ":":
                out.append('"%s"' % v)
            elif v in ("true", "false", "null"):
                out.append(v)
            else:
                out.append('"%s"' % v)
        elif t == "o" and v == "," and nxt in ("}", "]"):
            continue
        else:
            out.append(v)
    return "".join(out)


def load_json_text(text):
    try:
        return json.loads(text)
    except ValueError:
        return json.loads(json5_to_json(text))


def is_structured_color(v):
    return isinstance(v, dict) and (("colorSpace" in v and "components" in v) or
                                    (all(k in v for k in ("r", "g", "b")) and all(isinstance(v[k], (int, float)) for k in ("r", "g", "b"))))


TOKEN_META = {"type", "description", "comment", "attributes", "path", "name", "original", "filePath", "isSource",
              "category", "originalValue", "deprecated", "deprecated_comment", "uuid", "$schema", "private",
              "renamed", "themeable", "docs", "id", "group", "state", "introduced", "extensions", "alpha", "usage"}


def is_value_token(node):
    if "value" not in node:
        return False
    v = node["value"]
    if isinstance(v, (str, int, float, list)) or is_structured_color(v):
        return True
    return isinstance(v, dict) and set(node.keys()) <= TOKEN_META | {"value"}


def ext_modes(ext):
    """Return {mode: raw-or-(raw, alpha)} from $extensions holding per-mode values."""
    out = {}
    if not isinstance(ext, dict):
        return out
    for ename, ev in ext.items():
        if not isinstance(ev, dict):
            continue
        en = ename.lower()
        known = en in ("carbon.themes", "org.primer.overrides", "mode", "modes", "com.figma.modes", "themes")
        vals = list(ev.values())
        looks = bool(vals) and all(isinstance(x, str) or (isinstance(x, dict) and ("value" in x or "$value" in x)) for x in vals)
        if known or (looks and any(is_mode_key(k) or mode_kind_from_name(k) for k in ev.keys())):
            for m, v in ev.items():
                if isinstance(v, dict):
                    raw = v.get("$value", v.get("value"))
                    out[m] = (raw, v.get("alpha"))
                else:
                    out[m] = (v, None)
    return out


def walk_tokens(node, path, typ, mode, store, file, depth=0, fmt="dtcg"):
    if isinstance(node, dict):
        ntyp = node.get("$type", typ)
        if "$value" in node or ("$type" in node and ext_modes(node.get("$extensions"))):
            key = ".".join(path)
            desc = node.get("$description")
            ext = node.get("$extensions")
            mod = None
            if isinstance(ext, dict) and isinstance(ext.get("studio.tokens"), dict):
                mod = ext["studio.tokens"].get("modify")
            if "$value" in node:
                store.add(key, node["$value"], mode=mode, path=list(path), desc=desc, file=file, typ=ntyp,
                          alpha_mul=node.get("alpha") if isinstance(node.get("alpha"), (int, float)) else None, modify=mod, fmt=fmt)
            for m, (raw, al) in ext_modes(ext).items():
                store.add(key, raw, mode=m, path=list(path), desc=desc, file=file, typ=ntyp, alpha_mul=al, fmt=fmt)
            return
        if "sets" in node and isinstance(node["sets"], dict) and node["sets"] and all(isinstance(v, dict) for v in node["sets"].values()):
            key = ".".join(path)
            for m, sub in node["sets"].items():
                raw = sub.get("$value", sub.get("value"))
                if raw is None and "sets" in sub:
                    continue
                store.add(key, raw, mode=m, path=list(path), desc=node.get("description"), file=file,
                          typ=schema_type(sub.get("$schema")) or ntyp, fmt="spectrum")
            return
        if "value" in node and is_value_token(node):
            key = ".".join(path)
            attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
            desc = node.get("description") or node.get("comment") or attrs.get("description")
            t = node.get("type") or schema_type(node.get("$schema")) or ntyp
            if isinstance(t, str) and t.lower() == "alias":
                t = None
            if node.get("deprecated") is True and node.get("private") is True:
                pass
            ext = node.get("$extensions")
            mod = ext["studio.tokens"].get("modify") if isinstance(ext, dict) and isinstance(ext.get("studio.tokens"), dict) else None
            store.add(key, node["value"], mode=mode, path=list(path), desc=desc, file=file, typ=t, modify=mod, fmt=fmt)
            return
        if is_structured_color(node) or (isinstance(node.get("hex"), str) and node["hex"].startswith("#")):
            store.add(".".join(path), node, mode=mode, path=list(path), file=file, typ="color", fmt=fmt)
            return
        for k, v in node.items():
            if not isinstance(k, str) or k.startswith("$"):
                continue
            m2, p2 = mode, path + [k]
            if depth <= 2 and isinstance(v, dict) and is_mode_key(k) and not ("$value" in v or "value" in v):
                m2, p2 = norm_mode(k), path
            walk_tokens(v, p2, ntyp, m2, store, file, depth + 1, fmt)
    elif isinstance(node, str):
        if path and (re.match(r"^\{[^{}]+\}$", node) or cm.parse_color(node) is not None):
            if re.fullmatch(r"[0-9a-fA-F]{6}", node):
                return
            if node.strip().lower() in cm.NAMED and (path[-1].lower() in ("name", "title", "label", "id", "emoji", "description", "comment", "displayname")
                                                    or node.strip() != node.strip().lower()):
                return
            store.add(".".join(path), node, mode=mode, path=list(path), file=file, typ=typ, fmt="flat")
    elif isinstance(node, list):
        if typ and "font" in str(typ).lower():
            return
        for i, v in enumerate(node[:256]):
            if isinstance(v, (dict, str)):
                walk_tokens(v, path + [str(i)], typ, mode, store, file, depth + 1, fmt)


def schema_type(s):
    if not isinstance(s, str):
        return None
    m = re.search(r"/([\w-]+)\.json$", s)
    return m.group(1) if m else None


def parse_json_doc(d, store, file, fmode):
    if not isinstance(d, dict):
        if isinstance(d, list):
            walk_tokens(d, [], None, fmode, store, file)
        return "json-list"
    # claude.ai Design System tokens.json
    if isinstance(d.get("color"), dict) and isinstance(d["color"].get("tokens"), list):
        themes = [t for t in (d["color"].get("themes") or []) if isinstance(t, dict) and t.get("id")]
        multi = len(themes) > 1
        for t in themes:
            store.mode_display[norm_mode(t["id"])] = t.get("name") or t["id"]
        nonc = {"type", "spacing", "radius", "shadow", "fontweight", "fontsize", "lineheight", "letterspacing",
                "motion", "duration", "zindex", "breakpoint", "size", "sizing"}
        for fam, block in d.items():
            if not isinstance(block, dict) or not isinstance(block.get("tokens"), list):
                continue
            typ = "color" if fam == "color" else (fam if fam.lower() in nonc else None)
            for tk in block["tokens"]:
                if not isinstance(tk, dict) or "name" not in tk:
                    continue
                val, desc = tk.get("value"), tk.get("usage") or tk.get("description")
                if isinstance(val, dict) and not is_structured_color(val):
                    for tid, v in val.items():
                        store.add(tk["name"], v, mode=(tid if multi else None), desc=desc, file=file, typ=typ, fmt="claude-ds")
                else:
                    store.add(tk["name"], val, mode=fmode, desc=desc, file=file, typ=typ, fmt="claude-ds")
        fam = (d.get("type") or {}).get("families") if isinstance(d.get("type"), dict) else None
        if isinstance(fam, dict):
            for k, v in fam.items():
                store.fonts.append((k, v, file))
        for f in ((d.get("type") or {}).get("fonts") or []) if isinstance(d.get("type"), dict) else []:
            if isinstance(f, dict) and f.get("family"):
                store.fonts.append(("font-face", f["family"], file))
        return "claude-ds-tokens.json"
    # Figma Variables REST
    meta = d.get("meta") if isinstance(d.get("meta"), dict) else d
    if isinstance(meta.get("variables"), dict) and isinstance(meta.get("variableCollections"), dict):
        parse_figma_rest(meta, store, file)
        return "figma-variables-rest"
    # Tokens Studio
    if "$themes" in d or "$metadata" in d:
        parse_tokens_studio(d, store, file)
        return "tokens-studio"
    # Atlassian figma export
    if isinstance(d.get("name"), str) and isinstance(d.get("tokens"), dict) and any("/" in k for k in list(d["tokens"].keys())[:5]):
        mname = d["name"]
        for k, v in d["tokens"].items():
            key = k.split("/", 1)[1] if k.startswith(mname + "/") else k
            if isinstance(v, dict) and "value" in v:
                attrs = v.get("attributes") or {}
                store.add(key, v["value"], mode=mname, desc=attrs.get("description"), file=file, fmt="figma-export")
        return "atlassian-figma-export"
    # Style-Dictionary-like with a 'tokens' container (claude.ai project/tokens/tokens.json)
    if isinstance(d.get("tokens"), dict) and all(isinstance(v, dict) for v in list(d["tokens"].values())[:20]):
        md = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
        if md.get("name"):
            store.names.append(md["name"])
        walk_tokens(d["tokens"], [], None, fmode, store, file, fmt="style-dictionary")
        for fk in ("font", "fonts"):
            if isinstance(d.get(fk), dict):
                for k, v in d[fk].items():
                    store.fonts.append((k, v, file))
        return "style-dictionary(tokens container)"
    # SD raw.json (props/aliases)
    if isinstance(d.get("props"), dict):
        walk_tokens(d["props"], [], None, fmode, store, file, fmt="style-dictionary-raw")
        if isinstance(d.get("aliases"), dict):
            walk_tokens(d["aliases"], [], None, fmode, store, file, fmt="style-dictionary-raw")
        return "style-dictionary-raw"
    fmt = "dtcg" if json_has_key(d, "$value") else ("spectrum" if json_has_key(d, "sets") else "style-dictionary/flat")
    walk_tokens(d, [], None, fmode, store, file, fmt=fmt)
    # document-level mode overrides: {"$extensions": {"<vendor>": {"dark": {<token tree>}}}} (Pidgin)
    ext = d.get("$extensions")
    if isinstance(ext, dict):
        for vendor, ev in ext.items():
            if not isinstance(ev, dict):
                continue
            for mk, tree in ev.items():
                if isinstance(tree, dict) and mode_kind_from_name(mk) and json_has_key(tree, "$value"):
                    walk_tokens(tree, [], None, norm_mode(mk), store, file, fmt="dtcg-ext-mode")
                    store.notes.append("mode '%s' from $extensions.%s" % (norm_mode(mk), vendor))
    if isinstance(d.get("schemes"), dict):
        fmt = "material-theme-builder"
    return fmt


def json_has_key(d, key, depth=0):
    if depth > 6:
        return False
    if isinstance(d, dict):
        if key in d:
            return True
        return any(json_has_key(v, key, depth + 1) for v in list(d.values())[:50])
    return False


def parse_figma_rest(meta, store, file):
    cols = meta["variableCollections"]
    vars_ = meta["variables"]
    names = {vid: v.get("name", vid) for vid, v in vars_.items()}
    for vid, v in vars_.items():
        if v.get("resolvedType") not in ("COLOR", None):
            continue
        col = cols.get(v.get("variableCollectionId"), {})
        modes = {m.get("modeId"): m.get("name") for m in col.get("modes", [])}
        multi = len(modes) > 1
        key = names[vid].replace("/", ".")
        for mid, val in (v.get("valuesByMode") or {}).items():
            if isinstance(val, dict) and val.get("type") == "VARIABLE_ALIAS":
                raw = "{" + names.get(val.get("id"), str(val.get("id"))).replace("/", ".") + "}"
            else:
                raw = val
            store.add(key, raw, mode=(modes.get(mid, mid) if multi else None), desc=v.get("description"),
                      file=file, typ="color", fmt="figma-rest")


def parse_tokens_studio(d, store, file):
    themes = d.get("$themes") or []
    md = d.get("$metadata") if isinstance(d.get("$metadata"), dict) else {}
    order = md.get("tokenSetOrder") or [k for k in d if not k.startswith("$")]
    sets = {k: v for k, v in d.items() if not k.startswith("$") and isinstance(v, dict)}
    used = set()
    if themes:
        groups = {t.get("group") for t in themes if isinstance(t, dict)}
        for th in themes:
            if not isinstance(th, dict):
                continue
            mname = th.get("name") or "theme"
            if len(groups) > 1 and th.get("group"):
                mname = "%s-%s" % (th["group"], mname)
            sel = th.get("selectedTokenSets") or {}
            for sname in order:
                if sel.get(sname) in ("enabled", "source") and sname in sets:
                    used.add(sname)
                    walk_tokens(sets[sname], [], None, mname, store, file, fmt="tokens-studio")
    for sname in order:
        if sname in sets and sname not in used:
            m = None
            last = sname.split("/")[-1]
            if is_mode_key(last) or mode_kind_from_name(last):
                m = last
            walk_tokens(sets[sname], [], None, m, store, file, fmt="tokens-studio")


# ---------------------------------------------------------------- CSS
_STR_OR_COMMENT = re.compile(r'("(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|/\*.*?\*/', re.S)
_STR_OR_COMMENT_LC = re.compile(r'("(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|/\*.*?\*/|(?<![:\\/])//[^\n]*', re.S)
# linear-time: bounded value, unrolled comment body (C9: the old pattern backtracked cubically)
_DESC = re.compile(r"(?<![\w-])(--[\w-]{1,120})[ \t]*:[^;{}]{0,400};[ \t]*/\*+([^*]{0,600}(?:\*+[^*/][^*]{0,600}){0,20})\*+/")
_SIG = re.compile(r"[\"'{};()]")
_ATTR = re.compile(r"\[\s*data-([\w-]+)\s*[~|^$*]?=\s*[\"']?([^\"'\]\s]+)[\"']?\s*(?:[is]\s*)?\]", re.I)
_CLASS = re.compile(r"\.(-?[_a-zA-Z][\w-]*)(?![\w\\-])")
_GLOBAL = re.compile(r"^(?::root|html|:host|body|\*|::?before|::?after|html:root|:where\(:root\)|:is\(:root\)|:where\(html\))$", re.I)


def strip_comments(text, line_comments=False):
    rx = _STR_OR_COMMENT_LC if line_comments else _STR_OR_COMMENT
    return rx.sub(lambda m: m.group(1) if m.group(1) else " ", text)


def class_mode(cls):
    segs = [s for s in re.split(r"[-_]+", camel_split(cls).lower()) if s]
    for i, s in enumerate(segs):
        if s in ("light", "dark") or s in FLAVORS:
            rest = [x for x in segs[i:] if x not in ("theme", "mode", "scheme")]
            return "-".join(rest) or None
    return None


def selector_target(sel):
    nots = re.findall(r":not\(([^()]*(?:\([^()]*\)[^()]*)*)\)", sel)
    s = re.sub(r":not\([^()]*(?:\([^()]*\)[^()]*)*\)", "", sel.strip())
    for nt in nots:
        k, m = selector_target(nt)
        if k == "mode" and m and mode_kind_from_name(m):
            inv = "light" if mode_kind_from_name(m) == "dark" else "dark"
            k2, m2 = selector_target(s)
            if k2 == "global":
                return "mode", inv
    vals = []
    for an, av in _ATTR.findall(s):
        anl = an.lower()
        if any(w in anl for w in ("theme", "mode", "scheme", "appearance")) and not re.search(r"(accent|gray|grey|radius|scaling|panel|font|density|size)", anl):
            if av.lower() in ("auto", "system", "true", "false", "inherit"):
                continue
            prio = 2 if ("theme" in anl and anl != "theme") else 1
            vals.append((prio, av))
    if vals:
        vals.sort(key=lambda t: -t[0])
        return "mode", norm_mode(vals[0][1])
    for cls in _CLASS.findall(s):
        m = class_mode(cls)
        if m:
            return "mode", m
    core = re.sub(r"\s+", " ", _ATTR.sub("", s)).strip()
    if _GLOBAL.match(core) or core == "":
        return "global", None
    parts = [p.strip() for p in re.split(r"\s*,\s*", core)]
    if all(_GLOBAL.match(p) for p in parts if p):
        return "global", None
    return "scoped", None


class CssCtx(object):
    __slots__ = ("targets", "p3", "skip", "scoped_sel")


def css_context(stack, cache):
    key = tuple(stack)
    if key in cache:
        return cache[key]
    ctx = CssCtx()
    ctx.p3, ctx.skip, ctx.scoped_sel = False, False, None
    media_mode, sel_targets = None, None
    for pre in stack:
        pl = pre.lower().strip()
        if pl.startswith("@media"):
            if "prefers-color-scheme" in pl:
                media_mode = "dark" if re.search(r"prefers-color-scheme\s*:\s*dark", pl) else "light"
                if pl.startswith("@media not"):
                    media_mode = "light" if media_mode == "dark" else "dark"
            elif "color-gamut" in pl and ("p3" in pl or "rec2020" in pl):
                ctx.p3 = True
            elif re.search(r"\bprint\b|forced-colors|prefers-contrast|inverted-colors|monochrome|prefers-reduced-transparency", pl):
                ctx.skip = True
        elif pl.startswith("@supports"):
            if "display-p3" in pl or "rec2020" in pl:
                ctx.p3 = True
        elif pl.startswith("@theme"):
            sel_targets = [None]
        elif pl.startswith(("@layer", "@container", "@scope", "@document", "@starting-style")):
            continue
        elif pl.startswith("@"):
            ctx.skip = True
        else:
            tgts, scoped = [], []
            for sel in [x for x in re.split(r",(?![^()]*\))", pre) if x.strip()]:
                kind, m = selector_target(sel)
                if kind == "mode":
                    tgts.append(m)
                elif kind == "global":
                    tgts.append(None)
                else:
                    scoped.append(sel.strip())
            if tgts:
                if sel_targets is None or sel_targets == [None]:
                    sel_targets = tgts
                else:
                    # nested: keep outer modes, unless outer was global
                    sel_targets = [t for t in sel_targets if t is not None] or tgts
            elif sel_targets is None:
                ctx.scoped_sel = ", ".join(scoped)[:120]
            elif scoped and all(t is None for t in sel_targets):
                ctx.scoped_sel = ", ".join(scoped)[:120]
                sel_targets = None
    if sel_targets is None:
        ctx.targets = None
    else:
        tg = []
        for t in sel_targets:
            if t is None and media_mode:
                t = media_mode
            if t not in tg:
                tg.append(t)
        ctx.targets = tg
    cache[key] = ctx
    return ctx


def walk_css(text, on_decl):
    stack, i, start, paren, n = [], 0, 0, 0, len(text)
    while True:
        m = _SIG.search(text, i)
        if not m:
            break
        c, j = m.group(), m.start()
        if c in "\"'":
            k = j + 1
            while k < n:
                ch = text[k]
                if ch == "\\":
                    k += 2
                    continue
                if ch == c or ch == "\n":
                    break
                k += 1
            i = k + 1
            continue
        if c == "(":
            paren += 1
            i = j + 1
            continue
        if c == ")":
            paren = max(0, paren - 1)
            i = j + 1
            continue
        if paren and c != "}":
            i = j + 1
            continue
        if c == "{":
            stack.append(text[start:j].strip())
            start = i = j + 1
            paren = 0
            continue
        seg = text[start:j]
        _decl(seg, stack, on_decl)
        if c == "}" and stack:
            stack.pop()
        paren = 0
        start = i = j + 1
    _decl(text[start:], stack, on_decl)


def _decl(seg, stack, on_decl):
    seg = seg.strip()
    if not seg or seg.startswith("@") or ":" not in seg:
        return
    prop, val = seg.split(":", 1)
    prop = prop.strip()
    if prop.startswith("--") or prop.lower() in LITERAL_PROPS or prop.lower() in ("font-family", "color-scheme"):
        on_decl(stack, prop, val.strip())


LITERAL_PROPS = {"background", "background-color", "color", "accent-color", "caret-color", "border-color", "border",
                 "fill", "stroke", "outline-color", "text-decoration-color", "border-top-color", "border-bottom-color",
                 "border-left", "border-right", "border-top", "border-bottom"}
_LIT_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\([^()]*\)|color\(display-p3[^()]*\)")


def parse_css_text(text, store, file, fmode, fmt="css", scss_interp=False):
    descs = {}
    for m in _DESC.finditer(text):
        descs[m.group(1)] = m.group(2).strip()[:300]
    clean = strip_comments(text, line_comments=(fmt in ("scss", "less")))
    if scss_interp:
        clean = re.sub(r"#\{([^{}]*)\}", r"\1", clean)
    cache = {}
    counts = {"decl": 0, "scoped": 0}

    def on_decl(stack, prop, val):
        ctx = css_context(stack, cache)
        if ctx.skip:
            return
        if not prop.startswith("--"):
            pl = prop.lower()
            if pl in LITERAL_PROPS and len(store.literals) < 200000 and "var(" not in val:
                sel0 = stack[-1] if stack else ""
                lm = None
                if ctx.targets:
                    lm = next((t for t in ctx.targets if t), None)
                for cm_ in _LIT_COLOR.findall(val):
                    store.literals.append((lm or fmode, sel0[:80], pl, cm_))
            if ctx.targets is None:
                return
            sel = stack[-1].lower() if stack else ""
            if not re.search(r"(^|[\s,])(html|body|:root)\b", sel) and not any(t for t in ctx.targets):
                return
            if pl == "font-family":
                store.fonts.append(("css:" + sel[:40] + " font-family", val, file))
                return
            if pl == "color-scheme":
                store.notes.append("color-scheme: %s (%s)" % (val, sel[:40]))
                return
            if pl in ("background", "background-color"):
                pm = re.search(r"(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb|color|color-mix|light-dark)\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)|var\((?:[^()]|\([^()]*\))*\)|#[0-9a-fA-F]{3,8}\b|\b[a-z]{3,20}\b", val)
                if pm and re.fullmatch(r"[a-z]{3,20}", pm.group(0)) and pm.group(0) not in cm.NAMED:
                    pm = None
                if not pm:
                    return
                val = pm.group(0)
                pname = "page.background"
            elif pl == "color":
                pname = "page.foreground"
            else:
                pname = "page." + pl
            for t in ctx.targets:
                store.add(pname, val, mode=t or fmode, file=file, fmt=fmt, desc="from %s { %s }" % (sel[:60], prop))
            return
        counts["decl"] += 1
        if "light-dark(" in val:
            store.ensure_mode("light")
            store.ensure_mode("dark")
        if ctx.targets is None:
            counts["scoped"] += 1
            if ctx.scoped_sel:
                store.scoped.setdefault(ctx.scoped_sel, []).append((prop, val, file))
            return
        name = prop[2:]
        for t in ctx.targets:
            store.add(prop, val, mode=t or fmode, name=name, path=[name], desc=descs.get(prop), file=file,
                      p3=ctx.p3, fmt=fmt)

    walk_css(clean, on_decl)
    return counts


def promote_scoped(store, file_filter=None):
    """If no global custom properties were found, adopt the scoped selector with most color values."""
    best, best_n = None, 0
    for sel, decls in store.scoped.items():
        n = sum(1 for (_p, v, _f) in decls if cm.parse_color(v) is not None or "var(" in v)
        if n > best_n:
            best, best_n = sel, n
    if best and best_n >= 4:
        for (p, v, f) in store.scoped[best]:
            store.add(p, v, name=p[2:], path=[p[2:]], file=f, fmt="css-scoped", desc="scoped: " + best)
        store.notes.append("no global custom properties; adopted scoped selector '%s' (%d colors)" % (best, best_n))
        return True
    return False


def split_name_axis(store):
    """Catppuccin-style: one block with --ctp-<flavor>-<name>; split by a segment that is a mode word."""
    if store.over or len(store.base) < 12:
        return False
    keys = list(store.base.keys())
    for pos in range(0, 3):
        groups = {}
        for k in keys:
            segs = k.split("-")
            if len(segs) > pos + 1 and (segs[pos] in FLAVORS or segs[pos] in ("light", "dark")):
                groups.setdefault(segs[pos], []).append(k)
        if len(groups) >= 2 and all(len(v) >= 6 for v in groups.values()):
            for g, ks in groups.items():
                for k in ks:
                    e = store.base.pop(k)
                    segs = k.split("-")
                    nk = "-".join(segs[:pos] + segs[pos + 1:])
                    store.add(nk, e["raw"], mode=g, name=nk, path=[nk], desc=e.get("desc"), file=e.get("file"), fmt=e.get("fmt"))
            store.notes.append("modes split from name segment %d: %s" % (pos, sorted(groups)))
            return True
    return False


# ---------------------------------------------------------------- SCSS / LESS
def _read_value(text, i):
    depth, q, j, n = 0, None, i, len(text)
    while j < n:
        ch = text[j]
        if q:
            if ch == "\\":
                j += 2
                continue
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth <= 0 and ch in ";}":
            break
        j += 1
    return text[i:j].strip(), j


def _scss_map_items(inner):
    items = []
    parts = [p for p in cm.split_top(inner) if p.strip()]
    for idx, p in enumerate(parts):
        kv = _split_colon(p)
        if kv is None:
            items.append((str(idx), p.strip()))
        else:
            items.append((kv[0].strip().strip("\"'"), kv[1].strip()))
    return items


def _split_colon(p):
    depth, q = 0, None
    for i, ch in enumerate(p):
        if q:
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and depth == 0:
            return p[:i], p[i + 1:]
    return None


def _emit_scss_value(store, path, val, mode, file, fmt):
    v = re.sub(r"\s*!(default|global)\s*$", "", val).strip()
    if v.startswith("(") and v.endswith(")"):
        inner = v[1:-1].strip()
        while inner.startswith("(") and inner.endswith(")") and _split_colon(inner) is None and len(cm.split_top(inner)) == 1:
            inner = inner[1:-1].strip()
        items = _scss_map_items(inner)
        if items and any(_split_colon(p) for p in cm.split_top(inner) if p.strip()):
            keys = {k for k, _ in items}
            if keys and keys <= {"name", "variant"}:
                d = dict(items)
                ref = "{*.%s.%s}" % (d.get("name", "").strip("\"'"), d.get("variant", "primary").strip("\"'"))
                store.add(".".join(path), ref, mode=mode, path=list(path), file=file, fmt=fmt)
                return
            for k, sub in items:
                _emit_scss_value(store, path + [k], sub, mode, file, fmt)
            return
    if v in ("false", "null", "true"):
        return
    store.add(".".join(path), v, mode=mode, path=list(path), file=file, fmt=fmt)


def parse_scss_text(text, store, file, fmode, fmt="scss"):
    clean = strip_comments(text, line_comments=True)
    n = 0
    rx = re.compile(r"(?:^|(?<=[;{}\n]))\s*\$([\w-]+)\s*:" if fmt == "scss" else r"(?:^|(?<=[;{}\n]))\s*@([\w-]+)\s*:(?!\s*\()")
    for m in rx.finditer(clean):
        val, _end = _read_value(clean, m.end())
        if not val:
            continue
        if fmt == "less" and m.group(1) in ("media", "import", "font-face", "supports", "plugin"):
            continue
        _emit_scss_value(store, [m.group(1)], val, fmode, file, fmt)
        n += 1
    c = parse_css_text(text, store, file, fmode, fmt=fmt, scss_interp=True)
    return n + c["decl"]


# ---------------------------------------------------------------- JS / TS
_JS_TOK = re.compile(r'''(\s+)|(//[^\n]*)|(/\*.*?\*/)|("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|(`(?:\\.|[^`\\])*`)|(\d+(?:\.\d+)?)|([A-Za-z_$][\w$]*)|(=>|\.\.\.|[{}\[\]():,;=.?!<>+\-*/%&|^~])''', re.S)


def parse_js_text(text, store, file, fmode):
    if len(text) > 400000 or (text.count("\n") < len(text) / 2000):
        return parse_js_bundle(text, store, file, fmode)
    toks = []
    for m in _JS_TOK.finditer(text):
        ws, lc, bc, s, tpl, num, ident, p = m.groups()
        if ws or lc or bc:
            continue
        if s is not None:
            toks.append(("s", s[1:-1]))
        elif tpl is not None:
            toks.append(("t", tpl[1:-1]))
        elif num is not None:
            toks.append(("n", num))
        elif ident is not None:
            toks.append(("i", ident))
        else:
            toks.append(("p", p))
    stack, pending, count = [], None, 0
    i, n = 0, len(toks)

    def cur_path():
        return [f[1] for f in stack if f[1] is not None]

    while i < n:
        t, v = toks[i]
        nt = toks[i + 1] if i + 1 < n else ("", "")
        if t == "t" and "--" in v and ":" in v:
            parse_css_text(v.replace("\\n", "\n"), store, file, fmode, fmt="css-in-js")
        if t == "p" and v in "{[(":
            stack.append((v, pending if v != "(" else None, [0]))
            if v != "(":
                pending = None
            i += 1
            continue
        if t == "p" and v in "}])":
            if stack:
                stack.pop()
            i += 1
            continue
        if t == "p" and v in ",;":
            if v == ";":
                pending = None
            if stack and stack[-1][0] == "[":
                stack[-1][2][0] += 1
            i += 1
            continue
        in_obj = bool(stack) and stack[-1][0] == "{"
        if t in ("i", "s", "n") and nt == ("p", ":") and in_obj:
            key = v
            j = i + 2
            vt = toks[j] if j < n else ("", "")
            if vt[0] in ("s",) and (j + 1 >= n or toks[j + 1][1] in (",", "}")):
                if cm.parse_color(vt[1]) is not None:
                    path = cur_path() + [key]
                    store.add(".".join(path), vt[1], mode=fmode, path=path, file=file, fmt="js")
                    count += 1
                i = j + 1
                continue
            if vt[0] == "i":
                ref, k = [vt[1]], j + 1
                while k + 1 < n and ((toks[k] == ("p", ".") and toks[k + 1][0] == "i") or
                                     (toks[k] == ("p", "[") and toks[k + 1][0] in ("n", "s") and k + 2 < n and toks[k + 2] == ("p", "]"))):
                    if toks[k][1] == ".":
                        ref.append(toks[k + 1][1])
                        k += 2
                    else:
                        ref.append(toks[k + 1][1])
                        k += 3
                if len(ref) > 1 and k < n and toks[k][1] in (",", "}"):
                    path = cur_path() + [key]
                    store.add(".".join(path), "js:" + ".".join(ref), mode=fmode, path=path, file=file, fmt="js")
                    count += 1
                    i = k
                    continue
            pending = key
            i += 2
            continue
        if t == "i" and nt == ("p", "="):
            pending = v
            vt = toks[i + 2] if i + 2 < n else ("", "")
            if vt[0] == "s" and cm.parse_color(vt[1]) is not None:
                store.add(v, vt[1], mode=fmode, file=file, fmt="js")
                count += 1
            i += 2
            continue
        if t == "s" and stack and stack[-1][0] == "[" and (nt[1] in (",", "]")):
            if cm.parse_color(v) is not None:
                path = cur_path() + [str(stack[-1][2][0])]
                store.add(".".join(path), v, mode=fmode, path=path, file=file, fmt="js")
                count += 1
        i += 1
    return count


_BUNDLE_OBJ = re.compile(r"""["']?([A-Za-z_$][\w$-]{1,60})["']?\s*:\s*["'](#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\([^)"'\n]{1,80}\))["']""")


def parse_js_bundle(text, store, file, fmode):
    n = 0
    seen = set()
    for m in re.finditer(r"[{;]\s*--[\w-]+\s*:", text):
        a = max(0, m.start() - 4000)
        b = min(len(text), m.end() + 20000)
        q1 = max(text.rfind('"', a, m.start()), text.rfind("'", a, m.start()), text.rfind("`", a, m.start()))
        if q1 < 0 or q1 in seen:
            continue
        seen.add(q1)
        qc = text[q1]
        q2 = text.find(qc, m.end(), b)
        if q2 < 0:
            q2 = b
        frag = text[q1 + 1:q2].replace("\\n", "\n")
        # isolate the CSS: start at the first selector-ish char before the match
        c = parse_css_text(frag, store, file, fmode, fmt="js-bundle-css")
        n += c["decl"]
    names = {}
    for m in _BUNDLE_OBJ.finditer(text):
        names.setdefault(m.group(1), m.group(2))
    if n < 8:
        for k, v in names.items():
            if COLORISH.search(k) or len(names) < 400:
                store.add("js." + k, v, mode=fmode, name=k, file=file, fmt="js-bundle-literal")
                n += 1
    return n


# ---------------------------------------------------------------- HTML / XML
def tag_blocks(text, tag="style"):
    """Bodies of <tag ...>...</tag>, found with str.find (linear time; C9: the regex was quadratic)."""
    low = text.lower()
    out = []
    i = 0
    open_t, close_t = "<" + tag, "</" + tag
    while True:
        a = low.find(open_t, i)
        if a < 0:
            break
        b = low.find(">", a)
        if b < 0:
            break
        c = low.find(close_t, b)
        if c < 0:
            break
        out.append((a, c + len(close_t) + 1, text[b + 1:c]))
        i = c + len(close_t)
    return out


def parse_html_text(text, store, file, fmode):
    n = 0
    for _a, _b, body in tag_blocks(text, "style"):
        n += parse_css_text(body, store, file, fmode, fmt="html-style")["decl"]
    for m in re.finditer(r"""<(?:html|body)[^>]*\sstyle\s*=\s*["']([^"']*)["']""", text, re.I):
        n += parse_css_text(":root{%s}" % m.group(1), store, file, fmode, fmt="html-style-attr")["decl"]
    for m in re.finditer(r"<meta\s[^>]*>", text, re.I):
        tag = m.group(0)
        if re.search(r"""name\s*=\s*["']theme-color["']""", tag, re.I):
            cm_ = re.search(r"""content\s*=\s*["']([^"']+)["']""", tag, re.I)
            md = re.search(r"""media\s*=\s*["']([^"']+)["']""", tag, re.I)
            mode = None
            if md and "prefers-color-scheme" in md.group(1):
                mode = "dark" if "dark" in md.group(1) else "light"
            if cm_:
                store.add("meta.theme-color", cm_.group(1), mode=mode or fmode, file=file, fmt="html-meta",
                          desc="<meta name=theme-color>")
                n += 1
    t = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    if t:
        store.names.append(re.sub(r"\s+", " ", t.group(1)).strip()[:80])
    return n


def parse_android_xml(text, store, file, fmode):
    n = 0
    for m in re.finditer(r"""<(?:color|item)\s+name\s*=\s*["']([^"']+)["'][^>]*>\s*([^<]+?)\s*<""", text):
        v = m.group(2)
        if re.fullmatch(r"#[0-9a-fA-F]{8}", v):  # Android #AARRGGBB
            v = "#" + v[3:] + v[1:3]
        store.add(m.group(1), v, mode=fmode, file=file, fmt="android-xml")
        n += 1
    return n


# ---------------------------------------------------------------- driver
SUPPORTED = (".json", ".json5", ".tokens", ".css", ".scss", ".sass", ".less", ".js", ".mjs", ".cjs", ".ts",
             ".tsx", ".jsx", ".html", ".htm", ".xml")


MAX_FILE_BYTES = 4_000_000


def parse_file(path, store, display=None, force_mode=None):
    display = display or os.path.basename(path)
    if os.path.getsize(path) > MAX_FILE_BYTES:
        store.warn("%s: larger than %d bytes; not read" % (display, MAX_FILE_BYTES))
        store.formats.append({"file": display, "format": "too-large", "new_keys": 0, "filename_mode": None,
                              "bytes": os.path.getsize(path)})
        return "too-large"
    with open(path, "rb") as fh:
        data = fh.read()
    text = data.decode("utf-8", "replace")
    low = path.lower()
    fmode = force_mode or mode_from_filename(display) or mode_from_filename(path)
    t0 = len(store.base) + sum(len(v) for v in store.over.values())
    fmt = None
    try:
        if low.endswith((".json", ".json5", ".tokens")) or (text.lstrip()[:1] in "{[" and not low.endswith((".css", ".scss", ".less", ".js", ".mjs", ".ts", ".html", ".htm"))):
            d = load_json_text(text)
            if isinstance(d, dict):
                for nk in ("name", "title"):
                    if isinstance(d.get(nk), str) and len(d[nk]) < 80 and nk == "title":
                        store.names.append(d[nk])
            fmt = parse_json_doc(d, store, display, fmode)
        elif low.endswith(".css"):
            parse_css_text(text, store, display, fmode)
            fmt = "css"
        elif low.endswith((".scss", ".sass")):
            parse_scss_text(text, store, display, fmode, "scss")
            fmt = "scss"
        elif low.endswith(".less"):
            parse_scss_text(text, store, display, fmode, "less")
            fmt = "less"
        elif low.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")):
            parse_js_text(text, store, display, fmode)
            fmt = "js"
        elif low.endswith((".html", ".htm")):
            parse_html_text(text, store, display, fmode)
            fmt = "html"
        elif low.endswith(".xml"):
            parse_android_xml(text, store, display, fmode)
            fmt = "android-xml"
        elif low.endswith((".yml", ".yaml")):
            store.warn("%s: YAML not supported (stdlib has no YAML parser)" % display)
            fmt = "yaml(unsupported)"
        elif low.endswith(".styl"):
            store.warn("%s: Stylus not supported" % display)
            fmt = "stylus(unsupported)"
        else:
            parse_css_text(text, store, display, fmode)
            fmt = "css(guess)"
    except (ValueError, RecursionError) as ex:
        store.warn("%s: parse error: %s" % (display, (str(ex) or type(ex).__name__)[:160]))
        fmt = "error"
    t1 = len(store.base) + sum(len(v) for v in store.over.values())
    store.formats.append({"file": display, "format": fmt, "new_keys": t1 - t0, "filename_mode": fmode, "bytes": len(data)})
    return fmt


def pick_role(tokens, roles, excl):
    best = None
    for t in tokens:
        if t["alpha"] < 0.9:
            continue
        nm = camel_split(t["name"]).lower()
        segl = [x for x in re.split(r"[^a-z0-9]+", nm) if x]
        segs = set(segl)
        hit = segs & roles
        if not hit:
            continue
        if hit <= {"base", "page", "body"} and segl[-1] not in ("base", "page", "body"):
            continue  # 'base'/'page' only count as a role when they end the name (Catppuccin 'base')
        if segs & excl:
            continue
        score = len(segl) * 2 + len(nm) / 100.0
        if segs & {"default", "primary", "page", "body", "canvas", "app", "main", "1"}:
            score -= 2
        if segl[-1] in roles:
            score -= 3
        if nm.startswith("page."):
            score -= 4
        if best is None or score < best[0]:
            best = (score, t)
    return best[1] if best else None


BG_ROLES = {"bg", "background", "canvas", "surface", "base", "page", "body"}
FG_ROLES = {"fg", "foreground", "text", "ink", "body", "on"}
EXCL = {"hover", "active", "pressed", "selected", "inverse", "inverted", "emphasis", "accent", "brand", "danger",
        "error", "success", "warning", "attention", "info", "overlay", "disabled", "backdrop", "button", "btn",
        "input", "control", "alpha", "transparent", "highlight", "focus", "link", "critical", "caution", "magic",
        "discovery", "neutral-bold", "bold", "strong", "primary-container", "container", "tint", "shadow", "scrim",
        "selection", "tooltip", "badge", "chip", "toast", "banner", "nav", "header", "footer", "sidebar", "code",
        "subtle", "muted", "secondary", "tertiary", "dim", "bright", "variant", "contrast", "on", "ansi", "diff", "mark"}


def classify_mode(name, tokens):
    k = mode_kind_from_name(name)
    if k:
        return k, "name"
    bg = pick_role(tokens, BG_ROLES, EXCL)
    if bg:
        lum = cm.relative_luminance(cm.parse_color(bg["value_srgb"])["rgb"])
        return ("dark" if lum < 0.18 else "light"), "bg:%s=%s" % (bg["name"], bg["value_srgb"])
    fg = pick_role(tokens, FG_ROLES - {"on", "body"}, EXCL - {"on"})
    if fg:
        lum = cm.relative_luminance(cm.parse_color(fg["value_srgb"])["rgb"])
        return ("light" if lum < 0.18 else "dark"), "fg:%s=%s" % (fg["name"], fg["value_srgb"])
    return None, None


def classify_fonts(store):
    mono_hints = re.compile(r"mono|code|consolas|menlo|courier|monaco|sfmono|sf mono|jetbrains|fira code|"
                            r"source code|inconsolata|cascadia|hack|iosevka|ui-monospace|monospace|plex mono|roboto mono|geist mono", re.I)
    out = {"mono": [], "sans": [], "serif": [], "stacks": []}
    for name, val, file in store.fonts:
        if isinstance(val, list):
            fams = [str(x) for x in val]
        elif isinstance(val, str):
            if "var(" in val:
                continue
            fams = [f.strip().strip("\"'") for f in cm.split_top(val) if f.strip()]
        else:
            continue
        if not fams:
            continue
        nm = str(name).lower()
        if mono_hints.search(nm) or mono_hints.search(" ".join(fams[:2])):
            cat = "mono"
        elif "serif" in nm.replace("sans-serif", "") or (fams[-1].lower() == "serif"):
            cat = "serif"
        else:
            cat = "sans"
        out["stacks"].append({"token": name, "category": cat, "families": fams[:12], "file": file})
        for f in fams:
            if f not in out[cat] and len(out[cat]) < 24:
                out[cat].append(f)
    return out


def collect_font_tokens(store):
    for table in [store.base] + list(store.over.values()):
        for k, e in table.items():
            typ = str(e.get("typ") or "").lower().replace("-", "").replace("_", "")
            kl = camel_split(k).lower()
            if typ in ("fontfamily", "fontfamilies") or re.search(r"(^|[-_.])(font-?family|font-families|typeface|font)([-_.]|$)", kl) and \
                    re.search(r"(mono|sans|serif|code|body|heading|display|base|family|ui|text)", kl):
                raw = e["raw"]
                if isinstance(raw, str) and re.search(r"^\s*[\d.]+(px|rem|em)?\s*$|^\d{3}$", raw):
                    continue
                if isinstance(raw, (str, list)):
                    store.fonts.append((e["name"], raw, e.get("file")))


ROLE_SELECTORS = [("link", re.compile(r"(^|[\s,>])a(:link|:visited)?($|[\s,:])"), ("color",)),
                  ("heading", re.compile(r"(^|[\s,>])h[1-3]($|[\s,:])"), ("color",)),
                  ("button", re.compile(r"(^|[\s,>.])(button|btn|cta)", re.I), ("background", "background-color")),
                  ("selection", re.compile(r"::selection"), ("background", "background-color"))]


def literal_palette(store, max_tokens=32):
    """Fallback for sites whose CSS has no colour custom properties: frequency-ranked literal colours plus
    a few role guesses (link, heading, button, selection)."""
    counts, first = {}, {}
    roles = {}
    for mode, sel, prop, lit in store.literals:
        c = cm.parse_color(lit)
        if c is None or c["alpha"] < 0.5:
            continue
        key = (mode, c["hex"])
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, "%s { %s }" % (sel[:50], prop))
        for role, rx, props in ROLE_SELECTORS:
            if prop in props and rx.search(sel) and (mode, role) not in roles:
                roles[(mode, role)] = (lit, sel)
    added = 0
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    for (mode, hx), n in ranked[:max_tokens]:
        store.add("literal.%s" % hx.lstrip("#"), hx, mode=mode, desc="used %d times, e.g. %s" % (n, first[(mode, hx)]), fmt="css-literal")
        added += 1
    for (mode, role), (lit, sel) in roles.items():
        store.add("role.%s" % role, lit, mode=mode, desc="from %s" % sel[:60], fmt="css-literal")
    if added:
        store.notes.append("CSS has few colour custom properties: added %d frequency-ranked literal colours + %d role guesses" % (added, len(roles)))


def build_ir(store, source=None, name=None, elapsed=None):
    split_name_axis(store)
    if not store.base and not store.over and store.scoped:
        promote_scoped(store)
    if store.literals:
        ncolor = sum(1 for t in [store.base] + list(store.over.values()) for e in t.values()
                     if isinstance(e["raw"], str) and (cm.parse_color(e["raw"]) is not None or "var(" in e["raw"]))
        if ncolor < 16:
            literal_palette(store)
    collect_font_tokens(store)
    modes_out = {}
    named = sorted(store.over.keys())
    fails_all = {}
    if not named:
        toks, fails = store.resolve_mode(None)
        modes_out["default"] = toks
        fails_all["default"] = fails
    else:
        for m in named:
            toks, fails = store.resolve_mode(m)
            modes_out[m] = toks
            fails_all[m] = fails
        if store.base:
            btoks, bfails = store.resolve_mode(None)
            bkind, _why = classify_mode("default", btoks)
            kmap = dict((m, classify_mode(m, modes_out[m])[0]) for m in named)
            kinds = set(kmap.values())
            if bkind is None and "dark" in kinds and "light" not in kinds:
                bkind = "light"  # :root defaults + dark overrides: the unscoped base is the light theme
            same = [m for m in named if kmap[m] == bkind]
            plain = [m for m in same if not any(x in VARIANT_PENALTY for x in re.split(r"[-_]", m))]
            if btoks and bkind and not plain:
                nm = bkind if bkind not in modes_out else "default"
                modes_out[nm] = btoks
                fails_all[nm] = bfails
                store.notes.append("base (:root/unscoped) tokens emitted as mode '%s' (classified %s)" % (nm, bkind))
    modes = {}
    for m, toks in modes_out.items():
        kind, why = classify_mode(m, toks)
        modes[m] = {"kind": kind, "kind_basis": why, "display": store.mode_display.get(m, m),
                    "count": len(toks), "unresolved": fails_all.get(m, {}), "tokens": toks}
    preferred = {}
    for kind in ("light", "dark"):
        cands = [m for m, v in modes.items() if v["kind"] == kind and v["count"] > 0]
        if cands:
            def pen(m):
                segs = re.split(r"[-_]", m)
                return (sum(1 for s in segs if s in VARIANT_PENALTY), -modes[m]["count"] // 50, len(m))
            preferred[kind] = sorted(cands, key=pen)[0]
    fonts = classify_fonts(store)
    nm = name or (store.names[0] if store.names else None)
    ir = {"ir_version": IR_VERSION, "source": source or {}, "name": nm, "modes": modes, "preferred": preferred,
          "fonts": fonts, "files": store.formats, "notes": store.notes, "warnings": store.warnings,
          "stats": {"modes": len(modes), "colors_per_mode": {m: v["count"] for m, v in modes.items()},
                    "max_colors": max([v["count"] for v in modes.values()] or [0]),
                    "elapsed_s": round(elapsed, 3) if elapsed is not None else None}}
    return ir


def iter_inputs(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(SUPPORTED + (".yml", ".yaml")):
                        yield os.path.join(root, f), os.path.relpath(os.path.join(root, f), p)
        else:
            yield p, os.path.basename(p)


def dir_modes(displays):
    """Files with the same basename in sibling dirs differing in ONE path segment (themes/g10/x.json,
    themes/white/x.json) -> that segment is the mode."""
    groups = {}
    for p, d in displays.items():
        parts = d.strip("/").split("/")
        if len(parts) >= 2:
            groups.setdefault((len(parts), parts[-1]), []).append((p, parts))
    out = {}
    for (_n, _b), items in groups.items():
        if len(items) < 2:
            continue
        diff = [i for i in range(len(items[0][1]) - 1) if len(set(x[1][i] for x in items)) > 1]
        if len(diff) == 1:
            for p, parts in items:
                out[p] = parts[diff[0]]
    vals = set(out.values())
    for p, d in displays.items():
        if p not in out:
            segs = d.strip("/").split("/")[:-1]
            hit = [x for x in segs if x in vals]
            if len(hit) == 1:
                out[p] = hit[0]
    return out


VARIANT_WORDS = {"high", "contrast", "medium", "low", "dim", "dimmed", "colorblind", "tritanopia", "protanopia",
                 "deuteranopia", "hc", "increased"}


def stem_modes(displays):
    """'_md-sys-color__high-contrast.scss' next to '_md-sys-color.scss' -> mode 'high-contrast'
    (only for contrast/vision variants; light/dark words are handled by mode_from_filename)."""
    def stem(d):
        return re.sub(r"(\.(json5?|css|scss|less|js|mjs|ts|tokens))+$", "", os.path.basename(d), flags=re.I)
    out = {}
    items = [(p, os.path.dirname(d), stem(d)) for p, d in displays.items()]
    stems = {(dr, st) for _p, dr, st in items}
    for p, dr, st in items:
        if mode_from_filename(st):
            continue
        bases = [b for (d2, b) in stems if d2 == dr and b != st and st.startswith(b) and len(b) >= 3]
        if not bases:
            continue
        b = max(bases, key=len)
        segs = [x for x in re.split(r"[-_. ]+", st[len(b):].lower()) if x]
        while segs and segs[-1] in GENERIC_TAIL:
            segs.pop()
        if segs and all(x in VARIANT_WORDS for x in segs):
            out[p] = "-".join(segs)
    return out


def normalize_paths(paths, source=None, name=None, displays=None):
    t0 = time.time()
    store = Store()
    inputs = list(iter_inputs(paths))
    disp_map = {p: ((displays or {}).get(p) or d) for p, d in inputs}
    dmodes = dir_modes(disp_map)
    for p, m in stem_modes(disp_map).items():
        dmodes.setdefault(p, m)
    if dmodes:
        store.notes.append("modes from directory/stem names: %s" % sorted(set(dmodes.values())))
    for p, _d in inputs:
        parse_file(p, store, disp_map[p], force_mode=dmodes.get(p))
    return build_ir(store, source=source, name=name, elapsed=time.time() - t0)


def summary(ir):
    lines = ["name: %s" % ir.get("name"), "files: %s" % ", ".join("%s[%s:%d]" % (f["file"], f["format"], f["new_keys"]) for f in ir["files"])]
    for m, v in ir["modes"].items():
        lines.append("mode %-28s kind=%-5s n=%-5d basis=%s unresolved=%s" % (m, v["kind"], v["count"], v["kind_basis"], v["unresolved"]))
    lines.append("preferred: %s" % ir["preferred"])
    lines.append("fonts: mono=%s sans=%s" % (ir["fonts"]["mono"][:5], ir["fonts"]["sans"][:4]))
    if ir["notes"]:
        lines.append("notes: %s" % ir["notes"][:4])
    if ir["warnings"]:
        lines.append("warnings: %s" % ir["warnings"][:4])
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="*")
    ap.add_argument("-o", "--out")
    ap.add_argument("--name")
    ap.add_argument("--source")
    ap.add_argument("--manifest", help="manifest.json written by fetch_discover.py")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args(argv)
    paths, displays, source, name = list(a.inputs), {}, {"input": a.source} if a.source else {}, a.name
    if a.manifest:
        with open(a.manifest) as fh:
            man = json.load(fh)
        for c in man.get("chosen", []):
            if c.get("local"):
                paths.append(c["local"])
                displays[c["local"]] = c.get("display") or os.path.basename(c["local"])
        source = {"input": man.get("input"), "class": man.get("class"), "urls": [c.get("url") for c in man.get("chosen", [])]}
        name = name or man.get("name")
    if not paths:
        ap.error("no inputs")
    ir = normalize_paths(paths, source=source, name=name, displays=displays)
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(ir, fh, separators=(",", ":"))
    if not a.quiet:
        print(summary(ir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
