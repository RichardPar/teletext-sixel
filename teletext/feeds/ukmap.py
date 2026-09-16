"""A map of the UK, drawn for the weather pages.

The coastline is a coarse polygon in degrees, projected with the
longitude squeezed by the cosine of the middle latitude so the country
keeps its shape.  Cities are plotted where they actually are, which is
what makes a weather map readable at this size.
"""

import math

from .. import font, imageconv

# Great Britain, clockwise from Land's End.  Coarse: at the size these
# maps are drawn, a point every twenty miles is more than enough.
GB = [
    (50.07, -5.72), (50.20, -5.40), (50.35, -4.70), (50.37, -4.14),
    (50.60, -3.40), (50.72, -3.00), (50.58, -2.45), (50.72, -1.90),
    (50.80, -1.10), (50.74, 0.25), (51.13, 1.33), (51.38, 1.40),
    (51.55, 0.70), (51.72, 0.95), (52.08, 1.62), (52.48, 1.75),
    (52.93, 1.30), (52.80, 0.55), (52.90, 0.30), (53.30, 0.15),
    (53.60, 0.10), (53.70, -0.30), (54.12, -0.08), (54.50, -0.60),
    (54.62, -1.08), (55.00, -1.40), (55.55, -1.60), (55.77, -2.00),
    (56.05, -2.60), (56.10, -3.20), (56.45, -2.80), (56.75, -2.50),
    (57.15, -2.09), (57.50, -1.78), (57.70, -2.00), (57.68, -3.50),
    (57.60, -4.00), (57.85, -3.90), (58.30, -3.20), (58.64, -3.07),
    (58.60, -4.20), (58.62, -5.00), (58.20, -5.30), (57.90, -5.20),
    (57.55, -5.80), (57.30, -5.70), (56.90, -5.80), (56.60, -6.10),
    (56.40, -5.90), (56.10, -5.60), (55.60, -5.10), (55.30, -5.60),
    (55.45, -4.90), (55.00, -4.80), (54.85, -5.00), (54.90, -4.00),
    (54.95, -3.60), (54.65, -3.50), (54.20, -3.20), (54.10, -2.90),
    (53.75, -3.05), (53.42, -3.10), (53.35, -3.70), (53.30, -4.60),
    (52.90, -4.50), (52.55, -4.10), (52.10, -4.40), (51.85, -5.30),
    (51.70, -5.20), (51.62, -4.30), (51.45, -3.20), (51.38, -2.70),
    (51.22, -3.30), (51.10, -4.20), (50.80, -4.55), (50.55, -4.90),
    (50.35, -5.15), (50.07, -5.72),
]

# Ireland, for Belfast and the shape of the sea between.
IRELAND = [
    (55.38, -7.37), (55.25, -6.50), (54.85, -5.75), (54.60, -5.55),
    (54.25, -5.55), (54.05, -6.05), (53.85, -6.10), (53.35, -6.10),
    (52.95, -6.02), (52.25, -6.35), (52.15, -7.10), (51.85, -8.30),
    (51.60, -9.90), (52.05, -10.45), (52.55, -9.90), (53.00, -9.90),
    (53.40, -9.90), (54.00, -10.10), (54.30, -10.00), (54.30, -8.80),
    (54.65, -8.80), (55.05, -8.30), (55.38, -7.37),
]

CITIES = {
    'London': (51.51, -0.13), 'Cambridge': (52.21, 0.12),
    'Southampton': (50.90, -1.40), 'Plymouth': (50.37, -4.14),
    'Bristol': (51.45, -2.59), 'Cardiff': (51.48, -3.18),
    'Swansea': (51.62, -3.94), 'Norwich': (52.63, 1.30),
    'Birmingham': (52.48, -1.90), 'Nottingham': (52.95, -1.15),
    'Manchester': (53.48, -2.24), 'Liverpool': (53.41, -2.99),
    'Leeds': (53.80, -1.55), 'Newcastle': (54.97, -1.61),
    'Belfast': (54.60, -5.93), 'Glasgow': (55.86, -4.25),
    'Edinburgh': (55.95, -3.19), 'Aberdeen': (57.15, -2.09),
    'Inverness': (57.48, -4.22),
}

BOUNDS = (49.8, 59.2, -10.8, 2.2)        # south, north, west, east

