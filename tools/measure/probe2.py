"""probe2.py - draws pairs of solid bands in Terminal.app: the left band is a color drawn normally, the
right band is the same color drawn faint (SGR 2). A screenshot then shows how Terminal draws faint text.

usage: python3 -I probe2.py MARKER_FILE
Each band is one row of 18 full-block cells. A row holds two pairs: normal A, faint A, normal B,
faint B. A default-background row separates rows. The driver finds the first and the last band of the
left column and interpolates the rows between. After drawing, it writes MARKER_FILE and waits for one line on stdin.
"""
import sys
import time

E = '\033['
CELLS = 18
GAP = 2
FULL = '█'  # full block: a band of glyph pixels in the text color


def tc(r, g, b):
    return '38;2;%d;%d;%d' % (r, g, b)


def tcbg(r, g, b):
    return '48;2;%d;%d;%d' % (r, g, b)


# (label, SGR codes of the normal band). The faint band adds SGR 2.
PAIRS = [
    ('anchor_top', ''),
    ('fg', ''),
    ('red', '31'), ('green', '32'), ('yellow', '33'), ('blue', '34'), ('magenta', '35'), ('cyan', '36'),
    ('white', '37'), ('brightBlack', '90'), ('brightRed', '91'), ('brightWhite', '97'),
    ('bold_fg', '1'),
    ('tc_ff8800', tc(255, 136, 0)),
    ('tc_ffffff', tc(255, 255, 255)),
    ('tc_808080', tc(128, 128, 128)),
    ('tc_000000', tc(0, 0, 0)),
    ('tc_00ff00', tc(0, 255, 0)),
    # Explicit cell backgrounds: does faint mix toward the cell background or the window background?
    ('tc_ff8800_on_white', tc(255, 136, 0) + ';' + tcbg(255, 255, 255)),
    ('tc_ff8800_on_black', tc(255, 136, 0) + ';' + tcbg(0, 0, 0)),
    ('tc_ffffff_on_black', tc(255, 255, 255) + ';' + tcbg(0, 0, 0)),
    ('tc_000000_on_white', tc(0, 0, 0) + ';' + tcbg(255, 255, 255)),
    ('x256_196', '38;5;196'),
    ('anchor_bottom', ''),
]
assert len(PAIRS) % 2 == 0


def band(codes, faint):
    parts = [c for c in (('2' if faint else ''), codes) if c]
    sgr = (E + ';'.join(parts) + 'm') if parts else ''
    return sgr + FULL * CELLS + E + '0m'


def main():
    marker = sys.argv[1]
    time.sleep(2.0)  # the driver resizes the window first
    out = [E + '2J' + E + 'H', '\n']
    half = len(PAIRS) // 2
    for r in range(half):
        cells = []
        for label, codes in (PAIRS[r], PAIRS[r + half]):
            anchor = label.startswith('anchor')
            cells += [band(codes, False), band(codes, not anchor)]
        out.append((' ' * GAP).join(cells) + '\n')
        out.append('\n')
    sys.stdout.write(''.join(out))
    sys.stdout.flush()
    with open(marker, 'w') as f:
        f.write('ready\n')
    try:
        sys.stdin.readline()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
