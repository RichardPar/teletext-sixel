"""SAA5050-style character shapes for Level 1 teletext.

Every character cell is CELL_W x CELL_H pixels.  Alphanumerics use a 5x9
shape placed in columns 0..4, leaving column 5 as the inter-character gap,
exactly like the SAA5050 ROM used by the BBC Micro and most UK sets.

The glyph bitmaps are taken from Bedstead (https://bjh21.me.uk/bedstead/),
Ben Harris and Simon Tatham's reconstruction of the SAA5050 family,
checked against a real chip and dedicated to the public domain (CC0).

Mosaic (block) graphics divide the cell into 2 columns x 3 rows of blocks,
which is why CELL_W/CELL_H are 6 and 9 rather than something rounder.
"""

CELL_W = 6
CELL_H = 9

# Each entry: <hex code> followed by CELL_H row patterns, '#' = ink.
_BASE = """
20 ..... ..... ..... ..... ..... ..... ..... ..... .....
21 ..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#.. ..... .....
22 .#.#. .#.#. .#.#. ..... ..... ..... ..... ..... .....
23 .#.#. .#.#. ##### .#.#. ##### .#.#. .#.#. ..... .....
24 .###. #.#.# #.#.. .###. ..#.# #.#.# .###. ..... .....
25 ##... ##..# ...#. ..#.. .#... #..## ...## ..... .....
26 .#... #.#.. #.#.. .#... #.#.# #..#. .##.# ..... .....
27 ..#.. ..#.. .#... ..... ..... ..... ..... ..... .....
28 ...#. ..#.. .#... .#... .#... ..#.. ...#. ..... .....
29 .#... ..#.. ...#. ...#. ...#. ..#.. .#... ..... .....
2A ..#.. #.#.# .###. ..#.. .###. #.#.# ..#.. ..... .....
2B ..... ..#.. ..#.. ##### ..#.. ..#.. ..... ..... .....
2C ..... ..... ..... ..... ..... ..#.. ..#.. .#... .....
2D ..... ..... ..... .###. ..... ..... ..... ..... .....
2E ..... ..... ..... ..... ..... ..... ..#.. ..... .....
2F ..... ....# ...#. ..#.. .#... #.... ..... ..... .....
30 ..#.. .#.#. #...# #...# #...# .#.#. ..#.. ..... .....
31 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###. ..... .....
32 .###. #...# ....# ..##. .#... #.... ##### ..... .....
33 ##### ....# ...#. ..##. ....# #...# .###. ..... .....
34 ...#. ..##. .#.#. #..#. ##### ...#. ...#. ..... .....
35 ##### #.... ####. ....# ....# #...# .###. ..... .....
36 ..##. .#... #.... ####. #...# #...# .###. ..... .....
37 ##### ....# ...#. ..#.. .#... .#... .#... ..... .....
38 .###. #...# #...# .###. #...# #...# .###. ..... .....
39 .###. #...# #...# .#### ....# ...#. .##.. ..... .....
3A ..... ..... ..#.. ..... ..... ..... ..#.. ..... .....
3B ..... ..... ..#.. ..... ..... ..#.. ..#.. .#... .....
3C ...#. ..#.. .#... #.... .#... ..#.. ...#. ..... .....
3D ..... ..... ##### ..... ##### ..... ..... ..... .....
3E .#... ..#.. ...#. ....# ...#. ..#.. .#... ..... .....
3F .###. #...# ...#. ..#.. ..#.. ..... ..#.. ..... .....
40 .###. #...# #.### #.#.# #.### #.... .###. ..... .....
41 ..#.. .#.#. #...# #...# ##### #...# #...# ..... .....
42 ####. #...# #...# ####. #...# #...# ####. ..... .....
43 .###. #...# #.... #.... #.... #...# .###. ..... .....
44 ####. #...# #...# #...# #...# #...# ####. ..... .....
45 ##### #.... #.... ####. #.... #.... ##### ..... .....
46 ##### #.... #.... ####. #.... #.... #.... ..... .....
47 .###. #...# #.... #.... #..## #...# .#### ..... .....
48 #...# #...# #...# ##### #...# #...# #...# ..... .....
49 .###. ..#.. ..#.. ..#.. ..#.. ..#.. .###. ..... .....
4A ....# ....# ....# ....# ....# #...# .###. ..... .....
4B #...# #..#. #.#.. ##... #.#.. #..#. #...# ..... .....
4C #.... #.... #.... #.... #.... #.... ##### ..... .....
4D #...# ##.## #.#.# #.#.# #...# #...# #...# ..... .....
4E #...# #...# ##..# #.#.# #..## #...# #...# ..... .....
4F .###. #...# #...# #...# #...# #...# .###. ..... .....
50 ####. #...# #...# ####. #.... #.... #.... ..... .....
51 .###. #...# #...# #...# #.#.# #..#. .##.# ..... .....
52 ####. #...# #...# ####. #.#.. #..#. #...# ..... .....
53 .###. #...# #.... .###. ....# #...# .###. ..... .....
54 ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#.. ..... .....
55 #...# #...# #...# #...# #...# #...# .###. ..... .....
56 #...# #...# #...# .#.#. .#.#. ..#.. ..#.. ..... .....
57 #...# #...# #...# #.#.# #.#.# #.#.# .#.#. ..... .....
58 #...# #...# .#.#. ..#.. .#.#. #...# #...# ..... .....
59 #...# #...# .#.#. ..#.. ..#.. ..#.. ..#.. ..... .....
5A ##### ....# ...#. ..#.. .#... #.... ##### ..... .....
5B .#### .#... .#... .#... .#... .#... .#### ..... .....
5C ..... #.... .#... ..#.. ...#. ....# ..... ..... .....
5D ####. ...#. ...#. ...#. ...#. ...#. ####. ..... .....
5E ..#.. .#.#. #...# ..... ..... ..... ..... ..... .....
5F ..... ..... ..... ..... ..... ..... ##### ..... .....
60 .#... ..#.. ...#. ..... ..... ..... ..... ..... .....
61 ..... ..... .###. ....# .#### #...# .#### ..... .....
62 #.... #.... ####. #...# #...# #...# ####. ..... .....
63 ..... ..... .#### #.... #.... #.... .#### ..... .....
64 ....# ....# .#### #...# #...# #...# .#### ..... .....
65 ..... ..... .###. #...# ##### #.... .###. ..... .....
66 ...#. ..#.. ..#.. .###. ..#.. ..#.. ..#.. ..... .....
67 ..... ..... .#### #...# #...# #...# .#### ....# .###.
68 #.... #.... ####. #...# #...# #...# #...# ..... .....
69 ..#.. ..... .##.. ..#.. ..#.. ..#.. .###. ..... .....
6A ..#.. ..... ..#.. ..#.. ..#.. ..#.. ..#.. ..#.. .#...
6B .#... .#... .#..# .#.#. .##.. .#.#. .#..# ..... .....
6C .##.. ..#.. ..#.. ..#.. ..#.. ..#.. .###. ..... .....
6D ..... ..... ##.#. #.#.# #.#.# #.#.# #.#.# ..... .....
6E ..... ..... ####. #...# #...# #...# #...# ..... .....
6F ..... ..... .###. #...# #...# #...# .###. ..... .....
70 ..... ..... ####. #...# #...# #...# ####. #.... #....
71 ..... ..... .#### #...# #...# #...# .#### ....# ....#
72 ..... ..... .#.## .##.. .#... .#... .#... ..... .....
73 ..... ..... .#### #.... .###. ....# ####. ..... .....
74 ..#.. ..#.. .###. ..#.. ..#.. ..#.. ...#. ..... .....
75 ..... ..... #...# #...# #...# #...# .#### ..... .....
76 ..... ..... #...# #...# .#.#. .#.#. ..#.. ..... .....
77 ..... ..... #...# #...# #.#.# #.#.# .#.#. ..... .....
78 ..... ..... #...# .#.#. ..#.. .#.#. #...# ..... .....
79 ..... ..... #...# #...# #...# #...# .#### ....# .###.
7A ..... ..... ##### ...#. ..#.. .#... ##### ..... .....
7B ...## ..#.. ..#.. .#... ..#.. ..#.. ...## ..... .....
7C ..#.. ..#.. ..#.. ..#.. ..#.. ..#.. ..#.. ..... .....
7D ##... ..#.. ..#.. ...#. ..#.. ..#.. ##... ..... .....
7E .#... #.#.# ...#. ..... ..... ..... ..... ..... .....
7F ##### ##### ##### ##### ##### ##### ##### ..... .....
"""

