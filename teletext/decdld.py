"""Send pages as text in a downloaded font, instead of as graphics.

A DEC terminal from the VT220 on can be given a soft character set with
DECDLD, and will then draw those shapes from its own character
generator.  Loading the teletext font once costs about 7K; after that a
page is 40x25 characters and a handful of attribute changes - around
1.2K instead of the 7K-25K a sixel image of the same page costs.

The mapping onto the hardware is closer than it sounds:

  teletext 40 columns   -> DECDWL, a double-width line of 40 columns
  teletext double height-> DECDHL, the terminal's own double-height line
  alphanumerics         -> a 94-character soft set in G0
  mosaics               -> a 96-character soft set in G1, switched with
                           SO/SI exactly as teletext switches its own

Parameter semantics are from the DEC documentation; the shapes and the
sixel data are verified by decoding them back (see the tests).  The
matrix limits differ between terminal models, so --cell is adjustable:
a VT340 holds a 10x20 cell, older hardware may cap at 15x12.
"""

from . import font, page as P, render

DCS = '\x1bP'
ST = '\x1b\\'

# Designating sequences.  'Dscs' is the name the terminal knows the set
# by; a space intermediate keeps it clear of the standard registrations.
ALPHA_DSCS = ' @'
MOSAIC_DSCS = ' A'

SO = '\x0e'          # invoke G1 - the mosaics
SI = '\x0f'          # invoke G0 - the alphanumerics


