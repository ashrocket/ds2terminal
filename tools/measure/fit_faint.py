"""fit_faint.py - fits a model of Terminal.app faint (SGR 2) text to the probe2 results.

usage: python3 -I fit_faint.py RESULT.json [RESULT.json ...]
Each sample is (text color, background, faint color), all as rendered sRGB. Models, per channel c:
  gamma:  out = c + t (bg - c)                        on sRGB-encoded values
  linear: the same on linear-light values
  power:  out = (w c^p + (1 - w) bg^p)^(1/p)          on sRGB-encoded values (p = 1 is gamma)
It prints the best parameters and the error (in 8-bit steps) of each model.
"""
import json
import sys


def rgb(h):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def enc(v):
    v = min(1.0, max(0.0, v))
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def samples(paths):
    out = []
    for path in paths:
        d = json.load(open(path))
        for p in d['pairs']:
            if p['label'].startswith('anchor'):
                continue
            bg = d['background']
            if p['label'].endswith('_on_white'):
                bg = '#ffffff'
            if p['label'].endswith('_on_black'):
                bg = '#000000'
            out.append((d['profile'], p['label'], rgb(p['normal']), rgb(bg), rgb(p['faint'])))
    return out


def m_gamma(c, b, t):
    return c + t * (b - c)


def m_linear(c, b, t):
    return enc(lin(c) + t * (lin(b) - lin(c)))


def m_power(c, b, w, p):
    return (w * c ** p + (1 - w) * b ** p) ** (1.0 / p)


def err(S, f):
    e, worst = [], (0, None)
    for prof, label, c, b, o in S:
        for i in range(3):
            d = abs(f(c[i], b[i]) - o[i]) * 255
            e.append(d)
            if d > worst[0]:
                worst = (d, '%s/%s ch%d' % (prof, label, i))
    return (sum(x * x for x in e) / len(e)) ** 0.5, worst


def main():
    S = samples(sys.argv[1:])
    print('%d samples' % len(S))
    best = min(((err(S, lambda c, b, t=t / 1000.0: m_gamma(c, b, t))[0], t / 1000.0) for t in range(300, 800, 5)))
    print('gamma : t=%.3f rms=%.2f worst=%s' % (best[1], best[0], err(S, lambda c, b: m_gamma(c, b, best[1]))[1]))
    bl = min(((err(S, lambda c, b, t=t / 1000.0: m_linear(c, b, t))[0], t / 1000.0) for t in range(300, 900, 5)))
    print('linear: t=%.3f rms=%.2f worst=%s' % (bl[1], bl[0], err(S, lambda c, b: m_linear(c, b, bl[1]))[1]))
    bp = min(((err(S, lambda c, b, w=w / 1000.0, p=p / 100.0: m_power(c, b, w, p))[0], w / 1000.0, p / 100.0)
              for w in range(250, 600, 5) for p in range(80, 260, 2)))
    print('power : w=%.3f p=%.2f rms=%.2f worst=%s' % (bp[1], bp[2], bp[0],
                                                       err(S, lambda c, b: m_power(c, b, bp[1], bp[2]))[1]))
    print('gamma 0.5 (the old model): rms=%.2f' % err(S, lambda c, b: m_gamma(c, b, 0.5))[0])
    if '-v' in sys.argv:
        for prof, label, c, b, o in S:
            pr = [m_power(c[i], b[i], bp[1], bp[2]) for i in range(3)]
            print('  %-12s %-20s got=%s model=%s' % (prof, label, ['%3d' % round(v * 255) for v in o],
                                                     ['%3d' % round(v * 255) for v in pr]))


if __name__ == '__main__':
    main()