# The English G0 set replaces a handful of ASCII positions.
_ENGLISH = """
23 ..##. .#..# .#... ###.. .#... .#... ##### ..... .....
5B ..... ..#.. .#... ##### .#... ..#.. ..... ..... .....
5C #.... #.... #.... #.... #.##. ....# ...#. ..#.. ..###
5D ..... ..#.. ...#. ##### ...#. ..#.. ..... ..... .....
5E ..... ..#.. .###. #.#.# ..#.. ..#.. ..... ..... .....
5F .#.#. .#.#. ##### .#.#. ##### .#.#. .#.#. ..... .....
60 ..... ..... ..... ##### ..... ..... ..... ..... .....
7B .#... .#... .#... .#... .#..# ...## ..#.# ..### ....#
7C .#.#. .#.#. .#.#. .#.#. .#.#. .#.#. .#.#. ..... .....
7D ##... ..#.. ##... ..#.. ##..# ...## ..#.# ..### ....#
7E ..... ..#.. ..... ##### ..... ..#.. ..... ..... .....
"""


def _parse(table):
    glyphs = {}
    for line in table.strip().splitlines():
        parts = line.split()
        code = int(parts[0], 16)
        rows = parts[1:]
        if len(rows) != CELL_H:
            raise ValueError("glyph %02X has %d rows" % (code, len(rows)))
        bits = []
        for row in rows:
            v = 0
            for x, ch in enumerate(row):
                if ch == '#':
                    # glyph occupies columns 0..4 of a 6-wide cell
                    v |= 1 << (CELL_W - 1 - x)
            bits.append(v)
        glyphs[code] = bits
    return glyphs


