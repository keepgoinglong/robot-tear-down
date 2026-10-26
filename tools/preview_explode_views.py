#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw the explode layout as AABB wireframes: home (grey) vs exploded (colour),
iso + three orthographic views.  Lets me judge symmetry / tidiness without a GPU.
"""
import json, io, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

FILE = sys.argv[1] if len(sys.argv) > 1 else '/sessions/sweet-quirky-hypatia/mnt/outputs/机械臂-三维拆解.html'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/sessions/sweet-quirky-hypatia/mnt/outputs/_robot/preview_explode.png'
MODE = sys.argv[3] if len(sys.argv) > 3 else 'explode'

s = io.open(FILE, encoding='utf-8', errors='surrogateescape').read()
a = s.index('window.ROBOT_META='); b = s.index(';\nwindow.ROBOT_BIN_Z=', a)
meta = json.loads(s[a + len('window.ROBOT_META='):b])
inst = meta['instances']

def box(i):
    d = i['ex'] if MODE == 'explode' else [0, 0, 0]
    dd = i['exd'] if MODE == 'explode' else 0
    return ([i['bboxMin'][k] + d[k] * dd for k in range(3)],
            [i['bboxMax'][k] + d[k] * dd for k in range(3)])

CORN = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)]
E = [(0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (2, 4), (2, 6), (3, 5), (3, 6), (4, 7), (5, 7), (6, 7)]

fig = plt.figure(figsize=(17, 4.6), dpi=110)
ax3 = fig.add_subplot(141, projection='3d')
axf = fig.add_subplot(142); axs = fig.add_subplot(143); axt = fig.add_subplot(144)

cmap = plt.get_cmap('tab20')
for i, it in enumerate(inst):
    mn, mx = box(it)
    c = cmap(i % 20)
    p = [[mn[0] if k[0] == 0 else mx[0], mn[1] if k[1] == 0 else mx[1], mn[2] if k[2] == 0 else mx[2]] for k in CORN]
    for e in E:
        ax3.plot([p[e[0]][0], p[e[1]][0]], [p[e[0]][2], p[e[1]][2]], [p[e[0]][1], p[e[1]][1]],
                 color=c, lw=.7, alpha=.85)
    hmn = it['bboxMin']; hmx = it['bboxMax']
    for ax, (u, v) in ((axf, (0, 1)), (axs, (2, 1)), (axt, (0, 2))):
        ax.add_patch(plt.Rectangle((mn[u], mn[v]), mx[u] - mn[u], mx[v] - mn[v],
                                   fill=False, ec=c, lw=.9, alpha=.9))
        ax.add_patch(plt.Rectangle((hmn[u], hmn[v]), hmx[u] - hmn[u], hmx[v] - hmn[v],
                                   fill=False, ec='#bbb', lw=.6, ls=':', alpha=.9))

for ax, (u, v), t in ((axf, (0, 1), 'front  x-y'), (axs, (2, 1), 'side  z-y'), (axt, (0, 2), 'top  x-z')):
    ax.plot([0, 0], [-260, -260], '')          # keep limits
    ax.axhline(-260 if v == 1 else 0, color='#4ce0ff', lw=.8, alpha=.5)
    ax.axvline(0, color='#888', lw=.5)
    ax.set_title(t, fontsize=9); ax.set_aspect('equal'); ax.grid(alpha=.15); ax.tick_params(labelsize=6)
ax3.set_title('iso  (x right, y up, z toward viewer)', fontsize=9)
ax3.set_box_aspect((1, 1.1, 1)); ax3.tick_params(labelsize=6)
ax3.view_init(elev=18, azim=-58)
fig.suptitle('robot explode layout — %s  (grey dotted = assembled pose, colour = exploded)' % MODE, fontsize=10)
fig.tight_layout()
fig.savefig(OUT)
print('saved', OUT)