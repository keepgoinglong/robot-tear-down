#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Explode layout v5 — 方案 C: radial burst from the centre, x2.2, tidied.

  * every part flies along  中心 -> 自身  (y compressed, so the burst stays a
    little wider than tall); mirrored parts therefore get mirrored rays, which
    is what makes the exploded model read as symmetric / coordinated
  * distance = base + K * r  -> the whole machine scales up about its centre
    (K = 0.58 gives roughly x2.2 overall) so it looks like it was blown apart
    from the middle rather than shoved along six axes
  * parts that sit on the same ray and near each other stack in assembly order
    (ascending radius; the outermost travels furthest) so a ray becomes one
    tidy line instead of overlapping shells
  * any remaining interpenetration is repaired by pushing the inner part of the
    pair *further out along its own ray* — outward-only pushes cannot scramble
    the layout, they just widen the burst a little
"""
import json, math, io, sys

FILE = sys.argv[1] if len(sys.argv) > 1 else '/sessions/sweet-quirky-hypatia/mnt/outputs/机械臂-三维拆解.html'
s = io.open(FILE, encoding='utf-8', errors='surrogateescape').read()
a = s.index('window.ROBOT_META='); b = s.index(';\nwindow.ROBOT_BIN_Z=', a)
meta = json.loads(s[a + len('window.ROBOT_META='):b])
gm = {g['key']: g['size'] for g in meta['geoms']}
inst = meta['instances']
WB = meta['worldBBox']
C = [(WB['min'][k] + WB['max'][k]) / 2 for k in range(3)]

YCOMP = 0.66     # flatten the vertical component (burst wider than tall)
K = 0.58         # radial scale -> x2.2 overall
BASE = 12.0
MAXDIST = 170.0
DOT = 0.95       # same-ray threshold
NEAR = 130.0     # ... plus proximity, so a ray is also a local line
GAP = 9.0
LIMB_SNAP = 0.55  # how hard near-vertical rays are nudged to pure +/-Y
LEG_SPREAD = 1.45  # lower-half rays fanned outward
LEG_FLAT = 0.62    # ... and flattened vertically
PINNED = {31}      # 外壳2 stays put: everything else is pulled out of IT
# 用户指定：电池 / K230D / 前盖板 往**后**（-Z）出，不往上
FORCE_DIR = {2: (0, 0.0, -1), 6: (0, 0.0, -1), 28: (0, 0.0, -1)}

def norm(v):
    l = math.sqrt(sum(k * k for k in v)) or 1
    return [k / l for k in v]

def ctr(i):
    return [(i['bboxMin'][k] + i['bboxMax'][k]) / 2 for k in range(3)]

def ray(i):
    if i['_idx'] in FORCE_DIR:
        return norm(list(FORCE_DIR[i['_idx']]))
    c = ctr(i)
    v = [c[0] - C[0], (c[1] - C[1]) * YCOMP, c[2] - C[2]]
    if abs(v[1]) > 0.86 * math.sqrt(sum(k * k for k in v)):
        v[1] += (1 if v[1] > 0 else -1) * LIMB_SNAP * abs(v[1])
    if v[1] < 0:                 # the lower half fans OUT rather than diving
        v[0] *= LEG_SPREAD        # straight down - it keeps the feet clear of
        v[2] *= LEG_SPREAD        # the floor and stops the burst going lanky
        v[1] *= LEG_FLAT
    if math.sqrt(sum(k * k for k in v)) < 1e-6:
        v = [0, 1, 0]
    return norm(v)

def ext_along(i, dn):
    sz = gm[i['geom']]
    return abs(sz[0] * dn[0]) + abs(sz[1] * dn[1]) + abs(sz[2] * dn[2])

def radius(i):
    c = ctr(i)
    return math.sqrt(sum((c[k] - C[k]) ** 2 for k in range(3)))

# ---- base distances: radial scale, then cluster + stack ------------------
for i, it in enumerate(inst):
    it['_idx'] = i
    it['ex'] = [round(x, 4) for x in ray(it)]
    it['exd'] = 0.0 if i in PINNED else round(min(MAXDIST, BASE + K * radius(it)), 2)
    it['_r'] = radius(it)

order = sorted([i for i in range(len(inst)) if i not in PINNED],
               key=lambda i: -max(gm[inst[i]['geom']]))
clusters = []
for i in order:
    r = ray(inst[i]); c = ctr(inst[i])
    best = None
    for cl in clusters:
        d = sum(r[k] * cl['dir'][k] for k in range(3))
        if d < DOT:
            continue
        dist = math.sqrt(sum((c[k] - cl['c'][k]) ** 2 for k in range(3)))
        if dist > NEAR:
            continue
        sc = d - dist / NEAR * 0.4
        if best is None or sc > best[0]:
            best = (sc, cl)
    if best is None:
        clusters.append({'dir': r, 'c': c, 'members': [i]})
    else:
        cl = best[1]
        cl['members'].append(i)
        n = len(cl['members'])
        cl['c'] = [cl['c'][k] + (c[k] - cl['c'][k]) / n for k in range(3)]

for cl in clusters:
    dn = cl['dir']
    ms = cl['members']
    proj = {i: sum(ctr(inst[i])[k] * dn[k] for k in range(3)) for i in ms}
    ms.sort(key=lambda i: proj[i])
    # 1-D packing that keeps the assembly's own spacing: a part only gets pushed
    # out by the amount its neighbour would otherwise still overlap (the leg
    # parts are already 30-40 mm apart at home, so naive size-stacking doubled
    # the leg length)
    rel = {}
    for n, i in enumerate(ms):
        need = 0.0
        for j in ms[:n]:
            sep = (ext_along(inst[i], dn) + ext_along(inst[j], dn)) / 2 + GAP
            need = max(need, rel[j] + sep - (proj[i] - proj[j]))
        rel[i] = max(0.0, need)
        if i not in PINNED:
            inst[i]['exd'] = round(min(MAXDIST, inst[i]['exd'] + rel[i]), 2)
    cl['extra'] = max(rel.values()) if rel else 0.0
    for n, i in enumerate(ms):
        inst[i]['_rank'] = n
        inst[i]['_cl'] = id(cl)

def ebox(i):
    d = i['ex']; dd = i['exd']
    return ([i['bboxMin'][k] + d[k] * dd for k in range(3)],
            [i['bboxMax'][k] + d[k] * dd for k in range(3)])

def overlaps():
    out = []
    for ia in range(len(inst)):
        A = ebox(inst[ia])
        for ib in range(ia + 1, len(inst)):
            B = ebox(inst[ib])
            o = [min(A[1][k], B[1][k]) - max(A[0][k], B[0][k]) for k in range(3)]
            if all(v > 0 for v in o):
                out.append((min(o), ia, ib, o))
    return out

# ---- outward-only repair ------------------------------------------------
# Which of a colliding pair gets pushed matters: pushing the part that is
# already *further out* keeps the assembly order readable (feet below brackets
# below servos).  Pushing the inner one instead would let it overtake its
# neighbour, which is exactly what scrambled the leg stacks before.
def push_part(ia, ib):
    a, b = inst[ia], inst[ib]
    if a.get('_cl') is not None and a.get('_cl') == b.get('_cl'):
        return ia if a['_rank'] > b['_rank'] else ib
    return ia if a['_r'] >= b['_r'] else ib

for p in range(80):
    ov = overlaps()
    if not ov:
        break
    for pen, ia, ib, o in ov:
        k = push_part(ia, ib)
        if k in PINNED:          # never push the fixed shell
            k = ib if k == ia else ia
        inst[k]['exd'] = round(min(MAXDIST + 260, inst[k]['exd'] + pen * 0.75 + 2), 2)

allmn = [1e12] * 3; allmx = [-1e12] * 3
for i in inst:
    B = ebox(i)
    for k in range(3):
        allmn[k] = min(allmn[k], B[0][k]); allmx[k] = max(allmx[k], B[1][k])
ov = overlaps()
print('overlaps left %d  (mm3 %.0f)' % (len(ov), sum(v[0] ** 3 for v in ov)))
print('bbox %.0f x %.0f x %.0f  centre [%.1f %.1f %.1f]   home 206x420x199' % (
    allmx[0] - allmn[0], allmx[1] - allmn[1], allmx[2] - allmn[2],
    (allmn[0] + allmx[0]) / 2, (allmn[1] + allmx[1]) / 2, (allmn[2] + allmx[2]) / 2))
for v, ia, ib, o in sorted(ov, reverse=True)[:10]:
    print('   %6.1f  %2d %-18s x %2d %-18s %s' % (v, ia, inst[ia]['name'][:18], ib, inst[ib]['name'][:18],
                                                  [round(x, 1) for x in o]))
d = [i['exd'] for n, i in enumerate(inst) if n not in PINNED]
print('lowest part y %.0f  (floor at -260)' % allmn[1])
print('travel: min %.0f  mean %.0f  max %.0f   (%d clusters)' % (min(d), sum(d) / len(d), max(d), len(clusters)))
print('sizes %s' % sorted((len(c['members']) for c in clusters), reverse=True))
for cl in sorted(clusters, key=lambda c: -len(c['members']))[:8]:
    print('   ray %-24s n %2d  extra %5.0f  %s' % (
        str([round(x, 2) for x in cl['dir']]), len(cl['members']), cl['extra'],
        [inst[i]['name'][:8] for i in cl['members']]))

s = s[:a] + 'window.ROBOT_META=' + json.dumps(meta, ensure_ascii=False, separators=(',', ':')) + s[b:]
io.open(FILE, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('written')