ASCII_GLYPHS = _parse(_BASE)
ENGLISH_GLYPHS = dict(ASCII_GLYPHS)
ENGLISH_GLYPHS.update(_parse(_ENGLISH))

CHARSETS = {'ascii': ASCII_GLYPHS, 'english': ENGLISH_GLYPHS}

# Unicode spellings for the English G0 positions that are not plain ASCII.
ENGLISH_UNICODE = {
    0x23: '£',   # £
    0x5B: '←',   # ←
    0x5C: '½',   # ½
    0x5D: '→',   # →
    0x5E: '↑',   # ↑
    0x5F: '#',
    0x60: '—',   # —
    0x7B: '¼',   # ¼
    0x7C: '‖',   # ‖
    0x7D: '¾',   # ¾
    0x7E: '÷',   # ÷
    0x7F: '█',   # █
}

_BLANK = [0] * CELL_H
_cache = {}


def _mosaic_bits(code, sep):
    """Bit rows for a mosaic character.

    Teletext packs the six blocks into the character code as
    bits 0-4 plus bit 6, which is why 0x40-0x5F stay alphanumeric.
    """
    v = (code & 0x1F) | ((code & 0x40) >> 1)
    rows = [0] * CELL_H
    bw, bh = (2, 2) if sep else (3, 3)
    for by in range(3):
        for bx in range(2):
            if not (v >> (by * 2 + bx)) & 1:
                continue
            for y in range(by * 3, by * 3 + bh):
                for x in range(bx * 3, bx * 3 + bw):
                    rows[y] |= 1 << (CELL_W - 1 - x)
    return rows


def char_bitmap(code, charset='english', graphics=False, sep=False):
    """CELL_H rows of CELL_W bits; the MSB of each row is the leftmost pixel."""
    key = (code, charset, graphics, sep)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    if graphics and not 0x40 <= code < 0x60:
        bits = _mosaic_bits(code, sep)
    else:
        bits = CHARSETS.get(charset, ENGLISH_GLYPHS).get(code, _BLANK)
    _cache[key] = bits
    return bits


def is_mosaic(code, graphics):
    return graphics and code >= 0x20 and not 0x40 <= code < 0x60