SEA = (0, 0, 60)
LAND = (20, 70, 30)
COAST = (120, 200, 140)


class Projection(object):
    """Equirectangular, with longitude squeezed to keep the shape."""

    def __init__(self, width, height, bounds=BOUNDS):
        south, north, west, east = bounds
        self.bounds = bounds
        mid = math.radians((south + north) / 2.0)
        self.kx = math.cos(mid)
        span_x = (east - west) * self.kx
        span_y = north - south
        self.scale = min(width / span_x, height / span_y)
        self.width, self.height = width, height
        self.ox = (width - span_x * self.scale) / 2.0
        self.oy = (height - span_y * self.scale) / 2.0

    def __call__(self, lat, lon):
        south, _north, west, _east = self.bounds
        x = self.ox + (lon - west) * self.kx * self.scale
        y = self.height - self.oy - (lat - south) * self.scale
        return int(round(x)), int(round(y))


def _fill(img, points, colour):
    """Scanline fill of a closed polygon."""
    if len(points) < 3:
        return
    ys = [p[1] for p in points]
    for y in range(max(0, min(ys)), min(img.height, max(ys) + 1)):
        xs = []
        for i in range(len(points)):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % len(points)]
            if y1 == y2:
                continue
            if min(y1, y2) <= y < max(y1, y2):
                xs.append(x1 + (y - y1) * (x2 - x1) / float(y2 - y1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(max(0, int(xs[i])), min(img.width,
                                                   int(xs[i + 1]) + 1)):
                o = (y * img.width + x) * 3
                img.pix[o:o + 3] = bytes(colour)


def _line(img, x1, y1, x2, y2, colour):
    steps = max(abs(x2 - x1), abs(y2 - y1))
    if steps == 0:
        steps = 1
    for i in range(steps + 1):
        x = int(round(x1 + (x2 - x1) * i / float(steps)))
        y = int(round(y1 + (y2 - y1) * i / float(steps)))
        if 0 <= x < img.width and 0 <= y < img.height:
            o = (y * img.width + x) * 3
            img.pix[o:o + 3] = bytes(colour)


def _text(img, x, y, text, colour, charset='english', scale=1):
    """Draw with the teletext font, from the same fitted shapes the page
    renderer and the soft font use, so a label matches the text around
    it."""
    from ..page import _UNI_TO_CODE
    table = _UNI_TO_CODE.get(charset, _UNI_TO_CODE['english'])
    for ch in text:
        bits = font.fitted_bitmap(table.get(ch, 0x20), font.CELL_W,
                                  font.CELL_H, charset)
        for row in range(font.CELL_H):
            for col in range(font.CELL_W):
                if not (bits[row] >> (font.CELL_W - 1 - col)) & 1:
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        px, py = x + col * scale + dx, y + row * scale + dy
                        if 0 <= px < img.width and 0 <= py < img.height:
                            o = (py * img.width + px) * 3
                            img.pix[o:o + 3] = bytes(colour)
        x += font.CELL_W * scale
    return x


def draw(width, height, marks=(), charset='english'):
    """The map, with marks as (city, text, rgb).

    Labels that would sit on top of one another are dropped rather than
    overprinted - the south east is crowded at this size.
    """
    img = imageconv.Image(width, height,
                          bytearray(bytes(SEA) * (width * height)))
    proj = Projection(width, height)
    for shape in (IRELAND, GB):
        pts = [proj(lat, lon) for lat, lon in shape]
        _fill(img, pts, LAND)
        for i in range(len(pts) - 1):
            _line(img, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                  COAST)

    taken = []
    for city, text, colour in marks:
        if city not in CITIES:
            continue
        x, y = proj(*CITIES[city])
        w = len(text) * font.CELL_W + 4
        box = (x + 3, y - 5, x + 3 + w, y + 5)
        if any(not (box[2] < t[0] or box[0] > t[2] or
                    box[3] < t[1] or box[1] > t[3]) for t in taken):
            continue
        taken.append(box)
        for dy in (-1, 0, 1):               # the city itself
            for dx in (-1, 0, 1):
                if 0 <= x + dx < width and 0 <= y + dy < height:
                    o = ((y + dy) * width + x + dx) * 3
                    img.pix[o:o + 3] = bytes((255, 255, 255))
        _text(img, x + 4, y - 4, text, colour, charset)
    return img