def mosaic_bits(code, cell_w, cell_h, sep=False):
    """Mosaic blocks drawn straight into the cell.

    Scaling a 6x9 mosaic would put the block boundaries in the wrong
    place; the thirds and halves are worked out in the cell's own
    pixels instead.
    """
    v = P.unpack_mosaic(code)
    rows = [0] * cell_h
    xs = [0, cell_w // 2, cell_w]
    ys = [0, cell_h // 3, 2 * cell_h // 3, cell_h]
    for by in range(3):
        for bx in range(2):
            if not (v >> (by * 2 + bx)) & 1:
                continue
            x0, x1 = xs[bx], xs[bx + 1]
            y0, y1 = ys[by], ys[by + 1]
            if sep:                       # leave the gap teletext leaves
                x1 = max(x0 + 1, x1 - 1)
                y1 = max(y0 + 1, y1 - 1)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    rows[y] |= 1 << (cell_w - 1 - x)
    return rows


def glyph_bits(code, cell_w, cell_h, charset='english', graphics=False,
               sep=False):
    """One character as cell_h rows of cell_w bits."""
    if graphics and not 0x40 <= code < 0x60:
        # mosaics are drawn straight into the cell: scaling them would
        # put the block boundaries in the wrong place
        return mosaic_bits(code, cell_w, cell_h, sep)
    return font.fitted_bitmap(code, cell_w, cell_h, charset)


def encode_glyph(bits, cell_w, cell_h):
    """A glyph as DECDLD sixel data: columns of six, bands split by '/'."""
    parts = []
    for band in range(0, cell_h, 6):
        chars = []
        for x in range(cell_w):
            v = 0
            for k in range(6):
                y = band + k
                if y < cell_h and (bits[y] >> (cell_w - 1 - x)) & 1:
                    v |= 1 << k
            chars.append(chr(0x3F + v))
        parts.append(''.join(chars))
    return '/'.join(parts)


def soft_font(cell=(10, 20), charset='english', graphics=False,
              font_number=1, dscs=None, erase=2):
    """A DECDLD sequence defining one teletext character set.

    graphics=False loads the alphanumerics as a 94-character set (0x21
    to 0x7E); graphics=True loads the mosaics as a 96-character set, so
    that 0x20 and 0x7F - the empty and the full block - are included.
    """
    cell_w, cell_h = cell
    if dscs is None:
        dscs = MOSAIC_DSCS if graphics else ALPHA_DSCS
    if graphics:
        first, last, pss = 0x20, 0x7F, 1
    else:
        first, last, pss = 0x21, 0x7E, 0

    glyphs = []
    for code in range(first, last + 1):
        bits = glyph_bits(code, cell_w, cell_h, charset, graphics)
        glyphs.append(encode_glyph(bits, cell_w, cell_h))

    header = '%d;%d;%d;%d;%d;%d;%d;%d' % (
        font_number,        # Pfn  which font buffer
        0,                  # Pcn  first character, counted from the set start
        erase,              # Pe   erase control
        cell_w,             # Pcmw character matrix width
        0,                  # Pw   font width: 0 = the current one
        2,                  # Pt   2 = full cell
        cell_h,             # Pcmh character matrix height
        pss)                # Pss  0 = 94 characters, 1 = 96
    return '%s%s{%s%s%s' % (DCS, header, dscs, ';'.join(glyphs), ST)


def font_download(cell=(10, 20), charset='english'):
    """Both sets, alphanumerics and mosaics."""
    return (soft_font(cell, charset, graphics=False, font_number=1) +
            soft_font(cell, charset, graphics=True, font_number=2))


def wrap(data, width=132):
    """Break a font download into lines a record-oriented filesystem holds.

    A DECDLD sequence is one string of several thousand characters, and
    RSX records are much shorter.  Breaks fall between whole glyph
    definitions, never inside one, and never inside the introducer or
    the terminator; the CR LF that a file's records gain moves the
    cursor but leaves the glyphs being loaded alone.
    """
    lines = []
    line = ''
    i = 0
    while i < len(data):
        if data.startswith(DCS, i):
            # introducer, parameters, and the two-character Dscs
            end = data.find('{', i)
            end = len(data) if end < 0 else min(end + 3, len(data))
            token = data[i:end]
        elif data.startswith(ST, i):
            end = i + len(ST)
            token = data[i:end]
        else:
            semi = data.find(';', i)
            stop = data.find(ST, i)
            if semi >= 0 and (stop < 0 or semi < stop):
                end = semi + 1          # one glyph, with its separator
            elif stop >= 0:
                end = stop
            else:
                end = len(data)
            token = data[i:end]
        if line and len(line) + len(token) > width:
            lines.append(line)
            line = ''
        line += token
        i = end
    if line:
        lines.append(line)
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------
# a page as characters
# ---------------------------------------------------------------------

DECDWL = '\x1b#6'          # double width, single height - 40 columns
DECDHL_TOP = '\x1b#3'
DECDHL_BOTTOM = '\x1b#4'


def _sgr(fg, bg, flash, conceal):
    params = ['0', '3%d' % fg, '4%d' % bg]
    if flash:
        params.append('5')
    if conceal:
        params.append('8')
    return '\x1b[%sm' % ';'.join(params)


def page_text(pg, rows=24, home=True, designate=True, charset=None):
    """A page as characters for a terminal holding the soft font.

    Each teletext row becomes one double-width line, so the 40 columns
    land on an 80-column screen; a row carrying double height becomes
    the terminal's own double-height pair.  Attribute cells are sent as
    spaces, which is what they display.
    """
    charset = charset or pg.charset
    out = []
    if designate:
        out.append('\x1b(%s' % ALPHA_DSCS)     # G0 = alphanumerics
        out.append('\x1b)%s' % MOSAIC_DSCS)    # G1 = mosaics
    if home:
        out.append('\x1b[H')

    line = 1
    r = 0
    while r < P.ROWS and line <= rows:
        cells = render.row_cells(pg.rows[r])
        double = any(c.dbl for c in cells)
        if double and line + 1 > rows:
            break
        for half in ((DECDHL_TOP, DECDHL_BOTTOM) if double else (DECDWL,)):
            out.append('\x1b[%d;1H' % line)
            out.append(half)
            out.append(_row_text(cells, charset))
            line += 1
        r += 2 if double else 1
    out.append(SI)
    out.append('\x1b[0m')
    return ''.join(out)


def _row_text(cells, charset):
    out = []
    state = None
    shifted = False
    for cell in cells:
        want = (cell.fg, cell.bg, cell.flash, cell.conceal)
        if want != state:
            out.append(_sgr(*want))
            state = want
        mosaic = font.is_mosaic(cell.code, cell.gfx)
        if mosaic != shifted:
            out.append(SO if mosaic else SI)
            shifted = mosaic
        code = cell.code
        if not mosaic and code == 0x7F:
            # the solid block is not in the 94-character alpha set;
            # the mosaic set has it as every block filled
            out.append(SO + chr(0x7F) + (SO if shifted else SI))
            continue
        out.append(chr(code))
    if shifted:
        out.append(SI)
    return ''.join(out)