# When a cell has more pixels than 6x9 but fewer than twice that, some
# source rows and columns get two pixels and some one.  These orders
# decide which.  Columns 0, 2 and 4 carry nearly every vertical stem, so
# they widen first and stems come out even.  Rows 1, 5, 7 and 8 are
# where horizontal strokes almost never sit, so they deepen first and
# the bars of E, e and 3 stay one weight rather than a mix of one and two.
_COL_ORDER = (0, 2, 4, 5, 1, 3)
_ROW_ORDER = (1, 5, 7, 8, 3, 4, 0, 2, 6)
_BLOCK_ORDER = (1, 2, 0)


def _share(total, order):
    """Split total pixels between len(order) source lines."""
    n = len(order)
    sizes = [total // n] * n
    for i in order[:total % n]:
        sizes[i] += 1
    return sizes


def _mosaic_native(code, cell_w, cell_h, sep):
    """Mosaic blocks drawn in the cell's own pixels, never scaled."""
    v = (code & 0x1F) | ((code & 0x40) >> 1)
    widths = [cell_w - cell_w // 2, cell_w // 2]
    heights = _share(cell_h, _BLOCK_ORDER)
    rows = [0] * cell_h
    y0 = 0
    for by in range(3):
        bh = heights[by]
        x0 = 0
        for bx in range(2):
            bw = widths[bx]
            if (v >> (by * 2 + bx)) & 1:
                # separated graphics leave a third of the block as gap
                w = bw - max(1, bw // 3) if sep else bw
                h = bh - max(1, bh // 3) if sep else bh
                mask = 0
                for x in range(x0, x0 + max(1, w)):
                    mask |= 1 << (cell_w - 1 - x)
                for y in range(y0, y0 + max(1, h)):
                    rows[y] |= mask
            x0 += bw
        y0 += bh
    return rows


_native_cache = {}


def native_bitmap(code, cell_w, cell_h, charset='english', graphics=False,
                  sep=False, rounding=True):
    """A character drawn directly on a cell_w x cell_h pixel grid.

    Nothing is resampled.  Each of the 6x9 source pixels becomes a
    whole block of destination pixels - some columns two wide and some
    one, say - so every stroke lands on the pixel grid with hard edges.
    Where a block is at least two pixels each way, diagonals are cut
    along Bedstead's outline (see _bedstead_shape), which is what stops
    teletext text being a staircase; at 12x18 this is exactly the
    SAA5050's own doubled character, and larger cells get smooth
    45-degree edges instead of bigger steps.
    """
    key = (code, cell_w, cell_h, charset, graphics, sep, rounding)
    hit = _native_cache.get(key)
    if hit is not None:
        return hit
    if graphics and not 0x40 <= code < 0x60:
        out = _mosaic_native(code, cell_w, cell_h, sep)
        _native_cache[key] = out
        return out

    bits = char_bitmap(code, charset)
    widths = _share(cell_w, _COL_ORDER)
    heights = _share(cell_h, _ROW_ORDER)

    def on(x, y):
        if not (0 <= x < CELL_W and 0 <= y < CELL_H):
            return False
        return bool((bits[y] >> (CELL_W - 1 - x)) & 1)

    out = []
    for y in range(CELL_H):
        h = heights[y]
        for dy in range(h):
            v = 0
            px = 0
            for x in range(CELL_W):
                w = widths[x]
                inside = None
                if rounding and w >= 2 and h >= 2:
                    inside = _bedstead_shape(on, x, y)
                for dx in range(w):
                    if inside is None:
                        ink = on(x, y)
                    else:
                        ink = _covered(inside, dx, dy, w, h)
                    if ink:
                        v |= 1 << (cell_w - 1 - px)
                    px += 1
            out.append(v)
    _native_cache[key] = out
    return out


# Bedstead's diagonals sit a quarter of a pixel in from the corners.
_Q = 0.25
_SAMPLES = [(i + 0.5) / 4 for i in range(4)]


def _bedstead_shape(on, x, y):
    """The ink inside one source pixel, as a test on (u, v) in 0..1.

    This is the outline construction from Ben Harris and Simon Tatham's
    Bedstead font (CC0, bjh21.me.uk/bedstead): where the SAA5050 would
    fill a corner, a white pixel gains a triangle reaching three
    quarters of the way across, and the ink pixels either side of the
    diagonal lose a small triangle, so a diagonal stroke becomes a
    straight 45-degree edge rather than a staircase.  u runs right and
    v runs down.  Returns None when the pixel is a plain square.
    """
    L, R = on(x - 1, y), on(x + 1, y)
    U, D = on(x, y - 1), on(x, y + 1)
    UL, UR = on(x - 1, y - 1), on(x + 1, y - 1)
    DL, DR = on(x - 1, y + 1), on(x + 1, y + 1)
    q = _Q
    if on(x, y):
        tl = tr = bl = br = True
        if (UL and not U and not L) or (DR and not D and not R):
            tr = bl = False
        if (UR and not U and not R) or (DL and not D and not L):
            tl = br = False
        # where diagonal stems join, trimming would leave a notch
        tl = tl or L or UL or U
        tr = tr or R or UR or U
        bl = bl or L or DL or D
        br = br or R or DR or D
        if tl and tr and bl and br:
            return None
        return lambda u, v: not ((not tl and u + v < q) or
                                 (not tr and 1 - u + v < q) or
                                 (not bl and u + 1 - v < q) or
                                 (not br and 2 - u - v < q))
    tl = L and U and not UL
    tr = R and U and not UR
    bl = L and D and not DL
    br = R and D and not DR
    if not (tl or tr or bl or br):
        return None
    # two triangles in one pixel meet at a notch instead of merging
    return lambda u, v: (
        (tl and u + v < 1 - q and (not bl or v - u < q)) or
        (bl and v - u > q and (not br or u + v < 2 - q)) or
        (tr and u - v > q and (not tl or u + v > 1 - q)) or
        (br and u + v > 2 - q and (not tr or u - v < q)))


def _covered(inside, dx, dy, w, h):
    """Whether most of destination pixel (dx, dy) of a w x h block is ink."""
    hits = 0
    for sy in _SAMPLES:
        for sx in _SAMPLES:
            if inside((dx + sx) / w, (dy + sy) / h):
                hits += 1
    return hits >= 8


def rounded_bitmap(code, charset='english', graphics=False, sep=False):
    """A character doubled to 12x18 with SAA5050-style rounding."""
    return native_bitmap(code, CELL_W * 2, CELL_H * 2, charset, graphics,
                         sep)


def _spans(n, out_n):
    """(index, weight) pairs covering each destination pixel."""
    step = n / float(out_n)
    out = []
    for i in range(out_n):
        lo, hi = i * step, (i + 1) * step
        parts = []
        j = int(lo)
        while j < hi and j < n:
            weight = min(hi, j + 1) - max(lo, j)
            if weight > 0:
                parts.append((j, weight))
            j += 1
        out.append(parts)
    return out


_fit_cache = {}


def fitted_bitmap(code, cell_w, cell_h, charset='english', graphics=False,
                  sep=False, threshold=0.5):
    """A character fitted to an arbitrary cell, by area.

    Every part of the system that draws text - the page renderer, the
    downloaded soft font, the labels on the weather map - comes through
    here, so a character looks the same wherever it is drawn.  The
    source is the rounded 12x18 shape, and a destination pixel takes ink
    when at least `threshold` of its area is ink; sampling the nearest
    source pixel instead thins stems to a hairline.
    """
    key = (code, cell_w, cell_h, charset, graphics, sep, threshold)
    hit = _fit_cache.get(key)
    if hit is not None:
        return hit
    if graphics and not 0x40 <= code < 0x60:
        bits = char_bitmap(code, charset, True, sep)
        src_w, src_h = CELL_W, CELL_H
    else:
        bits = rounded_bitmap(code, charset)
        src_w, src_h = CELL_W * 2, CELL_H * 2
    if (cell_w, cell_h) == (src_w, src_h):
        _fit_cache[key] = bits
        return bits

    xspans = _spans(src_w, cell_w)
    yspans = _spans(src_h, cell_h)
    out = []
    for y in range(cell_h):
        v = 0
        for x in range(cell_w):
            ink = area = 0.0
            for sy, wy in yspans[y]:
                row = bits[sy]
                for sx, wx in xspans[x]:
                    w = wy * wx
                    area += w
                    if (row >> (src_w - 1 - sx)) & 1:
                        ink += w
            if area and ink / area >= threshold:
                v |= 1 << (cell_w - 1 - x)
        out.append(v)
    _fit_cache[key] = out
    return out
