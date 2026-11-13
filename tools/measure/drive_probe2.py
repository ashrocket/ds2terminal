"""drive_probe2.py - measures how Terminal.app draws faint (SGR 2) text.

It opens ONE new Terminal window (no .terminal import, no preference change), optionally switches that
window only to an installed profile, runs probe2.py in it, captures the window, converts the capture
to sRGB, reads each band, and closes its own window.

usage: python3 -I drive_probe2.py OUT_DIR [PROFILE_NAME]

Safety: it stops when the new tab lands in a window that existed before (window tabbing), so it never
resizes or closes a window that it did not make.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pngpix  # noqa: E402
import probe2  # noqa: E402

SRGB_ICC = '/System/Library/ColorSync/Profiles/sRGB Profile.icc'
COLS = 80
ROWS = len(probe2.PAIRS) + 4


def osa(script, check=True):
    r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError('osascript failed: %s' % r.stderr.strip())
    return r.stdout.strip()


def window_ids():
    out = osa('tell application "Terminal" to get id of every window')
    return set(int(v) for v in re.findall(r'\d+', out))


def px(img, x, y):
    w, h, bpp, rows = img
    o = x * bpp
    return tuple(rows[y][o:o + 3])


def dist(a, b):
    return max(abs(p - q) for p, q in zip(a, b))


def modal(img, x):
    counts = {}
    for y in range(img[1]):
        c = px(img, x, y)
        counts[c] = counts.get(c, 0) + 1
    return max(counts, key=counts.get)


def runs_down(img, x, bg, min_len):
    """Vertical runs at column x that are not the background: [(y0, y1)]."""
    out, start = [], None
    for y in range(img[1]):
        on = dist(px(img, x, y), bg) > 3
        if on and start is None:
            start = y
        if not on and start is not None:
            if y - start >= min_len:
                out.append((start, y))
            start = None
    return out


def solid(img, x, y, r=3):
    """The color at (x, y) and the largest channel difference in the (2r+1) square around it."""
    c = px(img, x, y)
    spread = max(dist(c, px(img, x + dx, y + dy)) for dx in range(-r, r + 1) for dy in range(-r, r + 1))
    return c, spread


def main():
    out_dir = os.path.abspath(sys.argv[1])
    profile = sys.argv[2] if len(sys.argv) > 2 else None
    os.makedirs(out_dir, exist_ok=True)
    marker = os.path.join(out_dir, 'probe.ready')
    errlog = os.path.join(out_dir, 'probe.stderr')
    for p in (marker, errlog):
        if os.path.exists(p):
            os.remove(p)
    before = window_ids()
    cmd = "exec /usr/bin/python3 -I '%s' '%s' 2> '%s'" % (os.path.join(HERE, 'probe2.py'), marker, errlog)
    res = osa('tell application "Terminal" to do script "%s"' % cmd.replace('"', '\\"'))
    m = re.search(r'window id (\d+)', res)
    if not m:
        sys.exit('could not read the window id from: %r' % res)
    wid = int(m.group(1))
    tab = 'selected tab of window id %d' % wid
    if wid in before:
        osa('tell application "Terminal" to do script "x" in %s' % tab, check=False)
        sys.exit('the probe opened as a tab of window %d, which existed before. Stopped; nothing was resized.' % wid)
    if profile:
        osa('tell application "Terminal" to set current settings of %s to settings set "%s"' % (tab, profile))
    osa('tell application "Terminal" to set number of columns of %s to %d' % (tab, COLS))
    osa('tell application "Terminal" to set number of rows of %s to %d' % (tab, ROWS))
    got_rows = int(osa('tell application "Terminal" to get number of rows of %s' % tab))
    if got_rows < ROWS - 2:
        osa('tell application "Terminal" to do script "x" in %s' % tab, check=False)
        time.sleep(3.0)
        if wid in window_ids():
            osa('tell application "Terminal" to close (every window whose id is %d)' % wid, check=False)
        sys.exit('the window has %d rows; the probe needs %d. The screen is too small.' % (got_rows, ROWS))
    t0 = time.time()
    while not os.path.exists(marker):
        if time.time() - t0 > 40:
            hist = osa('tell application "Terminal" to get history of %s' % tab, check=False)
            err = open(errlog).read() if os.path.exists(errlog) else ''
            sys.exit('probe did not report ready in 40 s.\nhistory: %r\nstderr: %r' % (hist[-600:], err[-600:]))
        time.sleep(0.25)
    time.sleep(1.0)
    used_profile = osa('tell application "Terminal" to get name of current settings of %s' % tab, check=False)
    raw = os.path.join(out_dir, 'probe_raw.png')
    srgb = os.path.join(out_dir, 'probe_srgb.png')
    subprocess.run(['screencapture', '-x', '-o', '-l', str(wid), raw], check=True)
    subprocess.run(['sips', '--matchTo', SRGB_ICC, raw, '--out', srgb], capture_output=True, check=True)
    # End the probe. Then close this window if its profile does not close it.
    osa('tell application "Terminal" to do script "x" in %s' % tab, check=False)
    time.sleep(1.5)
    if wid in window_ids():
        osa('tell application "Terminal" to close (every window whose id is %d)' % wid, check=False)

    img = pngpix.read_png(srgb)
    w, h = img[0], img[1]
    step = probe2.CELLS + probe2.GAP
    gap_x = int(w * (probe2.CELLS + probe2.GAP / 2.0) / COLS)
    bg = modal(img, gap_x)
    result = {'window_id': wid, 'profile': used_profile, 'size': [w, h], 'background': '#%02x%02x%02x' % bg,
              'pairs': []}
    xs = [int(w * (k * step + probe2.CELLS / 2.0) / COLS) for k in range(4)]
    runs = runs_down(img, xs[0], bg, min_len=8)
    # The title bar is not the background color: drop a first run that starts at the top edge.
    runs = [r for r in runs if r[0] > 4]
    half = len(probe2.PAIRS) // 2
    if len(runs) < 2:
        sys.exit('could not find the bands (runs: %r)' % runs)
    # On a white background the title bar and the tab bar also give runs: the bands are the last ones.
    if len(runs) > half:
        runs = runs[-half:]
    y_top = (runs[0][0] + runs[0][1]) / 2.0
    y_bot = (runs[-1][0] + runs[-1][1]) / 2.0
    result['rows'] = {'top': runs[0], 'bottom': runs[-1], 'runs_found': len(runs), 'expected': half}
    for i, (label, codes) in enumerate(probe2.PAIRS):
        r, side = i % half, i // half
        y = int(round(y_top + (y_bot - y_top) * r / (half - 1)))
        normal, sn = solid(img, xs[2 * side], y)
        dim, sd = solid(img, xs[2 * side + 1], y)
        result['pairs'].append({'label': label, 'sgr': codes, 'normal': '#%02x%02x%02x' % normal,
                                'faint': '#%02x%02x%02x' % dim, 'spread': [sn, sd]})
    json.dump(result, open(os.path.join(out_dir, 'probe2_result.json'), 'w'), indent=1)
    print('profile=%s background=%s size=%dx%d runs=%d' % (used_profile, result['background'], w, h, len(runs)))
    for p in result['pairs']:
        print('  %-22s normal=%s faint=%s spread=%s' % (p['label'], p['normal'], p['faint'], p['spread']))


if __name__ == '__main__':
    main()
