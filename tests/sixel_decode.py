"""A small sixel decoder, used by the tests to prove what we emit is
what a DEC terminal would paint."""

import re


def decode(data):
    """Return (width, height, pixels, palette) from a sixel string."""
    m = re.match(r'\x1bP(\d*);?(\d*);?(\d*)q', data)
    if not m:
        raise ValueError('no sixel introducer')
    i = m.end()
    end = data.find('\x1b\\', i)
    if end < 0:
        raise ValueError('no string terminator')
    body = data[i:end]

    palette = {}
    rows = []          # list of dict x -> colour, per pixel row
    colour = 0
    x = 0
    band = 0
    repeat = 1
    width = height = 0

    def put(value, count):
        nonlocal x
        for _ in range(count):
            for k in range(6):
                if value & (1 << k):
                    y = band + k
                    while len(rows) <= y:
                        rows.append({})
                    rows[y][x] = colour
            x += 1

    j = 0
    n = len(body)
    while j < n:
        ch = body[j]
        if ch == '"':                       # raster attributes
            m2 = re.match(r'"(\d+);(\d+);?(\d*);?(\d*)', body[j:])
            if m2:
                width = int(m2.group(3) or 0)
                height = int(m2.group(4) or 0)
                j += m2.end()
                continue
            j += 1
        elif ch == '#':
            m2 = re.match(r'#(\d+)(?:;(\d+);(\d+);(\d+);(\d+))?', body[j:])
            if not m2:
                raise ValueError('bad colour introducer')
            idx = int(m2.group(1))
            if m2.group(2):
                if m2.group(2) != '2':
                    raise ValueError('only RGB colour space is emitted')
                palette[idx] = tuple(int(m2.group(k)) * 255 // 100
                                     for k in (3, 4, 5))
            colour = idx
            j += m2.end()
        elif ch == '!':
            m2 = re.match(r'!(\d+)', body[j:])
            repeat = int(m2.group(1))
            j += m2.end()
            continue
        elif ch == '$':
            x = 0
            j += 1
        elif ch == '-':
            x = 0
            band += 6
            j += 1
        elif '?' <= ch <= '~':
            put(ord(ch) - 0x3F, repeat)
            repeat = 1
            j += 1
        else:
            j += 1
    if not width:
        width = max((max(r) + 1 if r else 0) for r in rows) if rows else 0
    if not height:
        height = len(rows)
    pixels = [[None] * width for _ in range(height)]
    for y, row in enumerate(rows[:height]):
        for px, c in row.items():
            if px < width:
                pixels[y][px] = c
    return width, height, pixels, palette
