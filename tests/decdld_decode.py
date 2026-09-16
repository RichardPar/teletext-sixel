"""Decode a DECDLD sequence back into glyph bitmaps, so the tests can
check that what we send describes the shapes we meant."""

import re


def decode(data):
    """Return (params, dscs, {code: rows_of_bits}, cell)."""
    m = re.match(r'\x1bP([0-9;]*)\{(.*?)\x1b\\', data, re.S)
    if not m:
        raise ValueError('not a DECDLD sequence')
    params = [int(p or 0) for p in m.group(1).split(';')]
    body = m.group(2)
    # the designating sequence runs up to the first glyph data
    dscs = ''
    i = 0
    while i < len(body) and not (0x3F <= ord(body[i]) <= 0x7E
                                 and body[i] not in ' @A'):
        dscs += body[i]
        i += 1
        if len(dscs) >= 2:
            break
    data_part = body[i:]
    font_number, first, erase, cell_w, _pw, _pt, cell_h, pss = (
        params + [0] * 8)[:8]

    glyphs = {}
    start = 0x21 if pss == 0 else 0x20
    for n, spec in enumerate(data_part.split(';')):
        rows = [0] * cell_h
        for b, band in enumerate(spec.split('/')):
            for x, ch in enumerate(band):
                v = ord(ch) - 0x3F
                for k in range(6):
                    y = b * 6 + k
                    if y < cell_h and (v >> k) & 1:
                        rows[y] |= 1 << (cell_w - 1 - x)
        glyphs[start + first + n] = rows
    return params, dscs, glyphs, (cell_w, cell_h)
