"""claudecode.py - how Claude Code draws on a theme. The tables are the theme tables of Claude Code 2.1.323 (read 2026-11-12).

The tables were read from the program file. They were not checked against a running session. The setting
`auto` is not in the tables: it reads the terminal background (OSC 11) and uses the dark theme when it gets
no answer. Terminal 2.15 answers with the theme background (tools/measure/osc11_probe.py), so
`auto` can select the correct mode. The report names `dark` or `light`."""
from . import colorlab as cl

VERSION = "2.1.323"
READABLE = 45.0   # APCA Lc: the lowest value for text that you must read on a colored cell
ANSI_SETTING = {"dark": "dark-ansi", "light": "light-ansi"}
ANSI_LABEL = {"dark": "Dark mode (ANSI colors only)", "light": "Light mode (ANSI colors only)"}
STANDARD_SETTING = {"dark": "dark", "light": "light"}
ELEMENTS = ("text", "secondary", "user_bg", "bash_bg", "diff_added", "diff_removed", "diff_added_word",
            "diff_removed_word", "selection_bg", "claude", "success", "error", "warning", "permission", "plan")
ANSI = {
    "dark": {"text": "brightWhite", "secondary": "white", "user_bg": "brightBlack", "bash_bg": "black",
             "diff_added": "green", "diff_removed": "red", "diff_added_word": "brightGreen",
             "diff_removed_word": "brightRed", "selection_bg": "blue", "claude": "brightRed",
             "success": "brightGreen", "error": "brightRed", "warning": "brightYellow",
             "permission": "brightBlue", "plan": "brightCyan"},
    "light": {"text": "black", "secondary": "brightBlack", "user_bg": "white", "bash_bg": "brightWhite",
              "diff_added": "green", "diff_removed": "red", "diff_added_word": "brightGreen",
              "diff_removed_word": "brightRed", "selection_bg": "cyan", "claude": "brightRed",
              "success": "green", "error": "red", "warning": "yellow", "permission": "blue", "plan": "cyan"},
}
STANDARD = {
    "dark": {"text": "#ffffff", "secondary": "#999999", "user_bg": "#373737", "bash_bg": "#413c41",
             "diff_added": "#225c2b", "diff_removed": "#7a2936", "diff_added_word": "#38a660",
             "diff_removed_word": "#b3596b", "selection_bg": "#264f78", "claude": "#d77757",
             "success": "#4eba65", "error": "#ff6b80", "warning": "#ffc107", "permission": "#b1b9f9",
             "plan": "#48968c"},
    "light": {"text": "#000000", "secondary": "#666666", "user_bg": "#f0f0f0", "bash_bg": "#faf5fa",
              "diff_added": "#69db7c", "diff_removed": "#ffa8b4", "diff_added_word": "#2f9d44",
              "diff_removed_word": "#d1454b", "selection_bg": "#b4d5ff", "claude": "#d77757",
              "success": "#2c7a39", "error": "#ab2b3f", "warning": "#966c1e", "permission": "#5769f7",
              "plan": "#006666"},
}
# (pair name, text element or "faint", background element or "bg")
PAIRS = (("text", "text", "bg"), ("faint text", "faint", "bg"), ("secondary text", "secondary", "bg"),
         ("user message", "text", "user_bg"), ("shell message", "text", "bash_bg"),
         ("added line", "text", "diff_added"), ("removed line", "text", "diff_removed"),
         ("added word", "text", "diff_added_word"), ("removed word", "text", "diff_removed_word"),
         ("selected text", "text", "selection_bg"), ("Claude color", "claude", "bg"),
         ("success", "success", "bg"), ("error", "error", "bg"), ("warning", "warning", "bg"),
         ("permission", "permission", "bg"), ("plan mode", "plan", "bg"))
BODY = ("text", "secondary text", "user message", "shell message", "added line", "removed line", "selected text")


def resolve(rec: dict, kind: str) -> dict:
    """Hex of every Claude Code element for this theme record, plus "bg" (the background slot).
    kind is "ansi" (elements map to the 16 ANSI slots) or "standard" (Claude Code's own colors)."""
    slots = {r["slot"]: r["hex"] for r in rec["slots"]}
    out = {"bg": slots["background"]}
    for el in ELEMENTS:
        if kind == "ansi":
            out[el] = slots[ANSI[rec["mode"]][el]]
        else:
            out[el] = STANDARD[rec["mode"]][el]
    return out


def rows(rec: dict, kind: str) -> list:
    """One row per PAIRS entry: the text and background hex and the absolute Lc of the pair."""
    c = resolve(rec, kind)
    out = []
    for name, txt, on in PAIRS:
        text = cl.faint(c["text"], c["bg"]) if txt == "faint" else c[txt]
        bg = c[on]
        out.append({"pair": name, "text": text, "on": bg, "lc": round(cl.lc_abs(text, bg), 1)})
    return out


