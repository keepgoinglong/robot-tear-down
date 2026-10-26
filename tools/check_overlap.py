#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose the current exploded layout: per-module cascade span, exploded world
bbox, and every still-overlapping pair (with names + volume)."""
import json, math, io, sys

FILE = sys.argv[1] if len(sys.argv) > 1 else '/sessions/sweet-quirky-hypatia/mnt/outputs/机械臂-三维拆解.html'
s = io.open(FILE, encoding='utf-8', errors='surrogateescape').read()
a = s.index('window.ROBOT_META='); b = s.index(';\nwindow.ROBOT_BIN_Z=', a)
meta = json.loads(s[a + len('window.ROBOT_META='):b])
gm = {g['key']: g for g in meta['geoms']}
inst = meta['instances']

def norm(v):
    l = math.sqrt(sum(k * k for k in v)) or 1
    return [k / l for k in v]

def ebox(i):
    d = i['ex']; dd = i['exd']
    return ([i['bboxMin'][k] + d[k] * dd for k in range(3)],
            [i['bboxMax'][k] + d[k] * dd for k in range(3)])

# group by identical dir
groups = {}
for i in inst:
    groups.setdefault(tuple(i['ex']), []).append(i)

print('%-22s %2s  %-9s %-9s %6s %6s' % ('dir', 'n', 'homeSpan', 'distRange', 'spanRed', 'runLen'))
allmn = [1e12] * 3; allmx = [-1e12] * 3
for d, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    dn = norm(d)
    def proj(i, key):
        return sum(i[key][k] * dn[k] for k in range(3))
    home = [proj(i, 'bboxMin') for i in items] + [proj(i, 'bboxMax') for i in items]
    dd = [i['exd'] for i in items]
    ext = [abs(gm[i['geom']]['size'][0] * dn[0]) + abs(gm[i['geom']]['size'][1] * dn[1]) + abs(gm[i['geom']]['size'][2] * dn[2]) for i in items]
    runlen = sum(ext) + 26.0 * len(items)
    print('%-22s %2d  %9.1f %9.1f %6.1f %6.1f' % (str([round(x, 2) for x in d]), len(items),
                                                  max(home) - min(home), max(dd) - min(dd), runlen - (max(home) - min(home)), runlen))
    for i in items:
        B = ebox(i)
        for k in range(3):
            allmn[k] = min(allmn[k], B[0][k]); allmx[k] = max(allmx[k], B[1][k])
print('exploded world bbox %.0f x %.0f x %.0f mm  (home %.0f x %.0f x %.0f)' % (
    allmx[0] - allmn[0], allmx[1] - allmn[1], allmx[2] - allmn[2],
    *[meta['worldBBox']['size'][k] for k in range(3)]))
print('centre offset', [round((allmn[k] + allmx[k]) / 2, 1) for k in range(3)])

ov = []
for ia in range(len(inst)):
    A = ebox(inst[ia])
    for ib in range(ia + 1, len(inst)):
        B = ebox(inst[ib])
        o = [min(A[1][k], B[1][k]) - max(A[0][k], B[0][k]) for k in range(3)]
        if all(v > 0 for v in o):
            ov.append((o[0] * o[1] * o[2], ia, ib, o))
ov.sort(reverse=True)
print('overlapping pairs:', len(ov))
for v, ia, ib, o in ov[:20]:
    print('  %8.0f mm3  %2d %-20s x %2d %-20s ov %s' % (v, ia, inst[ia]['name'][:20], ib, inst[ib]['name'][:20],
                                                         [round(x, 1) for x in o]))