#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP assembly splitter v2 — handles complex entity instances, resolves the
assembly transform chain and emits one standalone STEP per unique leaf body.

Facts learned about this SolidWorks AP203 file:
  * entities are one per line; complex instances look like
        #id =( REPRESENTATION_RELATIONSHIP(...) REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(#idt) SHAPE_REPRESENTATION_RELATIONSHIP() );
  * the part -> shape link is REVERSED: PRODUCT_DEFINITION_SHAPE references the pd,
    SHAPE_DEFINITION_REPRESENTATION references that pds, and only then does the named
    representation hold the geometry.
"""
import re, os, json, sys
import numpy as np

SRC = '/sessions/sweet-quirky-hypatia/mnt/uploads/机器人.STEP'
OUT = '/sessions/sweet-quirky-hypatia/mnt/outputs/_robot/'
LEAF = OUT + 'leaves2/'

RE_LINE = re.compile(rb'^#(\d+)\s*=\s*(.*);\s*$', re.S)
RE_TYPES = re.compile(rb'([A-Z0-9_]+)\s*\(')
RE_REF = re.compile(rb'#(\d+)')
RE_STR = re.compile(rb"'([^']*)'")
RE_NUM = re.compile(rb'[-+0-9.][0-9.eE+-]*')


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    open(OUT + 'split2.log', 'a').write(s + '\n')


def decode_name(b):
    """STEP strings may carry \\X2\\<utf16be hex>\\X0\\ or \\X\\<hex>\\X0\\ escapes."""
    if not b:
        return ''
    out = []
    i = 0
    while i < len(b):
        if b.startswith(b'\\X2\\', i):
            j = b.find(b'\\X0\\', i)
            if j < 0:
                break
            hexs = b[i + 4:j]
            try:
                out.append(bytes.fromhex(hexs.decode('ascii')).decode('utf-16-be', 'replace'))
            except Exception:
                pass
            i = j + 4
        elif b.startswith(b'\\X\\', i):
            j = b.find(b'\\X0\\', i)
            if j < 0:
                break
            hexs = b[i + 3:j]
            try:
                out.append(bytes.fromhex(hexs.decode('ascii')).decode('latin-1'))
            except Exception:
                pass
            i = j + 4
        else:
            j = b.find(b'\\', i)
            if j < 0:
                out.append(b[i:].decode('gbk', 'replace'))
                break
            out.append(b[i:j].decode('gbk', 'replace'))
            i = j
    return ''.join(out).strip()


def first_string(body):
    m = RE_STR.search(body)
    return m.group(1) if m else b''


def ident():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mul(a, b):
    o = [0.0] * 16
    for i in range(4):
        for j in range(4):
            o[i * 4 + j] = a[i * 4] * b[j] + a[i * 4 + 1] * b[4 + j] + a[i * 4 + 2] * b[8 + j] + a[i * 4 + 3] * b[12 + j]
    return o


def inv_rigid(m):
    R = [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]]
    t = (m[3], m[7], m[11])
    o = ident()
    o[0], o[1], o[2] = R[0], R[3], R[6]
    o[4], o[5], o[6] = R[1], R[4], R[7]
    o[8], o[9], o[10] = R[2], R[5], R[8]
    o[3] = -(R[0] * t[0] + R[3] * t[1] + R[6] * t[2])
    o[7] = -(R[1] * t[0] + R[4] * t[1] + R[7] * t[2])
    o[11] = -(R[2] * t[0] + R[5] * t[1] + R[8] * t[2])
    return o


def main():
    os.makedirs(LEAF, exist_ok=True)
    for f in ('split2.log',):
        try:
            os.remove(OUT + f)
        except OSError:
            pass
    raw = open(SRC, 'rb').read()
    log('bytes', len(raw))

    # ---------------- pass 1: entity spans + types ----------------
    etype = {}          # id -> b'TYPE'   (simple)
    ecmplx = {}         # id -> (t1,t2,..) (complex instance)
    espan = {}
    n = bad = cplx = 0
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
        guard = 0
        while guard < 20000:            # entities may wrap over several lines
            if raw[pos:end].rstrip(b'\r').endswith(b';'):
                break
            nx = raw.find(b'\n', end + 1)
            if nx < 0:
                end = L
                break
            end = nx
            guard += 1
        text = raw[pos:end].rstrip(b'\r')
        m = RE_LINE.match(text)
        if m:
            eid = int(m.group(1))
            body = m.group(2)
            b0 = body.strip()
            if b0[:1] == b'(':
                ecmplx[eid] = tuple(RE_TYPES.findall(b0))
                cplx += 1
            else:
                tm = RE_TYPES.match(b0)
                if tm:
                    etype[eid] = tm.group(1)
            eq = text.find(b'=')
            s = pos + text.find(b'(', eq)
            e = pos + text.rfind(b')')
            if e > s:
                espan[eid] = (s, e + 1)
                n += 1
            else:
                bad += 1
        else:
            bad += 1
        pos = end + 1
    log('entities', n, ' complex', cplx, ' skipped', bad)

    # ---------------- reference index (forward + reverse) ----------------
    owners = np.empty(0, dtype=np.int64)
    refs = np.empty(0, dtype=np.int64)
    ids_sorted = sorted(espan.keys(), key=lambda i: espan[i][0])   # BY FILE POSITION
    spans = np.array([espan[i] for i in ids_sorted], dtype=np.int64)
    ids_arr = np.array(ids_sorted, dtype=np.int64)
    starts = spans[:, 0]
    o_list = []
    r_list = []
    idx = 0
    total = len(ids_arr)
    for m in RE_REF.finditer(raw):
        p = m.start()
        while idx < total and p > spans[idx, 1]:
            idx += 1
        if idx >= total:
            break
        if p >= spans[idx, 0]:
            o_list.append(int(ids_arr[idx]))
            r_list.append(int(m.group(1)))
    owners = np.array(o_list, dtype=np.int64)
    refs = np.array(r_list, dtype=np.int64)
    log('references', len(refs))
    by_ref = np.argsort(refs, kind='stable')
    Rs, Os = refs[by_ref], owners[by_ref]
    by_own = np.argsort(owners, kind='stable')
    Ow, Rw = owners[by_own], refs[by_own]

    def fwd(eid):
        i = np.searchsorted(Ow, eid, 'left')
        j = np.searchsorted(Ow, eid, 'right')
        return Rw[i:j].tolist()

    def rev(eid):
        i = np.searchsorted(Rs, eid, 'left')
        j = np.searchsorted(Rs, eid, 'right')
        return Os[i:j].tolist()

    def is_type(eid, t):
        if etype.get(eid) == t:
            return True
        c = ecmplx.get(eid)
        return bool(c) and t in c

    def bof(eid):
        s, e = espan[eid]
        return raw[s:e]

    # ---------------- axis2_placement_3d -> matrix ----------------
    def point(eid):
        if eid not in espan:
            return (0.0, 0.0, 0.0)
        rr = fwd(eid)
        src = rr[0] if rr else eid
        try:
            v = [float(x) for x in RE_NUM.findall(bof(src))[:3]]
            return tuple(v) if len(v) == 3 else (0.0, 0.0, 0.0)
        except Exception:
            return (0.0, 0.0, 0.0)

    def dirv(eid):
        if eid not in espan:
            return None
        rr = fwd(eid)
        src = rr[0] if rr else eid
        try:
            v = [float(x) for x in RE_NUM.findall(bof(src))[:3]]
            if len(v) == 3 and sum(abs(a) for a in v) > 1e-9:
                return v
        except Exception:
            pass
        return None

    def mk(loc, ax, rd):
        p = point(loc)
        z = dirv(ax) or [0, 0, 1]
        x = dirv(rd) or [1, 0, 0]

        def nrm(v):
            l = sum(a * a for a in v) ** .5 or 1
            return [a / l for a in v]
        def cr(a, b):
            return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
        def dt(a, b):
            return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
        z = nrm(z)
        x = nrm([x[0] - dt(x, z) * z[0], x[1] - dt(x, z) * z[1], x[2] - dt(x, z) * z[2]])
        y = cr(z, x)
        return [x[0], y[0], z[0], p[0], x[1], y[1], z[1], p[1], x[2], y[2], z[2], p[2], 0, 0, 0, 1.0]

    def axis(eid, depth=0):
        if depth > 6 or eid not in espan:
            return ident()
        t = etype.get(eid, b'')
        rr = fwd(eid)
        if t == b'AXIS2_PLACEMENT_3D' and len(rr) >= 3:
            return mk(rr[0], rr[1], rr[2])
        for x in rr:
            if etype.get(x) == b'AXIS2_PLACEMENT_3D':
                r2 = fwd(x)
                if len(r2) >= 3:
                    return mk(r2[0], r2[1], r2[2])
        return ident()

    # ---------------- assembly graph ----------------
    nauos = [i for i, t in etype.items() if t == b'NEXT_ASSEMBLY_USAGE_OCCURRENCE']
    nauo = {}
    for eid in nauos:
        r = RE_REF.findall(bof(eid))
        rr = [int(x) for x in r]
        nauo[eid] = {'parent': rr[0] if rr else 0, 'child': rr[1] if len(rr) > 1 else 0,
                     'name': decode_name(first_string(bof(eid)))}
    log('nauo', len(nauo))

    # pds whose definition is a nauo
    pds_of = {}
    for eid, t in etype.items():
        if t == b'PRODUCT_DEFINITION_SHAPE':
            for x in rev(eid):          # not needed; use fwd
                pass
    # definition is the *last* ref of PRODUCT_DEFINITION_SHAPE(name,desc,definition)
    for eid, t in etype.items():
        if t == b'PRODUCT_DEFINITION_SHAPE':
            rr = fwd(eid)
            if rr and rr[-1] in nauo:
                pds_of[rr[-1]] = eid
    log('pds_of', len(pds_of))

    # cdsh referencing that pds  ->  complex instance  ->  idt
    T = {}
    for nid in nauo:
        pds = pds_of.get(nid)
        if not pds:
            T[nid] = ident()
            continue
        rel = None
        for x in rev(pds):
            if is_type(x, b'CONTEXT_DEPENDENT_SHAPE_REPRESENTATION') or (ecmplx.get(x) and b'CONTEXT_DEPENDENT_SHAPE_REPRESENTATION' in ecmplx[x]):
                rel = x
        # the other argument of the cdsh is the relationship instance
        i = None
        if rel is not None:
            for x in fwd(rel):
                if is_type(x, b'REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION') or \
                   (ecmplx.get(x) and b'REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION' in ecmplx[x]):
                    i = x
        if i is None:
            T[nid] = ident()
            continue
        idt = None
        for x in fwd(i):
            if etype.get(x) == b'ITEM_DEFINED_TRANSFORMATION':
                idt = x
        if idt is None:
            T[nid] = ident()
            continue
        rr = fwd(idt)
        if len(rr) < 2:
            T[nid] = ident()
            continue
        T[nid] = mul(axis(rr[0]), inv_rigid(axis(rr[1])))
    log('transforms', sum(1 for v in T.values() if v != ident()), '/', len(T))

    # ---------------- hierarchy ----------------
    kids = {}
    for nid, v in nauo.items():
        kids.setdefault(v['parent'], []).append(nid)
    parents = set(v['parent'] for v in nauo.values())
    children = set(v['child'] for v in nauo.values())
    roots = [p for p in parents if p not in children]
    log('roots', roots, 'kids(root)', [len(kids.get(r, [])) for r in roots])

    def pd_name(pd):
        out = ''
        for x in fwd(pd):                       # PRODUCT_DEFINITION(...,#pdf,...)
            if etype.get(x, b'').startswith(b'PRODUCT_DEFINITION_FORMATION'):
                for y in fwd(x):
                    if etype.get(y) == b'PRODUCT':
                        out = decode_name(first_string(bof(y)))
        return out

    instances = []
    def expand(pd, m, depth, out):
        for nid in kids.get(pd, []):
            ch = nauo[nid]['child']
            m2 = mul(m, T.get(nid, ident()))
            if ch in parents and depth < 12:
                expand(ch, m2, depth + 1, out)
            else:
                out.append({'pd': ch, 'm': m2})

    for r in roots:
        for nid in kids.get(r, []):
            ch = nauo[nid]['child']
            m2 = T.get(nid, ident())
            out = []
            if ch in parents:
                expand(ch, m2, 1, out)
            else:
                out.append({'pd': ch, 'm': m2})
            instances.append({'name': pd_name(ch) or nauo[nid]['name'] or ('part_%d' % len(instances)),
                              'leaves': out})
    log('instances', len(instances), 'leaf refs', sum(len(i['leaves']) for i in instances))
    names = [i['name'] for i in instances]
    log('names:', ' | '.join(names[:14]))

    # ---------------- geometry closure per leaf pd ----------------
    hdr_end = raw.find(b'ENDSEC;')
    header = raw[:hdr_end + len(b'ENDSEC;')]

    def geometry_ids(pd):
        """pd -> pds(rev) -> sdr(rev) -> lightweight SHAPE_REPRESENTATION
           --(plain representation_relationship)--> ADVANCED_BREP_SHAPE_REPRESENTATION
           -> closure.  Assembly relations (the ones carrying a WITH_TRANSFORMATION
           subtype) are deliberately NOT followed, otherwise the whole robot comes in."""
        chain = set()
        seeds = []
        for pds in rev(pd):
            if etype.get(pds) != b'PRODUCT_DEFINITION_SHAPE':
                continue
            chain.add(pds)
            for sdr in rev(pds):
                if etype.get(sdr) != b'SHAPE_DEFINITION_REPRESENTATION':
                    continue
                chain.add(sdr)
                for x in fwd(sdr):
                    chain.add(x)
                    seeds.append(x)
        # follow the part-level representation relationship.  In this file the part
        # relations are SIMPLE entities while the 55 assembly relations are complex
        # instances carrying a WITH_TRANSFORMATION subtype — so only accept a link
        # whose far end is a real geometric representation.
        GEO_REPS = (b'ADVANCED_BREP_SHAPE_REPRESENTATION', b'MANIFOLD_SURFACE_SHAPE_REPRESENTATION',
                    b'GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION',
                    b'FACETED_BREP_SHAPE_REPRESENTATION', b'GEOMETRICALLY_BOUNDED_SURFACE_SHAPE_REPRESENTATION')
        for x in list(seeds):
            for rr in set(rev(x) + fwd(x)):
                if rr in chain:
                    continue
                t = etype.get(rr)
                c = ecmplx.get(rr)
                rel = (t in (b'SHAPE_REPRESENTATION_RELATIONSHIP', b'REPRESENTATION_RELATIONSHIP')) or \
                      bool(c) and (b'SHAPE_REPRESENTATION_RELATIONSHIP' in c or b'REPRESENTATION_RELATIONSHIP' in c)
                if not rel:
                    continue
                if c and b'REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION' in c:
                    continue
                for y in fwd(rr):
                    if etype.get(y) in GEO_REPS and y not in chain:
                        chain.add(rr)
                        chain.add(y)
                        seeds.append(y)
        got = set()
        stack = list(seeds)
        while stack:
            x = stack.pop()
            if x in got or x not in espan:
                continue
            got.add(x)
            stack.extend(fwd(x))
        return got, chain

    uniq = []
    seen = set()
    for ins in instances:
        for lf in ins['leaves']:
            if lf['pd'] not in seen:
                seen.add(lf['pd'])
                uniq.append(lf['pd'])
    log('unique leaf pds', len(uniq))

    idx = []
    if os.environ.get('DBG'):
        for pd in uniq[:3]:
            log('DEBUG pd', pd, pd_name(pd))
            r1 = rev(pd)
            log('   rev(pd) n=%d %s' % (len(r1), [(x, etype.get(x, b'?').decode('latin1')) for x in r1[:10]]))
            for pds in r1:
                if etype.get(pds) == b'PRODUCT_DEFINITION_SHAPE':
                    r2 = rev(pds)
                    log('   rev(pds %d) n=%d %s' % (pds, len(r2), [(x, etype.get(x, b'?').decode('latin1')) for x in r2[:10]]))
                    for sdr in r2:
                        if etype.get(sdr) == b'SHAPE_DEFINITION_REPRESENTATION':
                            f = fwd(sdr)
                            log('   fwd(sdr %d) = %s' % (sdr, [(x, etype.get(x, b'?').decode('latin1')) for x in f[:6]]))
                            for x in f:
                                log('      fwd(%d) n=%d  type=%s' % (x, len(fwd(x)), etype.get(x, b'?')[:44].decode('latin1')))
            log("   closure size", len(geometry_ids(pd)[0]))
        log('=== debug done')
        return

    for pd in uniq:
        geo, chain = geometry_ids(pd)
        keep = set(geo) | set(chain)
        # forward-closed only: adding reverse references (rev(pd)) would drag in
        # NAUOs / CC_DESIGN_* entities that point at sibling parts -> dangling refs
        for x in [pd] + fwd(pd):
            keep.add(x)
        keep = {x for x in keep if x in espan}
        chunks = []
        for i in sorted(keep):
            s, e = espan[i]
            if i in ecmplx:
                chunks.append(b'#' + str(i).encode() + b'=' + raw[s:e] + b';\r\n')
            else:
                chunks.append(b'#' + str(i).encode() + b'=' + etype.get(i, b'') + raw[s:e] + b';\r\n')
        txt = header + b'\r\nDATA;\r\n' + b''.join(chunks) + b'ENDSEC;\r\nEND-ISO-10303-21;\r\n'
        fn = 'pd_%d.step' % pd
        open(LEAF + fn, 'wb').write(txt)
        idx.append({'pd': pd, 'file': fn, 'bytes': len(txt), 'entities': len(keep),
                    'geoEntities': len(geo)})
    log('leaf files', len(idx), ' MB', round(sum(x['bytes'] for x in idx) / 1048576, 2),
        ' entities min/max', min(x['entities'] for x in idx), max(x['entities'] for x in idx))
    json.dump(idx, open(LEAF + 'index.json', 'w'), ensure_ascii=False, indent=1)
    json.dump(instances, open(OUT + 'instances.json', 'w'), ensure_ascii=False, indent=1)
    log('=== split2 done')


if __name__ == '__main__':
    main()