def _weakest(table: list) -> dict:
    """The BODY pair with the lowest Lc; the first one wins a tie."""
    body = [r for r in table if r["pair"] in BODY]
    low = min(body, key=lambda r: r["lc"])
    return {"pair": low["pair"], "lc": low["lc"]}


def pairing(rec: dict) -> dict:
    """Both Claude Code themes for this record, their weakest body pairs, and the recommended theme."""
    mode = rec["mode"]
    ansi_rows = rows(rec, "ansi")
    std_rows = rows(rec, "standard")
    ansi_weak = _weakest(ansi_rows)
    std_weak = _weakest(std_rows)
    if ansi_weak["lc"] >= READABLE:
        recommend = "ansi"
        reason = "ANSI theme: the weakest text pair is %s, Lc %.0f" % (ansi_weak["pair"], ansi_weak["lc"])
    elif std_weak["lc"] > ansi_weak["lc"]:
        recommend = "standard"
        reason = ("ANSI theme: %s is Lc %.0f, below 45. Standard theme: the weakest text pair is %s, Lc %.0f"
                  % (ansi_weak["pair"], ansi_weak["lc"], std_weak["pair"], std_weak["lc"]))
    else:
        recommend = "ansi"
        reason = "both themes have a weak pair; ANSI theme: %s is Lc %.0f" % (ansi_weak["pair"], ansi_weak["lc"])
    return {
        "claude_code_version": VERSION,
        "ansi": {"setting": ANSI_SETTING[mode], "label": ANSI_LABEL[mode], "rows": ansi_rows,
                 "weakest": ansi_weak},
        "standard": {"setting": STANDARD_SETTING[mode], "rows": std_rows, "weakest": std_weak},
        "recommend": recommend,
        "reason": reason,
    }


def markdown_lines(p: dict) -> list:
    """Markdown section for a pairing() result, without a trailing blank line."""
    a, s = p["ansi"], p["standard"]
    lines = [
        "### Claude Code",
        "",
        'Claude Code %s draws these pairs. "ANSI theme" is the setting `%s` ("%s"); it uses the 16 colors '
        'of this theme. "Standard theme" is the setting `%s`; it uses its own colors on this '
        'background.' % (p["claude_code_version"], a["setting"], a["label"], s["setting"]),
        "",
        "| Pair | ANSI theme | Lc | Standard theme | Lc |",
        "|---|---|---|---|---|",
    ]
    for ar, sr in zip(a["rows"], s["rows"]):
        lines.append("| %s | `%s` on `%s` | %.1f | `%s` on `%s` | %.1f |"
                     % (ar["pair"], ar["text"], ar["on"], ar["lc"], sr["text"], sr["on"], sr["lc"]))
    if p["recommend"] == "ansi":
        theme = "ANSI theme (`%s`)" % a["setting"]
    else:
        theme = "standard theme (`%s`)" % s["setting"]
    lines.append("")
    lines.append("Recommended Claude Code theme: **%s**. %s." % (theme, p["reason"]))
    return lines


def preview_lines(rec: dict, kind: str, span) -> list:
    """HTML lines for one Claude Code sample. span is preview._span(text, fg=None, bg=None, bold=False)."""
    c = resolve(rec, kind)
    fa = cl.faint(c["text"], c["bg"])
    if kind == "ansi":
        setting = ANSI_SETTING[rec["mode"]]
    else:
        setting = STANDARD_SETTING[rec["mode"]]
    return [
        span("# Claude Code, %s theme (%s)" % ("ANSI" if kind == "ansi" else "standard", setting), c["secondary"]),
        span(" > fix the rounding bug in app.py" + " " * 30, c["text"], c["user_bg"]),
        span("⏺ ", c["claude"]) + span("Update", c["text"], bold=True) + span("(app.py)", c["text"]),
        span("  ⎿  Updated app.py with 1 addition and 1 removal", fa),
        span("     12 ", fa) + span("-    total = ", c["text"], c["diff_removed"])
        + span("price * qty", c["text"], c["diff_removed_word"]) + span("            ", c["text"], c["diff_removed"]),
        span("     12 ", fa) + span("+    total = ", c["text"], c["diff_added"])
        + span("round(price * qty, 2)", c["text"], c["diff_added_word"]) + span("  ", c["text"], c["diff_added"]),
        span("     … +14 lines (ctrl+o to expand)", fa),
        span("⏺ ", c["success"]) + span("Tests pass.  ", c["text"]) + span("warning ", c["warning"])
        + span("error ", c["error"]) + span("permission ", c["permission"]) + span("plan mode", c["plan"]),
        span("  import sys, time    # collapsed preview: faint text", fa),
    ]
