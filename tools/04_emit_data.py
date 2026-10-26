#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emit the page's embedded data file.

The explode vectors are derived from the *mating geometry* rather than from a
radial fan: for every pair of parts whose boxes touch, the axis with the thinnest
overlap is the direction they come apart along (a cover lifts off its face, a
servo slides out of its mount, a shaft withdraws axially).  Those per-mate axes
are summed with a weight of 1/overlap-thickness so thin faces dominate, and the
travel distance is only as long as needed to clear the immediate neighbours —
thich keeps the exploded assembly compact and readable instead of a spray.
"""
import json, base64, os
import numpy as np

OUT = '/sessions/sweet-quirky-hypatia/mnt/outputs/_robot/'
PAGE = OUT + 'page/'
os.makedirs(PAGE, exist_ok=True)

d = json.load(open(OUT + 'parts.json', encoding='utf-8'))
bb = d['worldBBox']
ctr = np.array([(bb['min'][i] + bb['max'][i]) / 2.0 for i in range(3)])
print('bbox centre', np.round(ctr, 2).tolist())

# ---------- centre everything ----------
# NOTE: the geometry's local bbox is the quantisation frame used by the page to
# decode positions, so it must stay in the part-local frame (NOT recentred).
for g in d['geoms']:
    pass
for ins in d['instances']:
    ins['bboxMin'] = [round(ins['bboxMin'][i] - ctr[i], 4) for i in range(3)]
    ins['bboxMax'] = [round(ins['bboxMax'][i] - ctr[i], 4) for i in range(3)]
    ins['localMin'] = [round(ins['localMin'][i], 4) for i in range(3)]
    ins['localMax'] = [round(ins['localMax'][i], 4) for i in range(3)]
    # only the translation of the three.js matrix may be shifted — touching the
    # rotation entries corrupts the transform (this was a real bug).
    for k in (0, 1, 2):
        ins['mjs'][12 + k] = round(ins['mjs'][12 + k] - ctr[k], 6)
nb = [round(bb['min'][i] - ctr[i], 3) for i in range(3)]
nx = [round(bb['max'][i] - ctr[i], 3) for i in range(3)]
d['worldBBox'] = {'min': nb, 'max': nx, 'size': [round(nx[i] - nb[i], 2) for i in range(3)]}
d['centred'] = True
S = max(d['worldBBox']['size'])

# ---------- mate analysis -> explode axis + travel ----------
P = d['instances']
n = len(P)
MN = np.array([p['bboxMin'] for p in P])
MX = np.array([p['bboxMax'] for p in P])
SZ = MX - MN
GAP = S * 0.012                      # touching tolerance

dirs = np.zeros((n, 3))
wsum = np.zeros(n)
mates = [[] for _ in range(n)]
for i in range(n):
    for j in range(n):
        if i == j:
            continue
        lo = np.maximum(MN[i], MN[j]); hi = np.minimum(MX[i], MX[j])
        gap = np.maximum(lo - hi, 0.0)
        if gap.sum() > GAP:          # not in contact
            continue
        ov = np.maximum(hi - lo, 0.0)
        cand = [k for k in range(3) if ov[k] > 1e-6]
        if not cand:
            continue
        # thinnest overlap = the plane they separate across
        k = min(cand, key=lambda a: ov[a])
        if ov[k] > 0.55 * min(SZ[i][k], SZ[j][k]):
            # deep interlock -> separate along the axis they are most offset on
            k = int(np.argmax(np.abs((MN[i] + MX[i]) / 2 - (MN[j] + MX[j]) / 2 - (SZ[i] + SZ[j]) * 0)))
            dvec = (MN[i] + MX[i]) / 2 - (MN[j] + MX[j]) / 2
            if np.abs(dvec).max() < 1e-6:
                continue
            k = int(np.argmax(np.abs(dvec)))
            sgn = 1 if dvec[k] > 0 else -1
        else:
            sgn = 1 if (MN[i][k] + MX[i][k]) > (MN[j][k] + MX[j][k]) else -1
        v = np.zeros(3); v[k] = sgn
        w = 1.0 / max(ov[k], 0.5)
        dirs[i] += v * w
        wsum[i] += w
        mates[i].append(j)

fallback = 0
for i in range(n):
    if wsum[i] > 1e-9:
        v = dirs[i] / wsum[i]
        ln = np.linalg.norm(v)
        P[i]['ex'] = (v / ln).round(4).tolist() if ln > 1e-6 else [0, 1, 0]
    else:
        c = (MN[i] + MX[i]) / 2
        v = c if np.linalg.norm(c) > S * 0.05 else np.array([0.0, 1.0, 0.0])
        P[i]['ex'] = (v / np.linalg.norm(v)).round(4).tolist()
        fallback += 1

# travel: seed from the immediate neighbours, then iteratively resolve any
# remaining interpenetration by extending the outer part's travel along its axis
EX = np.array([np.array(P[i]['ex']) for i in range(n)])
for i in range(n):
    ax = EX[i]
    far = 0.0
    for j in mates[i]:
        ei = abs(ax @ SZ[i]); ej = abs(ax @ SZ[j])
        pi = ax @ ((MN[i] + MX[i]) / 2); pj = ax @ ((MN[j] + MX[j]) / 2)
        far = max(far, (ei + ej) / 2 + 0.10 * S - abs(pi - pj))
    P[i]['exd'] = max(far, 0.12 * S)

for it in range(40):
    moved = 0
    for i in range(n):
        ai = MN[i] + EX[i] * P[i]['exd']; bi = MX[i] + EX[i] * P[i]['exd']
        for j in range(i + 1, n):
            aj = MN[j] + EX[j] * P[j]['exd']; bj = MX[j] + EX[j] * P[j]['exd']
            ov = np.minimum(bi, bj) - np.maximum(ai, aj)
            if not (ov > 0).all():
                continue
            if float(np.prod(ov)) < (S * 0.04) ** 3:
                continue
            # push each along its own axis enough to separate on the worst axis
            k = int(np.argmin(ov))
            need = ov[k] * (1.05 if ov[k] > 0 else 1)
            pi = EX[i][k]; pj = EX[j][k]
            if abs(pi) >= abs(pj) and abs(pi) > 1e-3:
                P[i]['exd'] = round(P[i]['exd'] + need / abs(pi), 2); moved += 1
            elif abs(pj) > 1e-3:
                P[j]['exd'] = round(P[j]['exd'] + need / abs(pj), 2); moved += 1
            else:
                P[j]['exd'] = round(P[j]['exd'] + need, 2); moved += 1
            ai = MN[i] + EX[i] * P[i]['exd']; bi = MX[i] + EX[i] * P[i]['exd']
    if not moved:
        break
print('interpenetration passes used:', it)

# sanity: no interpenetration once exploded
bad = 0
for i in range(n):
    for j in range(i + 1, n):
        a = MN[i] + np.array(P[i]['ex']) * P[i]['exd']
        b = MX[i] + np.array(P[i]['ex']) * P[i]['exd']
        c = MN[j] + np.array(P[j]['ex']) * P[j]['exd']
        e = MX[j] + np.array(P[j]['ex']) * P[j]['exd']
        ov = np.minimum(b, e) - np.maximum(a, c)
        if (ov > 0).all():
            vol = float(np.prod(ov))
            if vol > (S * 0.04) ** 3:
                bad += 1
print('exploded interpenetrations:', bad)

# ---------- write ----------
blob = open(OUT + 'geoms.bin', 'rb').read()
import zlib
z = zlib.compress(blob, 9)
b64 = base64.b64encode(z).decode('ascii')
print('blob %.2fMB -> zlib %.2fMB' % (len(blob)/1048576, len(z)/1048576))
meta = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
sz = d['worldBBox']['size']
dims = ('window.AP2=window.AP2||{};window.AP2.DIMS={W:%s,H:%s,D:%s,HX:%s,HY:%s,HZ:%s};\n'
        % (sz[0], sz[1], sz[2], round(sz[0] / 2, 3), round(sz[1] / 2, 3), round(sz[2] / 2, 3)))
with open(PAGE + '45_data.js', 'w') as f:
    f.write(dims)
    f.write('window.ROBOT_META=' + meta + ';\n')
    f.write('window.ROBOT_BIN_Z="' + b64 + '";\n')
print('wrote 45_data.js  total %.1f MB' % ((len(meta) + len(b64)) / 1048576))
print('centred bbox size', d['worldBBox']['size'])