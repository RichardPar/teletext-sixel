#!/usr/bin/env python3
"""Rebuild docs/logo.svg from docs/logo.ttx.

The logo is an ordinary teletext page, drawn by the same renderer as
every other page, so it is exactly what a terminal shows.  The SVG is
that bitmap as rectangles - one per run of a colour in a row - with
crisp edges, so it stays sharp at any size.

    scripts/logo.py              writes docs/logo.svg
    ./ttx render docs/logo.ttx   the same logo, as sixel
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from teletext import page as P, render  # noqa: E402

ROWS = 11          # the logo occupies the top of the page
SCALE = 2          # 12x18 cells, the teletext chip's own size


def svg(bm, height):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
           'width="%d" height="%d" shape-rendering="crispEdges">'
           % (bm.width, height, bm.width * 2, height * 2),
           '<title>teletext-sixel</title>',
           '<rect width="%d" height="%d" fill="#000"/>' % (bm.width, height)]
    for y in range(height):
        base = y * bm.width
        x = 0
        while x < bm.width:
            v = bm.pix[base + x]
            end = x + 1
            while end < bm.width and bm.pix[base + end] == v:
                end += 1
            if v:
                r, g, b = bm.palette[v]
                out.append('<rect x="%d" y="%d" width="%d" height="1" '
                           'fill="#%02x%02x%02x"/>' % (x, y, end - x, r, g, b))
            x = end
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main():
    pg = P.load(os.path.join(HERE, 'docs', 'logo.ttx'))
    bm = render.render(pg, SCALE)
    height = ROWS * render.cell_size(SCALE)[1]
    path = os.path.join(HERE, 'docs', 'logo.svg')
    with open(path, 'w') as fh:
        fh.write(svg(bm, height))
    print('wrote %s (%dx%d)' % (path, bm.width, height))


if __name__ == '__main__':
    main()
