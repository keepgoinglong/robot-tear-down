#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a script-free twin of the page (same <style> + same body markup) so the
panel layout itself can be screenshotted in the preview panel — the real page
needs WebGL, which the preview panel cannot provide."""
import io, re

SRC = '/sessions/sweet-quirky-hypatia/mnt/outputs/机械臂-三维拆解.html'
DST = '/sessions/sweet-quirky-hypatia/mnt/outputs/_robot/layout_preview.html'
s = io.open(SRC, encoding='utf-8', errors='surrogateescape').read()

head = s[s.index('<style'):s.index('</style>') + 8]

# the preview panel's viewport is only ~537px wide, which trips every responsive
# breakpoint; strip them and render the desktop layout inside a scaled 1400x900
# frame instead (a transform also makes position:fixed elements resolve against
# the frame, which is exactly what the real page does against the viewport)
wide = re.sub(r'@media[^{]*\{.*?\n\}', '', head, flags=re.S)
body = s[s.index('<body'):s.index('<script', s.index('<body'))]

# drop the boot overlay, swap the canvas for a painted backdrop
body = re.sub(r'<div id="boot">.*?</div>\s*</div>\s*</div>', '', body, flags=re.S)
body = body.replace('<canvas id="view"></canvas>',
                    '<div id="view" style="background:'
                    'radial-gradient(58% 48% at 50% 46%,#101c28,#050a0f 72%),'
                    'radial-gradient(60% 44% at 50% 58%,rgba(30,120,180,.20),transparent 70%)"></div>')

NAMES = ['头部', 'sg90数字舵机', '固定块', '固定块', '前盖板', 'STM32', '电池', 'K230D',
         '外壳2', '分线板', 'TTL-5264_8P_Hub', '手臂左', '板件 137×39×24', '旋转连接座左',
         '交叉滚子外圈', '垫圈', '结构件 21×21×6', 'ST3215 数字舵机', '舵机座终版1左左左',
         '连接杆最终左', '底部连接支架左', '脚底板终版左', '盘/环件 36×31×4']
rows = []
for i, n in enumerate(NAMES):
    cls = ' class="done"' if i < 9 else (' class="active"' if i == 9 else '')
    rows.append('<li%s><span class="n">%02d</span><span class="t">%s</span><span class="s">✓</span></li>'
                % (cls, i + 1, n))
body = body.replace('<ol id="steplist"></ol>', '<ol id="steplist">' + ''.join(rows) + '</ol>')
body = body.replace('<b id="stepcount">0/55</b>', '<b id="stepcount">9/55</b>')
body = body.replace('<span id="steppct">0%</span>', '<span id="steppct">16%</span>')
body = body.replace('<i id="steptrack"></i>', '<i id="steptrack" style="right:84%"></i>')

wide_out = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
            + wide + '</head><body style="margin:0;background:#04070b">'
            + '<div style="width:1400px;height:900px;overflow:hidden;'
              'transform:scale(0.383);transform-origin:top left">'
            + body + '</div></body></html>')
io.open(DST.replace('.html', '_wide.html'), 'w', encoding='utf-8',
        errors='surrogateescape').write(wide_out)
print('wrote wide twin', len(wide_out))

out = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1">'
       + head + '</head>' + body + '</body></html>')
io.open(DST, 'w', encoding='utf-8', errors='surrogateescape').write(out)
print('wrote', DST, len(out), 'bytes')
print('boot removed:', 'id="boot"' not in out, '| rail:', '#dock{position:fixed;left:auto' in out)