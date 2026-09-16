"""Render a teletext Page into an indexed bitmap.

Implements the Level 1 spacing-attribute rules: set-at vs set-after,
held mosaics, double height, conceal and flash.
"""

from . import font, page as P

# The eight teletext colours, in code order.
PALETTE = [
    (0, 0, 0),        # 0 black
    (255, 0, 0),      # 1 red
    (0, 255, 0),      # 2 green
    (255, 255, 0),    # 3 yellow
    (0, 0, 255),      # 4 blue
    (255, 0, 255),    # 5 magenta
    (0, 255, 255),    # 6 cyan
    (255, 255, 255),  # 7 white
]


class Bitmap(object):
    __slots__ = ('width', 'height', 'pix', 'palette')

    def __init__(self, width, height, palette=None, fill=0):
        self.width = width
        self.height = height
        self.palette = list(palette or PALETTE)
        self.pix = bytearray([fill]) * (width * height)

    def colours_used(self):
        return sorted(set(self.pix))

    def reduce(self, n):
        """Squeeze the image into n colour registers.

        The most-used colours are kept and everything else is remapped to
        its nearest survivor, which is what a 4-register VT240 needs.
        """
        used = self.colours_used()
        if len(used) <= n:
            return self
        counts = {}
        for v in self.pix:
            counts[v] = counts.get(v, 0) + 1
        keep = sorted(used, key=lambda c: -counts[c])[:n]
        if 0 in used and 0 not in keep:
            keep[-1] = 0                    # always keep the paper colour
        keep = sorted(set(keep))
        newpal = [self.palette[c] if c < len(self.palette) else (0, 0, 0)
                  for c in keep]
        remap = {}
        for c in used:
            src = self.palette[c] if c < len(self.palette) else (0, 0, 0)
            best, bestd = 0, None
            for j, dst in enumerate(newpal):
                d = sum((src[k] - dst[k]) ** 2 for k in range(3))
                if bestd is None or d < bestd:
                    best, bestd = j, d
            remap[c] = best
        out = Bitmap(self.width, self.height, newpal)
        out.pix = bytearray(remap[v] for v in self.pix)
        return out

    def to_mono(self, ink=7, paper=0):
        out = Bitmap(self.width, self.height, self.palette)
        out.pix = bytearray(ink if v else paper for v in self.pix)
        return out


class Cell(object):
    __slots__ = ('code', 'fg', 'bg', 'gfx', 'sep', 'dbl', 'flash', 'conceal')

    def __init__(self, code, fg, bg, gfx, sep, dbl, flash, conceal):
        self.code = code
        self.fg = fg
        self.bg = bg
        self.gfx = gfx
        self.sep = sep
        self.dbl = dbl
        self.flash = flash
        self.conceal = conceal


def row_cells(codes):
    """Resolve one row of codes into 40 drawable cells."""
    fg, bg = 7, 0
    gfx = sep = flash = conceal = dbl = False
    hold = False
    held, held_sep = 0x20, False
    cells = []
    for c in codes:
        after = None
        if c < 0x20:
            # --- set-at attributes take effect on this cell ---
            if c == P.STEADY:
                flash = False
            elif c == P.CONCEAL:
                conceal = True
            elif c == P.BLACK_BACKGROUND:
                bg = 0
            elif c == P.NEW_BACKGROUND:
                bg = fg
            elif c == P.HOLD_MOSAICS:
                hold = True
            # --- set-after attributes are queued ---
            elif c <= 0x07:
                after = ('alpha', c)
            elif c == P.FLASH:
                after = ('flash', True)
            elif c == P.NORMAL_HEIGHT:
                after = ('dbl', False)
            elif c == P.DOUBLE_HEIGHT:
                after = ('dbl', True)
            elif 0x10 <= c <= 0x17:
                after = ('gfx', c - 0x10)
            elif c == P.CONTIGUOUS:
                after = ('sep', False)
            elif c == P.SEPARATED:
                after = ('sep', True)
            elif c == P.RELEASE_MOSAICS:
                after = ('hold', False)
            # the attribute cell itself shows a space, or the held mosaic
            if hold and gfx:
                dc, dg, ds = held, True, held_sep
            else:
                dc, dg, ds = 0x20, False, False
        else:
            dc, dg, ds = c, gfx, sep
            if font.is_mosaic(c, gfx):
                held, held_sep = c, sep
        cells.append(Cell(dc, fg, bg, dg, ds, dbl, flash, conceal))
        if after:
            kind, val = after
            if kind == 'alpha':
                fg, gfx = val, False
                held, held_sep = 0x20, False
            elif kind == 'gfx':
                fg, gfx = val, True
            elif kind == 'flash':
                flash = val
            elif kind == 'dbl':
                dbl = val
            elif kind == 'sep':
                sep = val
            elif kind == 'hold':
                hold = val
    return cells


