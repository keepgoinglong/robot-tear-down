#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deck follows the burst, so parts that fan down never sink through the floor.

The stage already exposes floor / shadowPlane / floorY, so this just drives them
straight; no re-parenting needed.
"""
import io

FILE = '/sessions/sweet-quirky-hypatia/mnt/outputs/机械臂-三维拆解.html'
s = io.open(FILE, encoding='utf-8', errors='surrogateescape').read()

def sub(a, b, tag):
    global s
    if a not in s:
        print('MISS:', tag); return
    s = s.replace(a, b, 1); print('ok:', tag)

sub("""    p.group.position.set(
      p.axis.x * p.dist * p.p + p.free.x,
      p.axis.y * p.dist * p.p + p.free.y,
      p.axis.z * p.dist * p.p + p.free.z);""",
    """    p.group.position.set(
      p.axis.x * p.dist * p.p + p.free.x,
      p.axis.y * p.dist * p.p + p.free.y,
      p.axis.z * p.dist * p.p + p.free.z);
    var qy = p.box.min.y + p.group.position.y;
    if (qy < lowY) lowY = qy;""", 'lowest scan')

sub("""  var dt = Math.min(.05, clock.getDelta());
  for (var i = 0; i < parts.length; i++) {""",
    """  var dt = Math.min(.05, clock.getDelta());
  var lowY = 1e9;
  for (var i = 0; i < parts.length; i++) {""", 'lowY decl')

sub("""  controls.update(dt);
  stage.update(dt);""",
    """  controls.update(dt);

  /* the lower half fans outward and down; let the deck ride with it so no part
     ever sinks through the grid (the assembled state keeps the floor where it
     was: -D.H * 0.62) */
  var deckTgt = Math.min(stage.floorY, lowY - 30);
  var deckY = A.damp(stage.floor.position.y, deckTgt, 3.5, dt);
  if (Math.abs(deckY - stage.floor.position.y) > 1e-4) {
    stage.floor.position.y = deckY;
    stage.shadowPlane.position.y = deckY + .4;
  }

  stage.update(dt);""", 'deck follow')

io.open(FILE, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('written', len(s))