#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pack3mf v2 — dedupe repeated instances.

Each of the 55 top-level components gets a *part-local* geometry (walked from its
children, i.e. without its own placement) plus its own placement matrix.  Parts
whose local geometry is identical (the 14 identical ST3215 servos, the pairs of
link plates, rollers, washers …) therefore share one stored mesh, which cuts the
payload by ~60%.

Outputs
  geoms.bin    concatenated quantised geometry buffers (u16 positions + u16/u32 indices)
  parts.json   {geoms:[...], instances:[...], worldBBox, totals}
"""
import zipfile, re, json, os, hashlib
import numpy as np

MF = '/sessions/sweet-quirky-hypatia/mnt/uploads/机器人2-ddd7daa9.3mf'
OUT = '/sessions/sweet-quirky-hypatia/mnt/outputs/_robot/'

RE_V = re.compile(rb'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"')
RE_T = re.compile(rb'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"')
RE_C = re.compile(rb'<component objectid="(\d+)"(?:\s+transform="([^"]*)")?')
RE_SUFFIX = re.compile(r'\((?:默认|Default)\)显示状态[- ]?\d*|_[0-9a-fA-F]{6}$')


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    open(OUT + 'mf2.log', 'a').write(s + '\n')


def clean_name(n):
    n = RE_SUFFIX.sub('', n or '')
    n = n.replace('(Default)', '').replace('(默认)', '')
    return n.strip() or '未命名'


def mat_ident():
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def parse_mat(s):
    if not s:
        return mat_ident()
    f = [float(x) for x in s.split()]
    return [f[0], f[1], f[2], 0, f[3], f[4], f[5], 0, f[6], f[7], f[8], 0, f[9], f[10], f[11], 1]


def mat_mul(a, b):
    return (np.array(a, dtype=np.float64).reshape(4, 4) @ np.array(b, dtype=np.float64).reshape(4, 4)).reshape(-1).tolist()


def quat_from_rows(place):
    """place = [r0,r1,r2,0, r3,r4,r5,0, r6,r7,r8,0, tx,ty,tz,1]  (3MF row-vector form)
    three.js applies M_transposed, so rotation = [[r0,r3,r6],[r1,r4,r7],[r2,r5,r8]]. """
    r0, r1, r2 = place[0], place[1], place[2]
    r3, r4, r5 = place[4], place[5], place[6]
    r6, r7, r8 = place[8], place[9], place[10]
    m = [[r0, r3, r6], [r1, r4, r7], [r2, r5, r8]]
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        q = 0.5 / ((tr + 1.0) ** 0.5)
        w = 0.25 / q
        x = (m[2][1] - m[1][2]) * q
        y = (m[0][2] - m[2][0]) * q
        z = (m[1][0] - m[0][1]) * q
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s2 = (1.0 + m[0][0] - m[1][1] - m[2][2]) ** 0.5 * 2
        w = (m[2][1] - m[1][2]) / s2
        x = 0.25 * s2
        y = (m[0][1] + m[1][0]) / s2
        z = (m[0][2] + m[2][0]) / s2
    elif m[1][1] > m[2][2]:
        s2 = (1.0 + m[1][1] - m[0][0] - m[2][2]) ** 0.5 * 2
        w = (m[0][2] - m[2][0]) / s2
        x = (m[0][1] + m[1][0]) / s2
        y = 0.25 * s2
        z = (m[1][2] + m[2][1]) / s2
    else:
        s2 = (1.0 + m[2][2] - m[0][0] - m[1][1]) ** 0.5 * 2
        w = (m[1][0] - m[0][1]) / s2
        x = (m[0][2] + m[2][0]) / s2
        y = (m[1][2] + m[2][1]) / s2
        z = 0.25 * s2
    n = (x * x + y * y + z * z + w * w) ** 0.5 or 1
    return [round(x / n, 7), round(y / n, 7), round(z / n, 7), round(w / n, 7)]


def main():
    try:
        os.remove(OUT + 'mf2.log')
    except OSError:
        pass
    z = zipfile.ZipFile(MF)
    data = z.read('3D/3dmodel.model')
    objs = {}
    for p in data.split(b'<object id="')[1:]:
        oid = int(p[:p.find(b'"')])
        comps = [(int(a), (b.decode() if b else None)) for a, b in RE_C.findall(p)]
        v = t = None
        if b'<vertices>' in p:
            vi = p.find(b'<vertices>')
            v = np.array(RE_V.findall(p[vi:p.find(b'</vertices>', vi)]), dtype=np.float64).astype(np.float32)
            ti = p.find(b'<triangles>')
            t = np.array(RE_T.findall(p[ti:p.find(b'</triangles>', ti)]), dtype=np.int32)
        objs[oid] = {'comps': comps, 'v': v, 't': t}
    root_id = int(re.search(rb'objectid="(\d+)"', re.search(rb'<build>.*?</build>', data, re.S).group(0)).group(1))
    log('objects %d, root %d with %d children' % (len(objs), root_id, len(objs[root_id]['comps'])))

    def walk(oid, m, out, depth=0):
        o = objs.get(oid)
        if o is None or depth > 12:
            return
        if o['v'] is not None and o['v'].shape[0]:
            out.append((oid, m))
        for cid, tr in o['comps']:
            walk(cid, mat_mul(m, parse_mat(tr)), out, depth + 1)

    # ---- local geometry + placement per top-level component ----
    step_inst = json.load(open(OUT + 'instances.json', encoding='utf-8'))
    comps = objs[root_id]['comps']
    insts = []

    def to3mf(m):
        """my 16-float layout -> the 3MF's 12-value order (translation at 9..11)"""
        return [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10], m[3], m[7], m[11]]

    # match each 3MF top-level placement against the STEP instances (nearest) so
    # the recovered Chinese part names land on the right bodies
    step_pool = []
    for s in step_inst:
        sm = s['leaves'][0]['m']
        step_pool.append((to3mf(sm), clean_name(s['name'])))
    agree = 0
    used = set()
    for i, (cid, tr) in enumerate(comps):
        place = parse_mat(tr)
        raw = [float(x) for x in tr.split()] if tr else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
        best, bestd = None, 1e9
        for k, (sm, nm) in enumerate(step_pool):
            if k in used:
                continue
            d = max(abs(raw[j] - sm[j]) for j in range(12))
            if d < bestd:
                bestd, best = d, (k, nm)
        nm = ''
        if best and bestd < 0.075:
            used.add(best[0]); nm = best[1]; agree += 1
        refs = []
        for sub, str2 in objs[cid]['comps']:
            walk(sub, parse_mat(str2), refs)
        if not refs and objs[cid]['v'] is not None:
            refs = [(cid, mat_ident())]
        insts.append({'name': nm or clean_name(str(cid)), 'place': place, 'refs': refs})
    log('placement agreement with STEP: %d / %d' % (agree, len(insts)))

    # ---- merge geometry per unique local signature ----
    geoms = {}
    order = []
    for ins in insts:
        key = hashlib.md5(('|'.join('%d:%s' % (oid, ','.join('%.4f' % x for x in m))
                                    for oid, m in ins['refs'])).encode()).hexdigest()[:16]
        ins['key'] = key
        if key in geoms:
            continue
        P = []
        T = []
        base = 0
        for oid, m in ins['refs']:
            o = objs[oid]
            M = np.array(m, dtype=np.float32).reshape(4, 4)
            q = (np.hstack([o['v'], np.ones((o['v'].shape[0], 1), np.float32)]) @ M)[:, :3]
            P.append(q)
            T.append(o['t'] + base)
            base += o['v'].shape[0]
        P = np.vstack(P)
        T = np.vstack(T)
        geoms[key] = {'P': P, 'T': T, 'refs': len(ins['refs'])}
        order.append(key)

    # ---- quantise + write ----
    gmeta = []
    chunks = []
    off = 0
    for key in order:
        g = geoms[key]
        P, T = g['P'], g['T']
        mn = P.min(axis=0); mx = P.max(axis=0)
        size = (mx - mn).astype(np.float64)
        scl = np.where(size > 1e-9, 65535.0 / np.maximum(size, 1e-9), 0.0)
        qi = np.clip(np.rint((P - mn) * scl), 0, 65535).astype(np.uint16)
        n = P.shape[0]
        u16 = n <= 65535
        vb = qi.astype('<u2').tobytes()
        ib = T.astype('<u2' if u16 else '<u4').tobytes()
        chunks.append(vb + ib)
        gmeta.append({'key': key, 'verts': int(n), 'tris': int(T.shape[0]), 'u16': bool(u16),
                      'bboxMin': [round(float(x), 4) for x in mn], 'bboxMax': [round(float(x), 4) for x in mx],
                      'size': [round(float(x), 3) for x in size],
                      'offset': off, 'byteLength': len(vb) + len(ib), 'vbufLen': len(vb),
                      'refs': g['refs']})
        off += len(vb) + len(ib)
    open(OUT + 'geoms.bin', 'wb').write(b''.join(chunks))

    # ---- instances with world bbox ----
    WMN = np.array([1e12] * 3); WMX = np.array([-1e12] * 3)
    inst_out = []
    for ins in insts:
        gm = [g for g in gmeta if g['key'] == ins['key']][0]
        M = np.array(ins['place'], dtype=np.float64).reshape(4, 4)
        mn = np.array(gm['bboxMin']); mx = np.array(gm['bboxMax'])
        corners = np.array([[x, y, z, 1] for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])])
        w = (corners @ M)[:, :3]
        wmn = w.min(axis=0); wmx = w.max(axis=0)
        WMN = np.minimum(WMN, wmn); WMX = np.maximum(WMX, wmx)
        inst_out.append({
            'name': ins['name'], 'geom': ins['key'],
            'm': [round(float(x), 6) for x in ins['place']],
            # column-major 16 values, ready for three.js Matrix4.fromArray()
            # three.js Matrix4.fromArray expects COLUMN-major, and the 3MF's 12
            # values in their original order are exactly that (the transpose of
            # its row-vector matrix, i.e. v' = M v).  Re-ordering them scrambles
            # both rotation and translation.
            # place is ALREADY in the exact layout three.js wants: pads at
            # 3/7/11, translation at 12/13/14, and its rotation block is the
            # transpose of the 3MF's row-vector rotation, which is what three.js
            # applies.  (Re-grouping or transposing it here was the bug.)
            'mjs': [round(float(x), 7) for x in ins['place']],
            'localMin': gm['bboxMin'], 'localMax': gm['bboxMax'],
            'bboxMin': [round(float(x), 3) for x in wmn], 'bboxMax': [round(float(x), 3) for x in wmx],
            'size': [round(float(x), 2) for x in (wmx - wmn)]
        })

    tot_v = sum(g['verts'] for g in gmeta); tot_t = sum(g['tris'] for g in gmeta)
    packed = off
    json.dump({
        'source': '机器人2-ddd7daa9.3mf', 'units': 'mm', 'geoms': gmeta, 'instances': inst_out,
        'worldBBox': {'min': [float(x) for x in WMN], 'max': [float(x) for x in WMX],
                      'size': [float(x) for x in (WMX - WMN)]},
        'totals': {'geoms': len(gmeta), 'instances': len(inst_out), 'verts': tot_v, 'tris': tot_t,
                   'packedBytes': packed,
                   'instancesTris': sum(g['tris'] for g in gmeta for i in inst_out if i['geom'] == g['key'])}
    }, open(OUT + 'parts.json', 'w'), ensure_ascii=False, indent=1)
    log('=== geoms %d (from %d instances)  verts %d  tris %d  packed %.2fMB' %
        (len(gmeta), len(inst_out), tot_v, tot_t, packed / 1048576))
    log('=== world bbox %.1f x %.1f x %.1f mm' % tuple(WMX - WMN))
    for i, ins in enumerate(inst_out):
        log('  %2d %-22s %s  size %s' % (i, ins['name'], ins['geom'][:8], ins['size']))
    open(OUT + 'pack.ok', 'w').write('ok')
    log('=== pack3mf2 done')


if __name__ == '__main__':
    main()