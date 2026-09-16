"""Image loading, teletext mosaic conversion and direct image->sixel.

No third-party dependencies are required: PNG (non-interlaced) and
Netpbm files are decoded here.  If Pillow happens to be installed it is
used for anything else (JPEG, GIF, WebP...).
"""

import struct
import zlib

from . import page as P, render

PALETTE = render.PALETTE

GFX_W = P.COLS * 2    # 80 mosaic pixels across
GFX_H = P.ROWS * 3    # 75 mosaic pixels down


class Image(object):
    """Truecolour image; pix is a bytearray of RGB triples."""

    __slots__ = ('width', 'height', 'pix')

    def __init__(self, width, height, pix=None):
        self.width = width
        self.height = height
        self.pix = pix if pix is not None else bytearray(width * height * 3)

    def get(self, x, y):
        o = (y * self.width + x) * 3
        return self.pix[o], self.pix[o + 1], self.pix[o + 2]

    def resize(self, w, h, fit=True, pad=(0, 0, 0)):
        """Box-average resize; with fit=True the aspect ratio is kept."""
        if fit:
            scale = min(w / float(self.width), h / float(self.height))
            tw = max(1, int(round(self.width * scale)))
            th = max(1, int(round(self.height * scale)))
        else:
            tw, th = w, h
        tmp = Image(tw, th)
        for ty in range(th):
            sy0 = ty * self.height // th
            sy1 = max(sy0 + 1, (ty + 1) * self.height // th)
            for tx in range(tw):
                sx0 = tx * self.width // tw
                sx1 = max(sx0 + 1, (tx + 1) * self.width // tw)
                r = g = b = n = 0
                for sy in range(sy0, sy1):
                    base = sy * self.width
                    for sx in range(sx0, sx1):
                        o = (base + sx) * 3
                        r += self.pix[o]
                        g += self.pix[o + 1]
                        b += self.pix[o + 2]
                        n += 1
                o = (ty * tw + tx) * 3
                tmp.pix[o] = r // n
                tmp.pix[o + 1] = g // n
                tmp.pix[o + 2] = b // n
        if (tw, th) == (w, h):
            return tmp
        out = Image(w, h, bytearray(bytes(pad) * (w * h)))
        ox, oy = (w - tw) // 2, (h - th) // 2
        for y in range(th):
            src = y * tw * 3
            dst = ((y + oy) * w + ox) * 3
            out.pix[dst:dst + tw * 3] = tmp.pix[src:src + tw * 3]
        return out

    def adjust(self, brightness=1.0, contrast=1.0):
        if brightness == 1.0 and contrast == 1.0:
            return self
        out = Image(self.width, self.height, bytearray(self.pix))
        for i in range(len(out.pix)):
            v = (out.pix[i] - 128) * contrast + 128
            v *= brightness
            out.pix[i] = 0 if v < 0 else (255 if v > 255 else int(v))
        return out


# ---------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------

def load(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return _load_png(data)
    if data[:2] in (b'P5', b'P6', b'P2', b'P3'):
        return _load_pnm(data)
    return _load_pillow(path)


def _load_pillow(path):
    try:
        from PIL import Image as PILImage
    except ImportError:
        raise ValueError('%s: unsupported format (install Pillow for '
                         'JPEG/GIF support)' % path)
    im = PILImage.open(path).convert('RGB')
    out = Image(im.width, im.height, bytearray(im.tobytes()))
    return out


def _load_png(data):
    pos = 8
    idat = []
    w = h = depth = ctype = interlace = 0
    palette = b''
    trns = b''
    while pos < len(data):
        (length,) = struct.unpack('>I', data[pos:pos + 4])
        ctag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctag == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', body)
        elif ctag == b'PLTE':
            palette = body
        elif ctag == b'tRNS':
            trns = body
        elif ctag == b'IDAT':
            idat.append(body)
        elif ctag == b'IEND':
            break
    if interlace:
        raise ValueError('interlaced PNG is not supported')
    if depth not in (1, 2, 4, 8, 16):
        raise ValueError('unsupported PNG bit depth %d' % depth)
    raw = zlib.decompress(b''.join(idat))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, channels * depth // 8)
    stride = (w * channels * depth + 7) // 8
    lines = []
    prev = bytearray(stride)
    o = 0
    for _ in range(h):
        ftype = raw[o]
        o += 1
        line = bytearray(raw[o:o + stride])
        o += stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                c = prev[i - bpp] if i >= bpp else 0
                b = prev[i]
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        lines.append(line)
        prev = line

    img = Image(w, h)
    for y, line in enumerate(lines):
        samples = _unpack_samples(line, depth, w * channels)
        for x in range(w):
            s = samples[x * channels:(x + 1) * channels]
            if ctype == 0:
                v = s[0]
                rgb = (v, v, v)
            elif ctype == 4:
                v = s[0]
                rgb = (v, v, v)
            elif ctype == 2:
                rgb = (s[0], s[1], s[2])
            elif ctype == 6:
                rgb = (s[0], s[1], s[2])
            else:
                i = s[0] * 3
                rgb = (palette[i], palette[i + 1], palette[i + 2])
            o = (y * w + x) * 3
            img.pix[o], img.pix[o + 1], img.pix[o + 2] = rgb
    return img


def _unpack_samples(line, depth, count):
    if depth == 8:
        return line
    if depth == 16:
        return line[0::2]
    out = []
    per = 8 // depth
    mask = (1 << depth) - 1
    scale = 255 // mask
    for byte in line:
        for k in range(per):
            out.append(((byte >> (8 - depth * (k + 1))) & mask) * scale)
            if len(out) >= count:
                return out
    return out


def _load_pnm(data):
    fields = []
    pos = 2
    magic = data[:2]
    while len(fields) < (3 if magic in (b'P5', b'P6', b'P2', b'P3') else 3):
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':
            while data[pos:pos + 1] not in (b'\n', b''):
                pos += 1
            continue
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        fields.append(int(data[start:pos]))
    w, h, maxv = fields
    pos += 1
    img = Image(w, h)
    if magic in (b'P5', b'P6'):
        grey = magic == b'P5'
        n = w * h * (1 if grey else 3)
        body = data[pos:pos + n]
        for i in range(w * h):
            if grey:
                v = body[i] * 255 // maxv
                img.pix[i * 3:i * 3 + 3] = bytes((v, v, v))
            else:
                img.pix[i * 3:i * 3 + 3] = bytes(
                    b * 255 // maxv for b in body[i * 3:i * 3 + 3])
    else:
        vals = [int(v) for v in data[pos:].split()]
        grey = magic == b'P2'
        for i in range(w * h):
            if grey:
                v = vals[i] * 255 // maxv
                img.pix[i * 3:i * 3 + 3] = bytes((v, v, v))
            else:
                img.pix[i * 3:i * 3 + 3] = bytes(
                    v * 255 // maxv for v in vals[i * 3:i * 3 + 3])
    return img


# ---------------------------------------------------------------------
# Image -> teletext mosaics
# ---------------------------------------------------------------------

def _nearest_teletext(rgb, allowed=range(8)):
    best, bestd = 0, None
    for i in allowed:
        pr, pg, pb = render.PALETTE[i]
        d = (rgb[0] - pr) ** 2 + (rgb[1] - pg) ** 2 + (rgb[2] - pb) ** 2
        if bestd is None or d < bestd:
            best, bestd = i, d
    return best


def equalise(img, amount=1.0):
    """Histogram-equalise the luminance, keeping hue.

    With black paper and six blocks per cell, what decides whether a
    picture reads at all is how many blocks end up lit.  A linear
    stretch leaves a dark photograph nearly empty and a bright one
    solid; equalising puts the ink/paper split near the median tone, so
    roughly half the blocks light up whatever the exposure.
    """
    n = img.width * img.height
    hist = [0] * 256
    lums = bytearray(n)
    for i in range(n):
        o = i * 3
        lum = (img.pix[o] * 299 + img.pix[o + 1] * 587
               + img.pix[o + 2] * 114) // 1000
        lums[i] = lum
        hist[lum] += 1
    cdf = []
    run = 0
    for v in range(256):
        run += hist[v]
        cdf.append(run)
    lo = next((c for c in cdf if c), 0)
    span = max(1, n - lo)
    table = [max(0, min(255, ((c - lo) * 255) // span)) for c in cdf]
    if amount < 1.0:
        table = [int(v * amount + i * (1 - amount))
                 for i, v in enumerate(table)]
    out = Image(img.width, img.height, bytearray(img.pix))
    for i in range(n):
        old = lums[i]
        new = table[old]
        o = i * 3
        if old == 0:
            out.pix[o] = out.pix[o + 1] = out.pix[o + 2] = new
            continue
        scale = new / float(old)
        for c in range(3):
            v = int(img.pix[o + c] * scale)
            out.pix[o + c] = 0 if v < 0 else (255 if v > 255 else v)
    return out


def rows_for(img, cols, max_rows, min_rows=3):
    """How many character rows a picture needs at this width.

    Mosaic pixels are square once rendered, so a 16:9 photo in 38 cells
    wants about 11 rows; asking for more just pads it with black bars.
    """
    px_w = cols * 2
    px_h = px_w * img.height / float(img.width)
    return max(min_rows, min(max_rows, int(round(px_h / 3.0))))


def autocontrast(img, low=0.02, high=0.98):
    """Stretch the luminance range; news thumbnails are often flat and
    collapse into a single teletext colour without this."""
    n = img.width * img.height
    hist = [0] * 256
    for i in range(n):
        o = i * 3
        lum = (img.pix[o] * 299 + img.pix[o + 1] * 587
               + img.pix[o + 2] * 114) // 1000
        hist[lum] += 1
    lo, hi, run = 0, 255, 0
    for v in range(256):
        run += hist[v]
        if run >= n * low:
            lo = v
            break
    run = 0
    for v in range(255, -1, -1):
        run += hist[v]
        if run >= n * (1 - high):
            hi = v
            break
    if hi - lo < 16:
        return img
    scale = 255.0 / (hi - lo)
    table = bytes(max(0, min(255, int((v - lo) * scale))) for v in range(256))
    out = Image(img.width, img.height,
                bytearray(table[v] for v in img.pix))
    return out


def _dither_cells(img, gw, h, rows, cols, background, switch_penalty,
                  dither=True, strength=1.0):
    """Quantise into teletext cells, dithering inside each cell.

    A character cell can hold one ink over the paper colour, so the
    error diffusion has to happen between those two colours rather than
    across all eight - dithering the picture into eight colours first
    and then forcing one ink per cell just turns the pattern into noise.
    Cells are visited in reading order, ink chosen from the pixels as
    they stand, then the six blocks are thresholded against that ink
    with the residual pushed into pixels not yet visited.
    """
    buf = [float(v) for v in img.pix]
    bg = PALETTE[background]
    out = []
    current = None
    for cy in range(rows):
        row = []
        for cx in range(cols):
            pix = []
            for by in range(3):
                for bx in range(2):
                    px, py = cx * 2 + bx, cy * 3 + by
                    o = (py * gw + px) * 3
                    pix.append((px, py, buf[o], buf[o + 1], buf[o + 2]))

            best = None
            for ink in range(8):
                if ink == background:
                    continue
                fg = PALETTE[ink]
                cost = 0.0
                for _, _, r, g, b in pix:
                    df = ((r - fg[0]) ** 2 + (g - fg[1]) ** 2 + (b - fg[2]) ** 2)
                    db = ((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2)
                    cost += min(df, db)
                if ink != current:
                    cost += switch_penalty
                if best is None or cost < best[0]:
                    best = (cost, ink)
            ink = best[1]
            fg = PALETTE[ink]

            bits = 0
            for i, (px, py, r, g, b) in enumerate(pix):
                df = (r - fg[0]) ** 2 + (g - fg[1]) ** 2 + (b - fg[2]) ** 2
                db = (r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2
                on = df <= db
                chosen = fg if on else bg
                if on:
                    bits |= 1 << i
                if not dither:
                    continue
                err = (r - chosen[0], g - chosen[1], b - chosen[2])
                for dx, dy, w in ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)):
                    w *= strength
                    nx, ny = px + dx, py + dy
                    if not (0 <= nx < gw and 0 <= ny < h):
                        continue
                    if ny == py and nx <= px:
                        continue
                    o = (ny * gw + nx) * 3
                    for c in range(3):
                        buf[o + c] += err[c] * w / 16.0
                    # refresh this cell's own pending pixels
                    for k in range(i + 1, 6):
                        if pix[k][0] == nx and pix[k][1] == ny:
                            o2 = (ny * gw + nx) * 3
                            pix[k] = (nx, ny, buf[o2], buf[o2 + 1], buf[o2 + 2])
            row.append((ink if bits else None, bits))
            if bits:
                current = ink
        out.append(row)
    return out


def _cell_cost(sub, ink, paper):
    """Bits and error for drawing six subpixels with one ink on one paper."""
    bits, cost = 0, 0
    fg = PALETTE[ink]
    bg = PALETTE[paper]
    for i, idx in enumerate(sub):
        rgb = PALETTE[idx]
        df = ((rgb[0] - fg[0]) ** 2 + (rgb[1] - fg[1]) ** 2
              + (rgb[2] - fg[2]) ** 2)
        db = ((rgb[0] - bg[0]) ** 2 + (rgb[1] - bg[1]) ** 2
              + (rgb[2] - bg[2]) ** 2)
        if df <= db:
            bits |= 1 << i
            cost += df
        else:
            cost += db
    return bits, cost


# One attribute cell is lost at every colour change, so a small gain in
# accuracy is not worth a hole in the picture.
SWITCH_PENALTY = 3 * 255 ** 2


def _emit_colour_row(pg, row, cells, background, sep, hold, left, art_col):
    """Write one row of (ink, bits) cells, spending a cell on each colour
    change.  With hold mosaics on, that cell repeats the previous blocks
    in the previous colour instead of leaving a black notch."""
    col = left
    first_ink = next((ink for ink, _ in cells if ink is not None), 7)
    pg.put(row, col, P.GRAPHICS_BLACK + first_ink)
    col += 1
    if hold:
        pg.put(row, col, P.HOLD_MOSAICS)
        col += 1
    if sep:
        pg.put(row, col, P.SEPARATED)
        col += 1
    current = first_ink
    for ink, bits in cells:
        if col >= P.COLS:
            break
        if ink is not None and ink != current:
            pg.put(row, col, P.GRAPHICS_BLACK + ink)
            current = ink
            col += 1
            if col >= P.COLS:
                break
        pg.put(row, col, P.mosaic_code(bits))
        col += 1


def to_page(img, rows=P.ROWS, top=0, mode='colour', colour='white',
            background=0, fit=True, dither=True, sep=False,
            brightness=1.0, contrast=1.0, target=None, contrast_stretch=True,
            hold=True, switch_penalty=SWITCH_PENALTY, left=0, width=None,
            dither_strength=0.35, equalise_amount=0.8):
    """Convert an image into teletext mosaic graphics on a Page.

    mode 'mono'   - one graphics colour, Floyd-Steinberg dithered
    mode 'colour' - dithered onto the eight colours, then one ink chosen
                    per character cell, biased towards keeping the ink it
                    already has because every change costs a cell
    """
    pg = target or P.Page()
    img = img.adjust(brightness, contrast)
    if contrast_stretch:
        img = autocontrast(img)
    if equalise_amount:
        img = equalise(img, equalise_amount)

    lead = 1 + (1 if hold and mode == 'colour' else 0) + (1 if sep else 0)
    cols = width or (P.COLS - left - lead)
    gw, h = cols * 2, rows * 3
    img = img.resize(gw, h, fit=fit, pad=PALETTE[background])
    art_col = left + lead

    if mode == 'mono':
        ink = (P.COLOUR_NAMES.index(colour)
               if isinstance(colour, str) else int(colour))
        bits = _threshold(img, dither)
        for cy in range(rows):
            row = top + cy
            if row >= P.ROWS:
                break
            col = left
            pg.put(row, col, P.GRAPHICS_BLACK + ink)
            col += 1
            if sep:
                pg.put(row, col, P.SEPARATED)
                col += 1
            for cx in range(cols):
                v = 0
                for by in range(3):
                    for bx in range(2):
                        px, py = cx * 2 + bx, cy * 3 + by
                        if px < gw and py < h and bits[py * gw + px]:
                            v |= 1 << (by * 2 + bx)
                pg.put(row, art_col + cx, P.mosaic_code(v))
        return pg

    grid = _dither_cells(img, gw, h, rows, cols, background, switch_penalty,
                         dither=dither, strength=dither_strength)

    for cy, cells in enumerate(grid):
        row = top + cy
        if row >= P.ROWS:
            break
        _emit_colour_row(pg, row, cells, background, sep, hold, left, art_col)
    return pg


def _threshold(img, dither=True):
    """Return a 0/1 bitmap, optionally Floyd-Steinberg dithered."""
    w, h = img.width, img.height
    lum = [0.0] * (w * h)
    for i in range(w * h):
        o = i * 3
        lum[i] = (0.299 * img.pix[o] + 0.587 * img.pix[o + 1]
                  + 0.114 * img.pix[o + 2])
    bits = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            old = lum[i]
            new = 255.0 if old >= 128 else 0.0
            bits[i] = 1 if new else 0
            if not dither:
                continue
            err = old - new
            if x + 1 < w:
                lum[i + 1] += err * 7 / 16.0
            if y + 1 < h:
                if x:
                    lum[i + w - 1] += err * 3 / 16.0
                lum[i + w] += err * 5 / 16.0
                if x + 1 < w:
                    lum[i + w + 1] += err * 1 / 16.0
    return bits


# ---------------------------------------------------------------------
# Image -> sixel directly (bypassing the teletext grid)
# ---------------------------------------------------------------------

def quantize(img, ncolours=16, dither=True):
    """Median-cut quantisation to an indexed render.Bitmap.

    Error diffusion is worth it here: without it a photograph reduced to
    8 or 16 registers bands badly across skies and skin.
    """
    pixels = [(img.pix[i * 3], img.pix[i * 3 + 1], img.pix[i * 3 + 2])
              for i in range(img.width * img.height)]
    boxes = [list(set(pixels)) or [(0, 0, 0)]]
    while len(boxes) < ncolours:
        boxes.sort(key=lambda b: -_box_range(b))
        target = boxes[0]
        if len(target) < 2:
            break
        ch = _widest_channel(target)
        target.sort(key=lambda c: c[ch])
        mid = len(target) // 2
        boxes = [target[:mid], target[mid:]] + boxes[1:]
    palette = []
    for box in boxes:
        if not box:
            continue
        n = len(box)
        palette.append(tuple(sum(c[k] for c in box) // n for k in range(3)))
    if not palette:
        palette = [(0, 0, 0)]

    bm = render.Bitmap(img.width, img.height, palette)
    w, h = img.width, img.height
    cache = {}

    def nearest(rgb):
        key = (rgb[0] >> 2, rgb[1] >> 2, rgb[2] >> 2)
        idx = cache.get(key)
        if idx is None:
            best, bestd = 0, None
            for j, p in enumerate(palette):
                d = ((rgb[0] - p[0]) ** 2 + (rgb[1] - p[1]) ** 2
                     + (rgb[2] - p[2]) ** 2)
                if bestd is None or d < bestd:
                    best, bestd = j, d
            idx = cache[key] = best
        return idx

    if not dither:
        for i, rgb in enumerate(pixels):
            bm.pix[i] = nearest(rgb)
        return bm

    buf = [float(v) for v in img.pix]
    for y in range(h):
        forward = not (y & 1)
        rng = range(w) if forward else range(w - 1, -1, -1)
        ahead = 1 if forward else -1
        for x in rng:
            o = (y * w + x) * 3
            rgb = tuple(0 if buf[o + c] < 0 else
                        (255 if buf[o + c] > 255 else int(buf[o + c]))
                        for c in range(3))
            idx = nearest(rgb)
            bm.pix[y * w + x] = idx
            chosen = palette[idx]
            for c in range(3):
                err = buf[o + c] - chosen[c]
                nx = x + ahead
                if 0 <= nx < w:
                    buf[(y * w + nx) * 3 + c] += err * 7 / 16.0
                if y + 1 < h:
                    b = ((y + 1) * w + x) * 3 + c
                    buf[b] += err * 5 / 16.0
                    if 0 <= x - ahead < w:
                        buf[b - ahead * 3] += err * 3 / 16.0
                    if 0 <= nx < w:
                        buf[b + ahead * 3] += err * 1 / 16.0
    return bm


def _box_range(box):
    if not box:
        return 0
    return max(max(c[k] for c in box) - min(c[k] for c in box)
               for k in range(3))


def _widest_channel(box):
    spans = [max(c[k] for c in box) - min(c[k] for c in box) for k in range(3)]
    return spans.index(max(spans))


def composite(bm, img, box, ncolours=8, base=8, fit=True, dither=True):
    """Blit a photo into an already-rendered page bitmap.

    Palette registers 0-7 hold the teletext colours, so the photo is
    quantised into registers 8 and up - on a VT340 that is exactly the
    16 colour registers the hardware provides.
    """
    x0, y0, w, h = box
    x0 = max(0, min(x0, bm.width))
    y0 = max(0, min(y0, bm.height))
    w = min(w, bm.width - x0)
    h = min(h, bm.height - y0)
    if w <= 0 or h <= 0:
        return bm
    small = img.resize(w, h, fit=fit, pad=(0, 0, 0))
    q = quantize(small, ncolours, dither=dither)
    bm.palette = list(bm.palette[:base]) + list(q.palette)
    for y in range(h):
        src = y * w
        dst = (y0 + y) * bm.width + x0
        for x in range(w):
            bm.pix[dst + x] = base + q.pix[src + x]
    return bm


def write_png(bm, path):
    """Write an indexed Bitmap as a PNG - handy for checking a page
    without a sixel terminal in front of you."""
    w, h = bm.width, bm.height
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        row = bm.pix[y * w:(y + 1) * w]
        for idx in row:
            r, g, b = bm.palette[idx] if idx < len(bm.palette) else (0, 0, 0)
            raw += bytes((r, g, b))
    def chunk(tag, body):
        return (struct.pack('>I', len(body)) + tag + body
                + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF))
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as fh:
        fh.write(png)
    return path
