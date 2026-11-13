#!/usr/bin/env python3
"""fetch_discover.py - find and download the colour-token files behind any design-system link.

Stdlib only, Python >= 3.9.   /usr/bin/python3 -I fetch_discover.py URL --out DIR [--max-files N]
                                [--budget-mb MB] [--timeout S] [--no-follow] [--quiet]
Writes DIR/manifest.json, DIR/files/* (chosen sources) and DIR/ir.json (normalize.py output).

URL classes: local file/dir, claude.ai artifact (needs Claude's Artifact tool), pidgin (needs MCP),
figma (needs token), github repo/tree/blob, raw.githubusercontent, npm (npmjs.com, unpkg, jsDelivr,
'npm:<pkg>'), jsDelivr gh, direct file URL, generic web page (HTML -> stylesheets -> @import ->
same-origin JS bundles if needed -> linked GitHub/npm source if the page yields too little).
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
import threading
from concurrent.futures import ThreadPoolExecutor

from . import normalize as N

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
      "Version/26.0 Safari/605.1.15 ds2terminal/0.1")
TOKEN_EXT = (".json", ".json5", ".tokens", ".css", ".scss", ".less", ".js", ".mjs", ".cjs", ".ts", ".xml")
EXT_W = {".json": 3.0, ".json5": 2.5, ".tokens": 3.0, ".css": 3.0, ".scss": 1.5, ".less": 1.2, ".js": 0.6,
         ".mjs": 0.6, ".cjs": 0.4, ".ts": 0.4, ".xml": 0.2}
NAME_W = [("token", 3.0), ("colou?rs?", 3.0), ("palette", 2.5), ("theme", 2.0), ("variables?|vars", 2.0),
          ("primitives?", 1.5), ("semantic", 1.5), ("scheme", 1.5), ("sys-colou?r", 2.0), ("(^|[-_.])light([-_.]|$)", 1.0),
          ("(^|[-_.])dark([-_.]|$)", 1.0), ("design-?system", 1.0), ("brand", 0.8), ("alias", 0.8), ("functional", 0.8),
          ("global", 0.5), ("ref-palette", 1.0)]
BAD_PATH = re.compile(r"(^|/)(tests?|__tests__|fixtures?|specs?|examples?|demos?|stories|storybook|\.storybook|"
                      r"__snapshots__|snapshots|node_modules|\.github|\.playwright|playwright|benchmarks?|schemas?|"
                      r"e2e|coverage|scripts|tasks|build-scripts|\.changeset|website|site|apps?/docs|docs?)(/|$)", re.I)
EXCLUDE = re.compile(r"(\.d\.ts|\.map|\.test\.|\.spec\.|\.stories\.|package(-lock)?\.json|tsconfig|eslint|babel|"
                     r"prettier|jest|vite\.config|webpack|rollup|lerna|renovate|composer\.json|manifest\.json|"
                     r"\.lock|yarn|pnpm|turbo\.json|vercel\.json|netlify|license|readme|changelog|\.min\.js$)", re.I)
COLOR_LIT = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b|#[0-9a-fA-F]{3}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(|color\(display-p3")


class Fetcher(object):
    def __init__(self, timeout=15, budget=6_000_000, max_file=2_500_000):
        self.timeout, self.budget, self.max_file = timeout, budget, max_file
        self.used, self.requests, self.cache, self.log = 0, 0, {}, []
        self.lock = threading.Lock()

    def get(self, url, max_bytes=None, accept="*/*", headers=None):
        if url in self.cache:
            return self.cache[url]
        max_bytes = min(max_bytes or self.max_file, self.max_file)
        pu = urllib.parse.urlparse(url)
        host = (pu.hostname or "").lower()
        if pu.scheme not in ("http", "https") or host in ("localhost", "0.0.0.0", "::1") or \
                re.match(r"^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)", host):
            res = (0, {}, b"", url, "refused: only public http(s) URLs are fetched")
            self.log.append({"url": url, "status": 0, "bytes": 0, "error": res[4]})
            return res
        if self.used >= self.budget:
            res = (0, {}, b"", url, "budget exhausted")
            self.log.append({"url": url, "status": 0, "bytes": 0, "error": "budget"})
            return res
        h = {"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip, deflate"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        t0 = time.time()
        with self.lock:
            self.requests += 1
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read(max_bytes + 1)
                enc = (r.headers.get("Content-Encoding") or "").lower()
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                status, final = r.status, r.geturl()
            with self.lock:
                self.used += len(raw)
            trunc = len(raw) > max_bytes
            # bounded decompression (C9: gzip.decompress on a bomb used gigabytes)
            if enc == "gzip":
                raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, max_bytes * 4)
            elif enc == "deflate":
                raw = zlib.decompressobj().decompress(raw, max_bytes * 4)
            err = "truncated at %d bytes" % max_bytes if trunc else None
            res = (status, hdrs, raw[:max_bytes * 4], final, err)
        except urllib.error.HTTPError as ex:
            res = (ex.code, {k.lower(): v for k, v in (ex.headers or {}).items()}, b"", url, "HTTP %d" % ex.code)
        except Exception as ex:  # noqa: BLE001 - network errors are reported, not raised
            res = (0, {}, b"", url, "%s: %s" % (type(ex).__name__, str(ex)[:120]))
        self.log.append({"url": url, "status": res[0], "bytes": len(res[2]), "ms": int((time.time() - t0) * 1000),
                         "error": res[4]})
        self.cache[url] = res
        return res

    def get_json(self, url, headers=None):
        st, _h, body, _f, err = self.get(url, accept="application/json", headers=headers)
        if st != 200:
            return None, err or ("HTTP %s" % st)
        try:
            return json.loads(body.decode("utf-8", "replace")), None
        except ValueError as ex:
            return None, "bad json: %s" % ex


# ---------------------------------------------------------------- classification
def classify(url):
    if os.path.exists(url):
        return {"class": "local", "path": os.path.abspath(url)}
    if url.startswith("npm:"):
        pkg, ver = split_pkg(url[4:])
        return {"class": "npm", "pkg": pkg, "version": ver, "path": None}
    u = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    host, parts = u.netloc.lower(), [p for p in u.path.split("/") if p]
    if host.endswith("claude.ai") and ("artifact" in parts or "design" in parts):
        return {"class": "claude-artifact", "needs_tool": "Artifact(action='list', scope='files', url=...), then Artifact(action='read', "
                "path=...) for project/tokens.json, project/tokens.css and project/tokens/tokens.json if present; "
                "save the files in one folder and pass that folder"}
    if "pidginroost.com" in host or host.startswith("pidgin"):
        return {"class": "pidgin", "needs_tool": "pidgin MCP: pidgin_get_design_system / pidgin_get_artifact"}
    if host.endswith("figma.com"):
        key = parts[1] if len(parts) > 1 else None
        return {"class": "figma", "file_key": key, "needs_tool": "Figma REST GET /v1/files/%s/variables/local with "
                "X-Figma-Token (Variables REST API requires an Enterprise plan); or the Figma MCP" % key}
    if host == "github.com" and len(parts) >= 2:
        o, r = parts[0], parts[1]
        if len(parts) >= 4 and parts[2] in ("tree", "blob"):
            return {"class": "github-" + parts[2], "owner": o, "repo": r, "ref": parts[3], "path": "/".join(parts[4:])}
        return {"class": "github-repo", "owner": o, "repo": r, "ref": None, "path": ""}
    if host == "raw.githubusercontent.com" and len(parts) >= 4:
        return {"class": "file", "url": url, "owner": parts[0], "repo": parts[1], "ref": parts[2], "path": "/".join(parts[3:])}
    if host in ("www.npmjs.com", "npmjs.com") and len(parts) >= 2 and parts[0] == "package":
        name = "/".join(parts[1:3]) if parts[1].startswith("@") else parts[1]
        ver = None
        if "v" in parts:
            i = parts.index("v")
            ver = parts[i + 1] if i + 1 < len(parts) else None
        return {"class": "npm", "pkg": name, "version": ver, "path": None}
    if host == "unpkg.com" or (host == "cdn.jsdelivr.net" and parts and parts[0] == "npm"):
        rest = parts[1:] if host == "cdn.jsdelivr.net" else parts
        if not rest:
            return {"class": "web", "url": url}
        spec = "/".join(rest[:2]) if rest[0].startswith("@") else rest[0]
        sub = rest[2:] if rest[0].startswith("@") else rest[1:]
        pkg, ver = split_pkg(spec)
        path = "/".join(sub)
        if path and os.path.splitext(path)[1].lower() in TOKEN_EXT:
            return {"class": "file", "url": url, "pkg": pkg, "version": ver, "path": path}
        return {"class": "npm", "pkg": pkg, "version": ver, "path": path or None}
    if host == "cdn.jsdelivr.net" and parts and parts[0] == "gh" and len(parts) >= 3:
        o = parts[1]
        r, _, ref = parts[2].partition("@")
        path = "/".join(parts[3:])
        if path and os.path.splitext(path)[1].lower() in TOKEN_EXT:
            return {"class": "file", "url": url, "owner": o, "repo": r, "ref": ref or None, "path": path}
        return {"class": "github-tree", "owner": o, "repo": r, "ref": ref or None, "path": path}
    ext = os.path.splitext(u.path)[1].lower()
    if ext in TOKEN_EXT or ext in (".yml", ".yaml"):
        return {"class": "file", "url": url, "path": u.path}
    return {"class": "web", "url": url}


def split_pkg(spec):
    if spec.startswith("@"):
        scope, _, rest = spec.partition("/")
        name, _, ver = rest.partition("@")
        return scope + "/" + name, (ver or None)
    name, _, ver = spec.partition("@")
    return name, (ver or None)


# ---------------------------------------------------------------- scoring
def name_score(path, size=None):
    pl = path.lower()
    base = os.path.basename(pl)
    ext = os.path.splitext(base)[1]
    if base.endswith(".tokens.json"):
        ext = ".tokens"
    if ext not in EXT_W or EXCLUDE.search(base):
        return None
    if size is not None and (size < 60 or size > 2_500_000):
        return None
    stem = re.sub(r"\.(json5?|css|scss|less|js|mjs|cjs|ts|xml|tokens)$", "", base)
    s = EXT_W[ext]
    for rx, w in NAME_W:
        if re.search(rx, stem):
            s += w
    if BAD_PATH.search(pl):
        s -= 4
    if re.search(r"(^|/)components?/", pl):
        s -= 2
    if re.search(r"(^|/)(functions|mixins|helpers|tools|utils|utilities|plugins|formats|transforms?|build)/", pl):
        s -= 3
    if re.search(r"(^|/)tokens?/", pl):
        s += 0.5
    if re.search(r"legacy|deprecated|compat|unsafe|(^|/)v\d+/|\bold\b|test", pl):
        s -= 2
    if re.search(r"high-?contrast|colorblind|tritanopia|protanopia|deuteranopia|increased-contrast|dimmed|wireframe", pl):
        s -= 1.5
    if re.search(r"(^|/)src/", pl) and ext in (".json", ".json5", ".tokens"):
        s += 0.5
    if re.search(r"(^|/)dist/", pl) and ext in (".css", ".json"):
        s += 0.5
    if "/figma/" in pl:
        s -= 0.5
    if re.search(r"\.min\.", base):
        s -= 0.3
    if re.search(r"(^|/)(esm|cjs|lib-commonjs|umd)/", pl) and ext in (".js", ".mjs", ".cjs"):
        s -= 0.5
    depth = pl.strip("/").count("/")
    s -= 0.15 * max(0, depth - 2)
    if size is not None and 1500 <= size <= 400_000:
        s += 0.5
    return round(s, 2)


def content_score(text):
    ncolor = len(COLOR_LIT.findall(text[:3_000_000]))
    ncustom = len(re.findall(r"--[\w-]+\s*:", text))
    nvalue = len(re.findall(r'["\']?\$value["\']?\s*:', text))
    nsd = len(re.findall(r'"value"\s*:', text))
    nref = len(re.findall(r"\{[\w.-]+\}|var\(--|[\w-]+\.\$[\w-]+|map[.-]get\(", text))
    nsass = len(re.findall(r"(?m)^\s*[$@][\w-]+\s*:", text))
    nref += len(re.findall(r"\b[a-z][A-Za-z]*\[\d+\]|\b[a-z][A-Za-z]*\.(?:shade|tint|primary)\d*\b", text))
    nlogic = len(re.findall(r"@function|@mixin|@if |@each ", text))
    kb = max(1.0, len(text) / 1024.0)
    s = math.log2(1 + ncolor) * 1.2 + math.log2(1 + nref) * 0.6
    if nvalue > 5:
        s += 2
    elif nsd > 5:
        s += 1
    if ncustom > 20 or nsass > 20:
        s += 1
    if (ncolor + nref) / kb < 0.15 and kb > 40:
        s -= 3
    if nlogic > 2 and ncolor < 10:
        s -= 3
    return round(s, 2), {"colors": ncolor, "custom_props": ncustom, "$value": nvalue, "value": nsd, "refs": nref, "sass_vars": nsass}


def ext_family(p):
    e = os.path.splitext(p.lower())[1]
    return {".json5": ".json", ".tokens": ".json", ".mjs": ".js", ".cjs": ".js", ".ts": ".js"}.get(e, e)


def partner_paths(path, all_paths):
    """Mode partner files: swap light<->dark in the file name / directory."""
    out = []
    for a, b in (("light", "dark"), ("dark", "light"), ("Light", "Dark"), ("Dark", "Light")):
        if a in path:
            cand = path.replace(a, b)
            if cand in all_paths and cand != path:
                out.append(cand)
    d, base = os.path.split(path)
    stem, ext = os.path.splitext(base)
    m = re.match(r"^(.*?)[-_.]dark([-_.].*)?$", stem, re.I)
    if m:  # amber-dark.css -> amber.css
        cand = os.path.join(d, m.group(1) + (m.group(2) or "") + ext)
        if cand in all_paths and cand not in out:
            out.append(cand)
    else:
        for sep in ("-", "_", "."):
            cand = os.path.join(d, stem + sep + "dark" + ext)
            if cand in all_paths and cand not in out:
                out.append(cand)
    return out


# ---------------------------------------------------------------- listing sources
def list_npm(f, pkg, ver):
    info = {"pkg": pkg}
    spec = pkg + ("@" + ver if ver else "")
    d, err = f.get_json("https://data.jsdelivr.com/v1/packages/npm/%s/resolved%s" % (pkg, ("?specifier=" + ver) if ver else ""))
    if d and d.get("version"):
        ver = d["version"]
    elif err:
        info["resolve_error"] = err
    info["version"] = ver
    if not ver:
        return info, []
    url = "https://data.jsdelivr.com/v1/packages/npm/%s@%s?structure=flat" % (pkg, ver)
    d, err = f.get_json(url)
    info["listing_url"] = url
    files = []
    if d and isinstance(d.get("files"), list):
        files = [(x["name"].lstrip("/"), x.get("size")) for x in d["files"]]
    else:
        info["listing_error"] = err
        d2, err2 = f.get_json("https://unpkg.com/%s@%s/?meta" % (pkg, ver))
        if d2:
            files = [(x["path"].lstrip("/"), x.get("size")) for x in flatten_unpkg(d2)]
            info["listing_url"] = "https://unpkg.com/%s@%s/?meta" % (pkg, ver)
        else:
            info["listing_error2"] = err2
    info["base"] = "https://cdn.jsdelivr.net/npm/%s@%s/" % (pkg, ver)
    _ = spec
    return info, files


def flatten_unpkg(d):
    if isinstance(d.get("files"), list):
        out = []
        for x in d["files"]:
            if x.get("type") == "directory":
                out.extend(flatten_unpkg(x))
            else:
                out.append(x)
        return out
    return [d] if d.get("path") else []


def list_github(f, owner, repo, ref, subpath=""):
    info = {"repo": "%s/%s" % (owner, repo)}
    hdr = {}
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        hdr["Authorization"] = "Bearer " + tok
    if not ref:
        d, err = f.get_json("https://api.github.com/repos/%s/%s" % (owner, repo), headers=hdr)
        if d and d.get("default_branch"):
            ref = d["default_branch"]
            info["description"] = d.get("description")
        else:
            info["api_error"] = err
    refs = [ref] if ref else ["main", "master"]
    # pin the branch to a commit: jsDelivr's listing for gh/<o>/<r>@<branch> is cached and can be stale
    # (verified: alphagov/govuk-frontend@main listed a file the CDN already 404s); @<sha> is immutable.
    if ref and not re.fullmatch(r"[0-9a-f]{40}", ref):
        st, _h, body, _f, err = f.get("https://api.github.com/repos/%s/%s/commits/%s" % (owner, repo, ref),
                                      accept="application/vnd.github.sha", headers=hdr)
        sha = body.decode("ascii", "replace").strip() if st == 200 else ""
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            info["sha"] = sha
            refs = [sha]
        else:
            info["sha_error"] = err or st
    files = []
    for rf in refs:
        url = "https://data.jsdelivr.com/v1/packages/gh/%s/%s@%s?structure=flat" % (owner, repo, rf)
        d, err = f.get_json(url)
        if d and isinstance(d.get("files"), list):
            files = [(x["name"].lstrip("/"), x.get("size")) for x in d["files"]]
            info.update({"ref": rf, "listing_url": url, "listing_via": "jsdelivr-gh",
                         "base": "https://cdn.jsdelivr.net/gh/%s/%s@%s/" % (owner, repo, rf)})
            break
        info["jsdelivr_error_%s" % rf[:12]] = err
    if not files:
        for rf in refs:
            url = "https://api.github.com/repos/%s/%s/git/trees/%s?recursive=1" % (owner, repo, rf)
            d, err = f.get_json(url, headers=hdr)
            if d and isinstance(d.get("tree"), list):
                files = [(x["path"], x.get("size")) for x in d["tree"] if x.get("type") == "blob"]
                info.update({"ref": rf, "listing_url": url, "listing_via": "github-trees", "truncated": d.get("truncated")})
                break
            info["trees_error_%s" % rf] = err
    info["_all_files"] = files
    if subpath:
        sp = subpath.strip("/") + "/"
        files = [(p, s) for p, s in files if p.startswith(sp) or p == subpath.strip("/")]
    # files are served from the same snapshot as the listing (jsDelivr caches a branch for hours; raw
    # GitHub may already have renamed files -> 404s seen with alphagov/govuk-frontend@main)
    info.setdefault("base", "https://raw.githubusercontent.com/%s/%s/%s/" % (owner, repo, info.get("ref") or refs[0]))
    return info, files


# ---------------------------------------------------------------- discovery core
def safe_name(path):
    """A file name for a fetched path: no folders, no dot names, unique (a short hash of the path)."""
    p = re.sub(r"[^A-Za-z0-9._-]+", "_", path.strip("/"))[-150:].lstrip(".")
    return "%s_%s" % (hashlib.sha1(path.encode("utf-8", "replace")).hexdigest()[:8], p or "index")


def pick_from_listing(f, files, base_url, outdir, max_files, notes, log_cands):
    scored = []
    for p, size in files:
        s = name_score(p, size)
        if s is not None and s > 1.0:
            scored.append((s, p, size))
    scored.sort(key=lambda t: (-t[0], t[1]))
    all_paths = {p for p, _s in files}
    sniffed = []
    top = scored[:16]
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda t: f.get(base_url + urllib.parse.quote(t[1])), top))
    for (s, p, size), (st, _h, body, _fu, err) in zip(top, results):
        if st != 200 or not body:
            log_cands.append({"path": p, "name_score": s, "error": err or st})
            continue
        text = body.decode("utf-8", "replace")
        cs, counts = content_score(text)
        w = 1.0 if s >= 2.5 else 0.5           # weak names (lib.js, chunk-x.css) must not win on content alone
        if ext_family(p) == ".js" and (len(text) > 150_000 or text.count("\n") < len(text) / 2000):
            w *= 0.5                           # bundled/minified JS: scanned, but never preferred
        sniffed.append({"path": p, "size": size, "name_score": s, "content_score": cs, "score": round(s + cs * w, 2),
                        "counts": counts, "body": body})
    for c in sniffed:
        log_cands.append({k: v for k, v in c.items() if k != "body"})
    good = [c for c in sniffed if c["counts"]["colors"] + c["counts"]["refs"] >= 3]
    if not good:
        return []
    good.sort(key=lambda c: -c["score"])
    best = good[0]
    fam = ext_family(best["path"])
    chosen = [best]
    for c in good[1:]:
        if len(chosen) >= max_files:
            break
        if ext_family(c["path"]) == fam and c["score"] >= best["score"] * 0.6:
            chosen.append(c)
    # bulk palette packages: many small sibling files in one directory (e.g. Radix: amber.css, amber-dark.css ...)
    bdir, bext = os.path.dirname(best["path"]), os.path.splitext(best["path"])[1]
    bns = best["name_score"]
    sibs = [(p, sz) for p, sz in files if os.path.dirname(p) == bdir and p.endswith(bext)
            and name_score(p, sz) is not None and name_score(p, sz) >= bns - 1.5]
    if len(sibs) > max_files and sibs and sum((sz or 0) for _p, sz in sibs) / len(sibs) < 8000:
        names = {p for p, _ in sibs}
        keep = [p for p, _ in sibs if not (re.search(r"-alpha\b|-p3\b", p) and re.sub(r"-alpha\b|-p3\b", "", p) in names)]
        keep = sorted(keep)[:96]
        have = {c["path"] for c in chosen}
        todo = [p for p in keep if p not in have]
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda p: f.get(base_url + urllib.parse.quote(p)), todo))
        for p, (st, _h, body, _fu, _e) in zip(todo, res):
            if st == 200 and body:
                chosen.append({"path": p, "body": body, "score": None, "bulk": True})
        notes.append("bulk sibling mode: %d files from %s/ (alpha/p3 variants skipped when a base file exists)" % (len(keep), bdir or "."))
    # add mode partners of chosen files (light<->dark), even if they were not sniffed
    have = {c["path"] for c in chosen}
    todo = []
    for c in list(chosen):
        for pp in partner_paths(c["path"], all_paths):
            if pp not in have and pp not in todo:
                todo.append(pp)
    todo = todo[:max_files]
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda p: f.get(base_url + urllib.parse.quote(p)), todo))
    for pp, (st, _h, body, _fu, _e) in zip(todo, res):
        if st == 200 and body:
            chosen.append({"path": pp, "body": body, "score": None, "partner": True})
            notes.append("added mode partner %s" % pp)
    out = []
    os.makedirs(os.path.join(outdir, "files"), exist_ok=True)
    for c in chosen:
        local = os.path.join(outdir, "files", safe_name(c["path"]))
        with open(local, "wb") as fh:
            fh.write(c["body"])
        out.append({"url": base_url + c["path"], "local": local, "display": c["path"], "bytes": len(c["body"]),
                    "score": c.get("score")})
    return out


def unresolved_count(ir):
    if not ir:
        return 0
    return sum(v["unresolved"].get("unresolved-ref", 0) for v in ir["modes"].values())


def resolve_deps(f, man, chosen, all_files, base, outdir, source, name):
    """Add palette/primitive files that define aliases the chosen files reference but do not define."""
    ir = evaluate(chosen, source, name)
    unres = unresolved_count(ir)
    if not ir or unres <= max(5, 0.05 * ir["stats"]["max_colors"]) or not chosen:
        return chosen, ir
    fam = ext_family(chosen[0].get("display") or chosen[0]["local"])
    have = {c.get("display") for c in chosen}
    cands = []
    for p, sz in all_files:
        if p in have or ext_family(p) != fam:
            continue
        sc = name_score(p, sz)
        if sc is None:
            continue
        if re.search(r"palette|colou?rs?|primitive|base|core|global|ref(erence)?|foundation", os.path.basename(p), re.I):
            sc += 3
        cands.append((sc, p))
    cands.sort(key=lambda t: -t[0])
    todo = [p for _s, p in cands[:8]]
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda p: f.get(base + urllib.parse.quote(p)), todo))
    extra = []
    for p, (st, _h, body, fu, _e) in zip(todo, res):
        if st != 200 or not body:
            continue
        cs, counts = content_score(body.decode("utf-8", "replace"))
        if counts["colors"] < 10:
            continue
        local = os.path.join(outdir, "files", "dep_" + safe_name(p))
        with open(local, "wb") as fh:
            fh.write(body)
        extra.append({"url": fu, "local": local, "display": p, "bytes": len(body), "alias_dep": True})
    if not extra:
        return chosen, ir
    ir2 = evaluate(chosen + extra, source, name)
    if unresolved_count(ir2) < unres:
        man["notes"].append("alias deps: %d unresolved refs -> %d after adding %s" % (unres, unresolved_count(ir2), [e["display"] for e in extra]))
        return chosen + extra, ir2
    return chosen, ir


def evaluate(chosen, source, name):
    paths = [c["local"] for c in chosen]
    displays = {c["local"]: c.get("display") for c in chosen}
    if not paths:
        return None
    return N.normalize_paths(paths, source=source, name=name, displays=displays)


def ir_summary(ir):
    if not ir:
        return {"colors_max": 0}
    return {"colors_max": ir["stats"]["max_colors"],
            "modes": {m: {"kind": v["kind"], "count": v["count"]} for m, v in ir["modes"].items()},
            "preferred": ir["preferred"], "mono_fonts": ir["fonts"]["mono"][:4],
            "formats": sorted(set(x["format"] for x in ir["files"]))}


def discover_listing(f, man, files, base, outdir, max_files):
    log_c = []
    chosen = pick_from_listing(f, files, base, outdir, max_files, man["notes"], log_c)
    man["candidates"] = log_c[:24]
    man["listing_count"] = len(files)
    return chosen


def discover_web(f, url, outdir, man, max_files, follow=True):
    st, hdrs, body, final, err = f.get(url, max_bytes=3_000_000, accept="text/html,*/*")
    if st != 200 or not body:
        man["errors"].append("page: %s" % (err or st))
        return []
    html = body.decode("utf-8", "replace")
    os.makedirs(os.path.join(outdir, "files"), exist_ok=True)
    chosen = []
    lp = os.path.join(outdir, "files", "page.html")
    with open(lp, "wb") as fh:
        fh.write(body)
    chosen.append({"url": final, "local": lp, "display": "page.html", "bytes": len(body)})
    page_origin = urllib.parse.urlparse(final).netloc
    css_urls = []
    for m in re.finditer(r"<link\b[^>]*>", html, re.I):
        tag = m.group(0)
        rel = re.search(r"""rel\s*=\s*["']?([^"'>]+)""", tag, re.I)
        href = re.search(r"""href\s*=\s*["']([^"']+)["']""", tag, re.I)
        if not rel or not href:
            continue
        r = rel.group(1).lower()
        if "stylesheet" in r or ("preload" in r and re.search(r"""as\s*=\s*["']?style""", tag, re.I)):
            css_urls.append(urllib.parse.urljoin(final, href.group(1).replace("&amp;", "&")))
    for m in re.finditer(r"""@import\s+(?:url\()?["']?([^"')\s;]+)""", "\n".join(b for _a, _b, b in N.tag_blocks(html, "style"))):
        css_urls.append(urllib.parse.urljoin(final, m.group(1)))
    seen, n_css = set(), 0
    queue = [u for u in css_urls if not (u in seen or seen.add(u))]
    man["stylesheets_found"] = len(queue)
    while queue and n_css < 12:
        cu = queue.pop(0)
        if re.search(r"fonts\.googleapis\.com|use\.typekit|font-awesome|fontawesome", cu):
            continue
        st, _h, cb, cfinal, cerr = f.get(cu, max_bytes=2_500_000, accept="text/css,*/*")
        if st != 200 or not cb:
            man["errors"].append("css %s: %s" % (cu[:100], cerr or st))
            continue
        n_css += 1
        local = os.path.join(outdir, "files", "css_%02d_%s" % (n_css, safe_name(urllib.parse.urlparse(cu).path)[-60:]))
        if not local.endswith(".css"):
            local += ".css"
        with open(local, "wb") as fh:
            fh.write(cb)
        chosen.append({"url": cfinal, "local": local, "display": os.path.basename(local), "bytes": len(cb)})
        for m in re.finditer(r"""@import\s+(?:url\()?["']?([^"')\s;]+)""", cb.decode("utf-8", "replace")[:200000]):
            iu = urllib.parse.urljoin(cfinal, m.group(1))
            if iu not in seen:
                seen.add(iu)
                queue.append(iu)
    ir = evaluate(chosen, {"input": url}, None)
    n = ir["stats"]["max_colors"] if ir else 0
    stripped = html
    for tg in ("script", "style"):
        parts, last = [], 0
        for a_, b_, _body in N.tag_blocks(stripped, tg):
            parts.append(stripped[last:a_])
            last = b_
        stripped = " ".join(parts + [stripped[last:]])
    text_len = len(re.sub(r"<[^>]{0,2000}>", " ", stripped).split())
    spa = text_len < 150 or bool(re.search(r"""<div[^>]+id=["'](root|app|__next|___gatsby)["'][^>]*>\s*</div>""", html))
    man["page"] = {"words": text_len, "spa_signal": spa, "colors_from_css": n, "stylesheets_fetched": n_css}
    if n < 12 or spa:
        scripts = []
        for m in re.finditer(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""", html, re.I):
            su = urllib.parse.urljoin(final, m.group(1).replace("&amp;", "&"))
            if urllib.parse.urlparse(su).netloc == page_origin or re.search(r"/_next/|/assets/|/static/|/build/", su):
                scripts.append(su)
        scripts.sort(key=lambda s: 0 if re.search(r"app|main|index|theme|layout|entry|_app|framework", s) else 1)
        nb = 0
        for su in scripts[:6]:
            st, _h, jb, jfinal, jerr = f.get(su, max_bytes=3_000_000, accept="*/*")
            if st != 200 or not jb:
                continue
            txt = jb.decode("utf-8", "replace")
            if not re.search(r"--[\w-]+\s*:|#[0-9a-fA-F]{6}", txt):
                continue
            nb += 1
            local = os.path.join(outdir, "files", "js_%02d_%s" % (nb, safe_name(urllib.parse.urlparse(su).path)[-60:]))
            if not local.endswith(".js"):
                local += ".js"
            with open(local, "wb") as fh:
                fh.write(jb)
            chosen.append({"url": jfinal, "local": local, "display": os.path.basename(local), "bytes": len(jb)})
        man["page"]["bundles_scanned"] = nb
    related = []
    for m in re.finditer(r"""href\s*=\s*["'](https?://(?:www\.)?(github\.com/[\w.-]+/[\w.-]+|npmjs\.com/package/(?:@[\w.-]+/)?[\w.-]+))""", html, re.I):
        u = m.group(1).rstrip("/")
        u = re.sub(r"\.git$", "", u)
        if u not in related and not re.search(r"github\.com/(sponsors|orgs|features|about|login|topics|site)/", u):
            related.append(u)
    def rel_score(u):
        tail = u.lower().split("/")[-1]
        sc = 0
        for w, wt in (("token", 4), ("primitive", 4), ("color", 3), ("palette", 3), ("theme", 2), ("design-system", 2),
                      ("design", 1), ("css", 1), ("style", 1), ("ui", 0.5)):
            if w in tail:
                sc += wt
        return sc
    related.sort(key=lambda u: -rel_score(u))
    man["related_sources"] = related[:10]
    return chosen


def discover(url, outdir, max_files=8, budget_mb=6.0, timeout=15, follow=True, depth=0):
    t0 = time.time()
    f = Fetcher(timeout=timeout, budget=int(budget_mb * 1_000_000))
    os.makedirs(outdir, exist_ok=True)
    cls = classify(url)
    man = {"input": url, "class": cls["class"], "resolved": cls, "chosen": [], "notes": [], "errors": [],
           "name": None}
    chosen = []
    try:
        if cls.get("needs_tool"):
            man["needs_tool"] = cls["needs_tool"]
        elif cls["class"] == "local":
            p = cls["path"]
            if os.path.isdir(p):
                files = []
                for root, _d, fs in os.walk(p):
                    for fn in fs:
                        full = os.path.join(root, fn)
                        files.append((os.path.relpath(full, p), os.path.getsize(full)))
                scored = [(name_score(rp, sz), rp) for rp, sz in files]
                scored = [t for t in scored if t[0] is not None]
                scored.sort(key=lambda t: -t[0])
                man["candidates"] = [{"path": rp, "name_score": s} for s, rp in scored[:20]]
                # prefer the claude.ai project layout when present
                layout = ("project/tokens.json", "project/tokens.css", "project/tokens/tokens.json",
                          "tokens.json", "tokens.css", "tokens/tokens.json")
                pref = [rp for rp in layout if os.path.exists(os.path.join(p, rp))]
                picks = pref or [rp for _s, rp in scored[:max_files]]
                chosen = [{"url": "file://" + os.path.join(p, rp), "local": os.path.join(p, rp), "display": rp,
                           "bytes": os.path.getsize(os.path.join(p, rp))} for rp in picks]
                dsj = [os.path.join(p, x) for x in ("design-system.json", "project/design-system.json") if os.path.exists(os.path.join(p, x))]
                if dsj:
                    try:
                        with open(dsj[0]) as fh:
                            man["name"] = json.load(fh).get("title")
                    except ValueError:
                        pass
            else:
                chosen = [{"url": "file://" + p, "local": p, "display": os.path.basename(p), "bytes": os.path.getsize(p)}]
        elif cls["class"] == "file":
            st, _h, body, final, err = f.get(cls["url"])
            if st == 200 and body:
                os.makedirs(os.path.join(outdir, "files"), exist_ok=True)
                local = os.path.join(outdir, "files", safe_name(urllib.parse.urlparse(final).path))
                with open(local, "wb") as fh:
                    fh.write(body)
                chosen = [{"url": final, "local": local, "display": os.path.basename(urllib.parse.urlparse(final).path), "bytes": len(body)}]
                # sibling mode partner for raw file links
                for a, b in (("light", "dark"), ("dark", "light")):
                    if a in final.rsplit("/", 1)[-1]:
                        pu = final[: final.rfind("/") + 1] + final.rsplit("/", 1)[-1].replace(a, b)
                        st2, _h2, b2, f2, _e2 = f.get(pu)
                        if st2 == 200 and b2:
                            l2 = os.path.join(outdir, "files", safe_name(urllib.parse.urlparse(f2).path))
                            with open(l2, "wb") as fh:
                                fh.write(b2)
                            chosen.append({"url": f2, "local": l2, "display": os.path.basename(urllib.parse.urlparse(f2).path), "bytes": len(b2), "partner": True})
                            man["notes"].append("added mode partner " + pu)
            else:
                man["errors"].append("file: %s" % (err or st))
        elif cls["class"] == "npm":
            info, files = list_npm(f, cls["pkg"], cls.get("version"))
            man["listing"] = info
            man["name"] = cls["pkg"]
            if cls.get("path"):
                sp = cls["path"].strip("/") + "/"
                files = [(p, s) for p, s in files if p.startswith(sp)]
            if files:
                chosen = discover_listing(f, man, files, info["base"], outdir, max_files)
                chosen, _ir = resolve_deps(f, man, chosen, files, info["base"], outdir, {"input": url}, man.get("name"))
            else:
                man["errors"].append("npm listing empty: %s" % info)
        elif cls["class"].startswith("github"):
            info, files = list_github(f, cls["owner"], cls["repo"], cls.get("ref"), cls.get("path") or "")
            man["listing"] = {k: v for k, v in info.items() if k != "_all_files"}
            man["name"] = "%s/%s" % (cls["owner"], cls["repo"])
            if cls["class"] == "github-blob" and cls.get("path"):
                files = [(p, s) for p, s in files if p == cls["path"]] or [(cls["path"], None)]
            if files:
                chosen = discover_listing(f, man, files, info["base"], outdir, max_files)
                chosen, _ir = resolve_deps(f, man, chosen, info.get("_all_files") or files, info["base"], outdir, {"input": url}, man.get("name"))
                # published npm package (built dist files) may be better than repo sources
                if follow and depth == 0:
                    st, _h, pj, _fu, _e = f.get(info["base"] + "package.json")
                    try:
                        pkg = json.loads(pj.decode("utf-8", "replace")) if st == 200 else {}
                    except ValueError:
                        pkg = {}
                    if pkg.get("name") and not pkg.get("private"):
                        man["npm_package"] = pkg["name"]
            else:
                man["errors"].append("github listing empty: %s" % info)
        elif cls["class"] == "web":
            chosen = discover_web(f, cls["url"], outdir, man, max_files, follow)
    except Exception as ex:  # noqa: BLE001
        man["errors"].append("exception: %s: %s" % (type(ex).__name__, str(ex)[:200]))
    man["chosen"] = chosen
    ir = None
    try:
        ir = evaluate(chosen, {"input": url, "class": cls["class"], "urls": [c["url"] for c in chosen]}, man.get("name"))
    except Exception as ex:  # noqa: BLE001
        man["errors"].append("normalize exception: %s: %s" % (type(ex).__name__, str(ex)[:200]))
    # a single token file whose aliases point into sibling files (e.g. Carbon dtcg/themes.json -> color-palette.json)
    if ir is not None and cls["class"] == "file":
        unres = sum(v["unresolved"].get("unresolved-ref", 0) for v in ir["modes"].values())
        if unres:
            sib_info, sib_files = None, []
            if cls.get("pkg"):
                sib_info, sib_files = list_npm(f, cls["pkg"], cls.get("version"))
            elif cls.get("owner"):
                sib_info, sib_files = list_github(f, cls["owner"], cls["repo"], cls.get("ref"))
            d = os.path.dirname(cls["path"].strip("/"))
            fam = ext_family(cls["path"])
            sibs = [p for p, sz in sib_files if os.path.dirname(p) == d and ext_family(p) == fam
                    and p != cls["path"].strip("/") and name_score(p, sz) is not None][:8]
            for p in sibs:
                st, _h, body, fu, _e = f.get(sib_info["base"] + urllib.parse.quote(p))
                if st == 200 and body:
                    local = os.path.join(outdir, "files", safe_name(p))
                    with open(local, "wb") as fh:
                        fh.write(body)
                    chosen.append({"url": fu, "local": local, "display": p, "bytes": len(body), "alias_sibling": True})
            if sibs:
                man["notes"].append("%d unresolved aliases: added %d sibling files from %s/" % (unres, len(sibs), d))
                ir = evaluate(chosen, {"input": url, "class": cls["class"], "urls": [c["url"] for c in chosen]}, man.get("name"))
    man["result"] = ir_summary(ir)
    # follow linked/packaged sources when the first pass is thin
    weak = man["result"]["colors_max"] < 24 or not any(v.get("kind") == "dark" for v in (man["result"].get("modes") or {}).values())
    if follow and depth == 0 and weak:
        alt = None
        if cls["class"].startswith("github") and man.get("npm_package"):
            alt = "npm:" + man["npm_package"]
        elif cls["class"] == "web" and man.get("related_sources"):
            alt = man["related_sources"][0]
        if alt:
            sub = discover(alt, os.path.join(outdir, "followed"), max_files, max(1.0, budget_mb - f.used / 1e6), timeout, False, depth + 1)
            man["followed"] = {"input": alt, "result": sub["result"], "seconds": sub["seconds"]}
            better = sub["result"]["colors_max"] > man["result"]["colors_max"] or (
                any(v.get("kind") == "dark" for v in (sub["result"].get("modes") or {}).values()) and sub["result"]["colors_max"] >= 16)
            if better:
                man["notes"].append("using followed source %s" % alt)
                man["chosen_primary"] = man["chosen"]
                man["chosen"] = sub["chosen"]
                man["result"] = sub["result"]
                ir = json.load(open(os.path.join(outdir, "followed", "ir.json"))) if os.path.exists(os.path.join(outdir, "followed", "ir.json")) else ir
                f.requests += sub["http"]["requests"]
                f.used += sub["http"]["bytes"]
    if ir is not None:
        with open(os.path.join(outdir, "ir.json"), "w") as fh:
            json.dump(ir, fh, separators=(",", ":"))
    man["http"] = {"requests": f.requests, "bytes": f.used, "log": f.log[-40:]}
    man["seconds"] = round(time.time() - t0, 2)
    with open(os.path.join(outdir, "manifest.json"), "w") as fh:
        json.dump(man, fh, indent=1)
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-files", type=int, default=8)
    ap.add_argument("--budget-mb", type=float, default=6.0)
    ap.add_argument("--timeout", type=float, default=15)
    ap.add_argument("--no-follow", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    man = discover(a.url, a.out, a.max_files, a.budget_mb, a.timeout, not a.no_follow)
    if not a.quiet:
        print(json.dumps({k: man.get(k) for k in ("input", "class", "needs_tool", "result", "seconds", "errors", "notes")}, indent=1))
        for c in man["chosen"]:
            print("  chosen:", c.get("url"), c.get("bytes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
