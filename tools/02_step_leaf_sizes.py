#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover the remaining part names by matching geometry by SIZE, not by placement.

For every unique leaf product-definition in the STEP we compute the bounding box
of the CARTESIAN_POINTs in its own entity closure (no CAD kernel needed — the
points are plain text).  That size is pose independent, so it can be matched
against the 3MF-derived local bounding boxes, which is exactly the information
that placement-based matching could not give us.
"""
import re, json, os
from collections import defaultdict

SRC = '/sessions/sweet-quirky-hypatia/mnt/uploads/机器人.STEP'
OUT = '/sessions/sweet-quirky-hypatia/mnt/outputs/_robot/'
RE_ENT = re.compile(rb'^#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;$', re.S)
RE_REF = re.compile(rb'#(\d+)')
RE_STR = re.compile(rb"'([^']*)'")
RE_NUM = re.compile(rb'[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?')


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    open(OUT + 'names.log', 'a').write(s + '\n')


def main():
    try:
        os.remove(OUT + 'names.log')
    except OSError:
        pass
    raw = open(SRC, 'rb').read()
    etype, espan = {}, {}
    pos = raw.find(b'DATA;') + 5
    L = len(raw)
    while pos < L:
        if raw[pos:pos + 1] != b'#':
            nl = raw.find(b'\n', pos)
            pos = (nl + 1) if nl >= 0 else L
            continue
        nl = raw.find(b'\n', pos)
        if nl < 0:
            nl = L
        end = nl
        g = 0
        while g < 20000:
            if raw[pos:end].rstrip(b'\r').endswith(b';'):
                break
            nx = raw.find(b'\n', end + 1)
            if nx < 0:
                end = L
                break
            end = nx
            g += 1
        text = raw[pos:end].rstrip(b'\r')
        m = RE_ENT.match(text)
        if m:
            eid = int(m.group(1))
            etype[eid] = m.group(2)
            eq = text.find(b'=')
            s0 = pos + text.find(b'(', eq)
            e0 = pos + text.rfind(b')')
            if e0 > s0:
                espan[eid] = (s0, e0 + 1)
        pos = end + 1
    log('entities', len(etype))

    def body(eid):
        s0, e0 = espan[eid]
        return raw[s0:e0]

    def refs(eid):
        return [int(x) for x in RE_REF.findall(body(eid))]

    # ---- unique leaf pds + their names, from the earlier split run ----
    idx = json.load(open(OUT + 'leaves2/index.json', encoding='utf-8'))
    inst = json.load(open(OUT + 'instances.json', encoding='utf-8'))
    leaf_name = {}
    for it in inst:
        for lf in it['leaves']:
            leaf_name.setdefault(lf['pd'], it['name'])
    log('unique leaves', len(idx), ' named', len(leaf_name))

    # ---- bounding box of the CARTESIAN_POINTs in each leaf's closure ----
    out = []
    for e in idx:
        pd = e['pd']
        seen, stack = set(), [pd]
        mn = [1e18] * 3
        mx = [-1e18] * 3
        cnt = 0
        while stack and cnt < 3000000:
            x = stack.pop()
            if x in seen or x not in espan:
                continue
            seen.add(x)
            cnt += 1
            if etype.get(x) == b'CARTESIAN_POINT':
                nums = RE_NUM.findall(body(x))
                if len(nums) >= 3:
                    try:
                        v = [float(n) for n in nums[-3:]]
                        for k in range(3):
                            if v[k] < mn[k]:
                                mn[k] = v[k]
                            if v[k] > mx[k]:
                                mx[k] = v[k]
                    except ValueError:
                        pass
            else:
                stack.extend(refs(x))
        size = [round(mx[k] - mn[k], 3) for k in range(3)]
        out.append({'pd': pd, 'name': leaf_name.get(pd, '?'), 'size': size,
                    'min': [round(v, 2) for v in mn], 'max': [round(v, 2) for v in mx],
                    'entities': cnt})
        log('  pd %-9d %-24s size %s' % (pd, leaf_name.get(pd, '?'), size))
    json.dump(out, open(OUT + 'step_leaf_sizes.json', 'w'), ensure_ascii=False, indent=1)
    log('=== done')


if __name__ == '__main__':
    main()