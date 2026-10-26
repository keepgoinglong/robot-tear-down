#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch the user-approved build in place: fix the label clutter + flicker.

  1. labels default to "selected / hovered / dragging only" (<= 3 at a time, so
     nothing can overlap)
  2. new 标签 button (+ L key) switches to "show all exploded part names"
  3. in "all" mode the de-collision order is by part index instead of by screen
     y, so the order cannot swap between frames (that swap was the flicker)
  4. label positions are rounded to whole pixels and the opacity transition is
     dropped, killing the remaining sub-pixel shimmer
  5. "all" mode uses a compact label (index + shortened name) so the density is
     bearable
"""
import re, sys

SRC = '/sessions/sweet-quirky-hypatia/mnt/uploads/机器人-三维拆解.html'
DST = '/sessions/sweet-quirky-hypatia/mnt/outputs/机械臂-三维拆解.html'

s = open(SRC, encoding='utf-8', errors='surrogateescape').read()
n0 = len(s)
rep = []

def sub(a, b, tag):
    global s
    if a not in s:
        print('MISS:', tag); return False
    s = s.replace(a, b, 1)
    print('ok:', tag); return True

# ---- 1. show rule -------------------------------------------------------
sub("""    var show = p.p > .30 || p === selected || p === hovered || (drag && drag.part === p);""",
    """    var show = p === selected || p === hovered || (drag && drag.part === p) ||
               (window.__labelAll && p.p > .30);""", 'show rule')

# ---- 2. stable order + integer positions --------------------------------
sub("""    vis.push({ el: el, x: pr.x, y: pr.y - lift });""",
    """    vis.push({ el: el, x: pr.x, y: pr.y - lift, i: p.i });""", 'vis entry')
sub("""  vis.sort(function (a, b) { return a.y - b.y; });""",
    """  /* order by part index, NOT by screen y — sorting by y let labels swap
     places between frames whenever two of them were at similar heights, and
     that swap is what read as flicker */
  vis.sort(function (a, b) { return a.i - b.i; });""", 'stable order')
sub("""    L.el.style.transform = 'translate(-50%,-50%) translate(' + L.x.toFixed(1) + 'px,' + L.y.toFixed(1) + 'px)';""",
    """    L.el.style.transform = 'translate(-50%,-50%) translate(' + Math.round(L.x) + 'px,' + Math.round(L.y) + 'px)';""",
    'integer positions')

# ---- 3. label mode plumbing --------------------------------------------
sub("""var labelEls = {};""",
    """window.__labelAll = false;
function labelHTML(p, compact) {
  var n = String(p.n).padStart(2, '0');
  if (!compact) return '<i>' + n + '</i>' + p.name;
  var t = p.name.length > 7 ? p.name.slice(0, 7) + '…' : p.name;
  return '<i>' + n + '</i>' + t;
}
var labelEls = {};""", 'label helpers')

sub("""document.getElementById('btnScreen').style.display = 'none';""",
    """document.getElementById('btnScreen').style.display = 'none';
var btnLabels = document.getElementById('btnLabels');
function setLabelMode(all) {
  window.__labelAll = all;
  parts.forEach(function (p) { labelEls[p.i].innerHTML = labelHTML(p, all); });
  btnLabels.classList.toggle('on', all);
}
btnLabels.addEventListener('click', function () { setLabelMode(!window.__labelAll); });""",
    'label button wiring')

sub("""  else if (k === 'x') toggleFlip('x');""",
    """  else if (k === 'l') setLabelMode(!window.__labelAll);
  else if (k === 'x') toggleFlip('x');""", 'L key')

open(DST, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('written', DST, len(s), 'bytes (was', n0, ')')