def cell_size(scale):
    """The character cell, in whole pixels, for a scale of 6x9 cells.

    Scale 1.5 is a 9x14 cell rather than 9x13.5: the page is drawn at
    this size directly, so it has to be a whole number of pixels.
    """
    if isinstance(scale, (tuple, list)):
        sx, sy = scale
    else:
        sx = sy = scale
    return (max(1, int(font.CELL_W * sx + 0.5)),
            max(1, int(font.CELL_H * sy + 0.5)))


def render(pg, scale=1, flash_on=True, reveal=False, charset=None,
           rounding=True):
    """Render a Page to a Bitmap at the terminal's own pixels.

    Every character is drawn straight onto its cell by
    font.native_bitmap, so there is no resampling anywhere and each
    stroke has hard edges.  scale is measured in 6x9 cells and may be
    an int, a float, or an (sx, sy) pair; it only picks the cell size.
    With rounding on, diagonals get the corner filling a real teletext
    chip applies wherever a cell is big enough to hold it.
    """
    cw, ch = cell_size(scale)
    return _compose(pg, charset or pg.charset, flash_on, reveal, cw, ch,
                    rounding)


def _compose(pg, charset, flash_on, reveal, cw, ch, rounding):
    bm = Bitmap(P.COLS * cw, P.ROWS * ch)
    r = 0
    while r < P.ROWS:
        cells = row_cells(pg.rows[r])
        _draw_row(bm, cells, r, charset, flash_on, reveal, None, cw, ch,
                  rounding)
        if any(c.dbl for c in cells) and r + 1 < P.ROWS:
            _draw_row(bm, cells, r + 1, charset, flash_on, reveal, 'bottom',
                      cw, ch, rounding)
            r += 2
        else:
            r += 1
    return bm


def _draw_row(bm, cells, screen_row, charset, flash_on, reveal, half,
              cw, ch, rounding):
    y0 = screen_row * ch
    w = bm.width
    pix = bm.pix
    blank = [0] * ch
    for col, cell in enumerate(cells):
        x0 = col * cw
        empty = False
        if half is not None and not cell.dbl:
            empty = True            # lower half of a non-double cell
        if cell.flash and not flash_on:
            empty = True
        if cell.conceal and not reveal:
            empty = True
        if empty:
            bits = blank
        else:
            bits = font.native_bitmap(cell.code, cw, ch, charset, cell.gfx,
                                      cell.sep, rounding)
        fg, bg = cell.fg, cell.bg
        for y in range(ch):
            if cell.dbl and half is None:
                src = y // 2
            elif cell.dbl:
                src = (y + ch) // 2
            else:
                src = y
            row = bits[src] if src < len(bits) else 0
            o = (y0 + y) * w + x0
            if row == 0:
                for x in range(cw):
                    pix[o + x] = bg
            else:
                for x in range(cw):
                    pix[o + x] = fg if (row >> (cw - 1 - x)) & 1 else bg


# ---------------------------------------------------------------------
# Terminal preview (no sixel needed)
# ---------------------------------------------------------------------

_ANSI_FG = [30, 31, 32, 33, 34, 35, 36, 37]
_ANSI_BG = [40, 41, 42, 43, 44, 45, 46, 47]


def _sextant(v):
    """Unicode sextant character for a 6-bit mosaic value."""
    if v == 0:
        return ' '
    if v == 63:
        return '█'
    if v == 21:
        return '▌'
    if v == 42:
        return '▐'
    i = v - 1
    if v > 21:
        i -= 1
    if v > 42:
        i -= 1
    return chr(0x1FB00 + i)


def ansi_preview(pg, flash_on=True, reveal=False, charset=None):
    """40x25 ANSI preview using Unicode sextants for mosaics."""
    charset = charset or pg.charset
    from .page import _CODE_TO_UNI
    table = _CODE_TO_UNI.get(charset, _CODE_TO_UNI['english'])
    out = []
    r = 0
    while r < P.ROWS:
        cells = row_cells(pg.rows[r])
        out.append(_ansi_row(cells, table, flash_on, reveal))
        if any(c.dbl for c in cells) and r + 1 < P.ROWS:
            # sextants cannot show half a glyph; repeat the row dimmed
            out.append(_ansi_row(cells, table, flash_on, reveal, dim=True))
            r += 2
        else:
            r += 1
    return '\n'.join(out)


def _ansi_row(cells, table, flash_on, reveal, dim=False):
    parts = []
    for cell in cells:
        blank = (cell.flash and not flash_on) or (cell.conceal and not reveal)
        if blank:
            ch = ' '
        elif font.is_mosaic(cell.code, cell.gfx):
            ch = _sextant(P.unpack_mosaic(cell.code))
        else:
            ch = table.get(cell.code, ' ')
        sgr = '%d;%d' % (_ANSI_FG[cell.fg], _ANSI_BG[cell.bg])
        if dim:
            sgr += ';2'
        parts.append('\x1b[%sm%s' % (sgr, ch))
    return ''.join(parts) + '\x1b[0m'
