#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill in the placeholder part names using the humanoid's left/right symmetry
and a few positional rules, then re-emit the page data.

Rules
  1. names ending 左/右 come in mirror pairs: if one side is identified, the
     instance whose centre is mirrored about X (and whose local geometry is the
     mirrored twin) takes the other name
  2. 头部 sits at the very top of the assembly
  3. the feet are the two lowest, widest parts; if one is named the other follows
  4. anything still unknown gets a positional placeholder
"""
import json, re
import numpy as np

OUT = '/sessions/sweet-quirky-hypatia/mnt/outputs/_robot/'
d = json.load(open(OUT + 'parts.json', encoding='utf-8'))
P = d['instances']
n = len(P)
C = np.array([[(i['bboxMin'][k] + i['bboxMax'][k]) / 2 for k in range(3)] for i in P])
SZ = np.array([[i['bboxMax'][k] - i['bboxMin'][k] for k in range(3)] for i in P])
UNK = lambda s: bool(re.fullmatch(r'\d+', s)) or s.startswith('未命名')

def twins(a, b):
    """mirror about the X axis: centres reflected, sizes equal"""
    return (abs(C[a][0] + C[b][0]) < 0.12 * max(SZ[a][0], SZ[b][0]) + 12 and
            abs(C[a][1] - C[b][1]) < 0.18 * max(SZ[a][1], SZ[b][1]) + 18 and
            abs(C[a][2] - C[b][2]) < 0.22 * max(SZ[a][2], SZ[b][2]) + 20 and
            abs(SZ[a][1] - SZ[b][1]) < 0.10 * max(SZ[a][1], SZ[b][1]) + 6 and
            abs(SZ[a][2] - SZ[b][2]) < 0.35 * max(SZ[a][2], SZ[b][2]) + 10)

fixed = 0
# 1) mirror pairs
for i in range(n):
    if UNK(P[i]['name']) or not re.search(r'[左右]', P[i]['name']):
        continue
    other = P[i]['name'].replace('左', '右') if '左' in P[i]['name'] else P[i]['name'].replace('右', '左')
    if other == P[i]['name']:
        continue
    cands = [j for j in range(n) if UNK(P[j]['name']) and twins(i, j) and abs(SZ[j][0] - SZ[i][0]) < 10]
    if len(cands) == 1:
        P[cands[0]]['name'] = other
        P[cands[0]]['nameSrc'] = 'mirror of ' + P[i]['name']
        fixed += 1
print('mirror pairs resolved:', fixed)

# 2) head = highest instance whose column is near the centre line
unk = [i for i in range(n) if UNK(P[i]['name'])]
if unk:
    top = max(unk, key=lambda i: C[i][1])
    if abs(C[top][0]) < 0.18 * max(SZ[:, 0]):
        P[top]['name'] = '头部'
        P[top]['nameSrc'] = 'highest centred part'
        fixed += 1
        print('head ->', top, np.round(C[top], 1).tolist(), np.round(SZ[top], 1).tolist())

# 3) feet: lowest two wide parts
unk = [i for i in range(n) if UNK(P[i]['name'])]
if len(unk) >= 2:
    lows = sorted(unk, key=lambda i: C[i][1])[:2]
    named_feet = [i for i in range(n) if '脚底板' in P[i]['name']]
    used = set(p['name'] for p in P if not UNK(p['name']))
    if len(named_feet) == 1:
        nm = P[named_feet[0]]['name']
        twin = nm.replace('左', '右') if '左' in nm else nm.replace('右', '左')
        if twin not in used:
            for i in lows:
                if abs(C[i][1] - C[named_feet[0]][1]) < 0.15 * max(SZ[:, 1]):
                    P[i]['name'] = twin; P[i]['nameSrc'] = 'mirror foot'
                    fixed += 1
                    print('foot ->', i, twin, np.round(C[i], 1).tolist())
                    break


# 3.5) same geometry => same name.  14 ST3215 servos and the mirrored pairs share
#      one mesh each, so one identified instance identifies all of them.
by_geom = {}
for i in range(n):
    by_geom.setdefault(P[i]['geom'], []).append(i)
prop_n = 0
for key, idxs in by_geom.items():
    known = [i for i in idxs if not UNK(P[i]['name'])]
    if not known:
        continue
    nm = P[known[0]]['name']
    for i in idxs:
        if UNK(P[i]['name']):
            P[i]['name'] = nm
            P[i]['nameSrc'] = 'same geometry as %d' % known[0]
            prop_n += 1
print('same-geometry propagation:', prop_n)

# 4) leftover -> positional placeholder
for i in range(n):
    if UNK(P[i]['name']):
        pos = []
        if C[i][1] > 0.12 * max(SZ[:, 1]):
            pos.append('上')
        elif C[i][1] < -0.12 * max(SZ[:, 1]):
            pos.append('下')
        pos.append('左' if C[i][0] < 0 else '右')
        sz = np.round(SZ[i], 0).astype(int).tolist()
        P[i]['name'] = '未识别件(%s %d×%d×%d)' % (''.join(pos), sz[0], sz[1], sz[2])
print('total named:', sum(1 for i in P if '未识别件' not in i['name']), '/', n)

json.dump(d, open(OUT + 'parts.json', 'w'), ensure_ascii=False, indent=1)
for i, p in enumerate(P):
    print('  %2d %-26s %s' % (i, p['name'], p.get('nameSrc', 'step')) )