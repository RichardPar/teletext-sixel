"""Teletext page model, the .ttx source format, and .tti import/export."""

import re

from . import font

COLS = 40
ROWS = 25

# Level 1 spacing attributes.
ALPHA_BLACK = 0x00
ALPHA_RED = 0x01
ALPHA_GREEN = 0x02
ALPHA_YELLOW = 0x03
ALPHA_BLUE = 0x04
ALPHA_MAGENTA = 0x05
ALPHA_CYAN = 0x06
ALPHA_WHITE = 0x07
FLASH = 0x08
STEADY = 0x09
END_BOX = 0x0A
START_BOX = 0x0B
NORMAL_HEIGHT = 0x0C
DOUBLE_HEIGHT = 0x0D
GRAPHICS_BLACK = 0x10
GRAPHICS_RED = 0x11
GRAPHICS_GREEN = 0x12
GRAPHICS_YELLOW = 0x13
GRAPHICS_BLUE = 0x14
GRAPHICS_MAGENTA = 0x15
GRAPHICS_CYAN = 0x16
GRAPHICS_WHITE = 0x17
CONCEAL = 0x18
CONTIGUOUS = 0x19
SEPARATED = 0x1A
BLACK_BACKGROUND = 0x1C
NEW_BACKGROUND = 0x1D
HOLD_MOSAICS = 0x1E
RELEASE_MOSAICS = 0x1F

COLOUR_NAMES = ['black', 'red', 'green', 'yellow',
                'blue', 'magenta', 'cyan', 'white']

# Markup token -> control code.  Long names are canonical, short ones handy.
TOKENS = {
    'flash': FLASH, 'steady': STEADY,
    'box': START_BOX, 'endbox': END_BOX,
    'normal': NORMAL_HEIGHT, 'double': DOUBLE_HEIGHT,
    'conceal': CONCEAL,
    'contig': CONTIGUOUS, 'sep': SEPARATED,
    'bgblack': BLACK_BACKGROUND, 'newbg': NEW_BACKGROUND,
    'hold': HOLD_MOSAICS, 'release': RELEASE_MOSAICS,
    'nh': NORMAL_HEIGHT, 'dh': DOUBLE_HEIGHT,
}
for _i, _name in enumerate(COLOUR_NAMES):
    TOKENS[_name] = _i                 # {red}   alphanumeric red
    TOKENS['g' + _name] = 0x10 + _i    # {gred}  mosaic red
    TOKENS[_name[0]] = _i              # {r}
    TOKENS['g' + _name[0]] = 0x10 + _i  # {gr}
TOKENS['k'] = ALPHA_BLACK
TOKENS['gk'] = GRAPHICS_BLACK

TOKEN_FOR_CODE = {}
for _t in ('black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan',
           'white', 'gblack', 'gred', 'ggreen', 'gyellow', 'gblue',
           'gmagenta', 'gcyan', 'gwhite', 'flash', 'steady', 'box', 'endbox',
           'normal', 'double', 'conceal', 'contig', 'sep', 'bgblack',
           'newbg', 'hold', 'release'):
    TOKEN_FOR_CODE.setdefault(TOKENS[_t], _t)

# Unicode -> teletext code, per G0 set.
_UNI_TO_CODE = {}
for _cs in ('ascii', 'english'):
    m = {}
    for _c in range(0x20, 0x80):
        m[chr(_c)] = _c
    if _cs == 'english':
        for _code, _ch in font.ENGLISH_UNICODE.items():
            m[_ch] = _code
        # ASCII spellings that no longer have their own glyph fall back
        # to the nearest English-set position.
        m['#'] = 0x5F
        m['£'] = 0x23
    _UNI_TO_CODE[_cs] = m

_CODE_TO_UNI = {}
for _cs, _m in _UNI_TO_CODE.items():
    r = {}
    for _ch, _code in _m.items():
        r.setdefault(_code, _ch)
    if _cs == 'english':
        r.update({c: u for c, u in font.ENGLISH_UNICODE.items()})
    _CODE_TO_UNI[_cs] = r


class Page(object):
    """A 40x25 grid of 7-bit teletext codes plus a little metadata."""

    def __init__(self, charset='english', number=100, title='', flash_ok=True):
        self.rows = [[0x20] * COLS for _ in range(ROWS)]
        self.charset = charset
        self.number = number
        self.title = title
        self.meta = {}

    # -- cell access ----------------------------------------------------
    def get(self, row, col):
        return self.rows[row][col]

    def put(self, row, col, code):
        if 0 <= row < ROWS and 0 <= col < COLS:
            self.rows[row][col] = code & 0x7F

    def write(self, row, col, text, charset=None):
        """Write a markup string starting at (row, col); returns next column."""
        for code in encode_line(text, charset or self.charset):
            if col >= COLS:
                break
            self.put(row, col, code)
            col += 1
        return col

    def clear(self):
        for r in range(ROWS):
            for c in range(COLS):
                self.rows[r][c] = 0x20

    def copy(self):
        p = Page(self.charset, self.number, self.title)
        p.rows = [list(r) for r in self.rows]
        p.meta = dict(self.meta)
        return p

    # -- mosaic helpers -------------------------------------------------
    def set_pixel(self, px, py, on=True, origin=(0, 0)):
        """Set one of the 80x75 mosaic pixels (2x3 per character cell)."""
        row = origin[0] + py // 3
        col = origin[1] + px // 2
        if not (0 <= row < ROWS and 0 <= col < COLS):
            return
        cur = self.rows[row][col]
        v = (cur & 0x1F) | ((cur & 0x40) >> 1) if cur >= 0x20 else 0
        bit = 1 << ((py % 3) * 2 + (px % 2))
        v = (v | bit) if on else (v & ~bit)
        self.rows[row][col] = mosaic_code(v)

    def draw_mosaic(self, row, col, art, colour=None, sep=False):
        """Draw '#'/'.' pixel art; each source line is one 2x3 pixel row.

        The graphics colour (and the separated-mosaics code, if asked
        for) occupy the cells immediately to the left of the art, as
        they must on a real Level 1 page.
        """
        if isinstance(colour, str):
            colour = COLOUR_NAMES.index(colour)
        codes = []
        if colour is not None:
            codes.append(GRAPHICS_BLACK + colour)
        if sep:
            codes.append(SEPARATED)
        for n, code in enumerate(codes):
            at = col - len(codes) + n
            self.put(row, max(0, at), code)
        cells = {}
        for py, line in enumerate(art):
            for px, ch in enumerate(line):
                if ch in ('#', '1', '*', 'X', 'x'):
                    key = (row + py // 3, col + px // 2)
                    cells[key] = cells.get(key, 0) | 1 << ((py % 3) * 2 + (px % 2))
        rows_used = (len(art) + 2) // 3
        for r in range(row, row + rows_used):
            for n, code in enumerate(codes):
                self.put(r, max(0, col - len(codes) + n), code)
        for (r, c), v in cells.items():
            self.put(r, c, mosaic_code(v))

    # -- text view ------------------------------------------------------
    def to_text(self):
        """Plain-text dump; control codes shown as spaces."""
        out = []
        for row in self.rows:
            out.append(''.join(
                _CODE_TO_UNI[self.charset].get(c, ' ') if c >= 0x20 else ' '
                for c in row).rstrip())
        return '\n'.join(out)


# The four FASTEXT keys, in the order every teletext service used them.
FASTEXT_COLOURS = ('red', 'green', 'yellow', 'cyan')


def fastext_bar(pg, links, row=ROWS - 1):
    """The coloured link bar along the bottom of a page.

    links is up to four (label, page) pairs; they are laid out in equal
    segments across the 40 columns, each starting with its own colour
    code - which costs a cell, as every teletext attribute does.
    """
    links = [l for l in links if l][:len(FASTEXT_COLOURS)]
    if not links:
        return
    width = COLS // len(links)
    text = []
    for i, link in enumerate(links):
        label, number = link if isinstance(link, (tuple, list)) else (link, '')
        caption = ('%s %s' % (label, number)).strip()
        text.append('{%s}%s' % (FASTEXT_COLOURS[i],
                                caption[:width - 1].ljust(width - 1)))
    pg.write(row, 0, ''.join(text).rstrip())


def mosaic_code(v):
    """Pack 6 mosaic bits into a teletext character code."""
    v &= 0x3F
    return 0x20 + (v & 0x1F) + (0x40 if v & 0x20 else 0)


def unpack_mosaic(code):
    return (code & 0x1F) | ((code & 0x40) >> 1)


_TOKEN_RE = re.compile(r'\{([a-zA-Z0-9.#]+)\}')


def encode_line(text, charset='english'):
    """Turn one markup line into a list of teletext codes."""
    codes = []
    uni = _UNI_TO_CODE[charset]
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '{':
            if text.startswith('{{', i):
                codes.append(uni.get('{', 0x7B))
                i += 2
                continue
            m = _TOKEN_RE.match(text, i)
            if m:
                name = m.group(1)
                key = name if name in TOKENS else name.lower()
                if key in TOKENS:
                    codes.append(TOKENS[key])
                    i = m.end()
                    continue
                if re.fullmatch(r'[0-9a-fA-F]{2}', name):
                    codes.append(int(name, 16) & 0x7F)
                    i = m.end()
                    continue
                if re.fullmatch(r'[.#]{6}', name):
                    v = sum(1 << b for b in range(6) if name[b] == '#')
                    codes.append(mosaic_code(v))
                    i = m.end()
                    continue
                raise ValueError('unknown token {%s}' % name)
        codes.append(uni.get(ch, 0x20))
        i += 1
    return codes


def decode_line(codes, charset='english'):
    """Inverse of encode_line: codes back to editable markup."""
    out = []
    table = _CODE_TO_UNI[charset]
    for c in codes:
        if c < 0x20:
            out.append('{%s}' % TOKEN_FOR_CODE.get(c, '%02X' % c))
        elif c == 0x7B and charset == 'ascii':
            out.append('{{')
        else:
            out.append(table.get(c, ' '))
    return ''.join(out).rstrip()


# ---------------------------------------------------------------------
# .ttx source files
# ---------------------------------------------------------------------

def parse(text, charset='english', warn=True):
    """Parse .ttx source into a Page.

    Directives start with '!', comments with '#' in column 1, and every
    other line is the next display row.  Rows and graphic blocks are
    applied in document order, so a later line overwrites an earlier one.
    """
    page = Page(charset=charset)
    row = 0
    ops = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if line.startswith('#'):
            continue
        if line.startswith('!'):
            parts = line[1:].split(None, 1)
            if not parts:
                continue
            name = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ''
            if name == 'charset':
                page.charset = arg.strip() or 'english'
            elif name == 'title':
                page.title = arg.strip()
            elif name == 'page':
                page.number = arg.strip()
            elif name == 'row':
                bits = arg.split(None, 1)
                row = int(bits[0])
                if len(bits) > 1:
                    ops.append(('text', row, bits[1]))
                    row += 1
            elif name == 'graphic':
                opts = _kvopts(arg)
                art = []
                while i < len(lines) and not lines[i].lower().startswith('!end'):
                    art.append(lines[i])
                    i += 1
                i += 1
                top = int(opts.get('row', row))
                ops.append(('graphic', top, art,
                            opts.get('colour', opts.get('color')),
                            int(opts.get('col', 1)),
                            opts.get('sep', '0') not in ('0', 'no', 'false')))
                row = top + (len(art) + 2) // 3
            elif name == 'body':
                # Written by an earlier version for a plain-text renderer
                # that no longer exists.  Skipped rather than rejected so
                # pages built then still load.
                while i < len(lines) and not lines[i].lower().startswith('!end'):
                    i += 1
                i += 1
            elif name in ('end', 'endgraphic', 'endbody'):
                continue
            elif name == 'meta':
                k, _, v = arg.partition('=')
                page.meta[k.strip()] = v.strip()
            else:
                raise ValueError('unknown directive !%s' % name)
            continue
        ops.append(('text', row, line))
        row += 1

    for op in ops:
        if op[0] == 'text':
            _, r, line = op
            if not 0 <= r < ROWS:
                continue
            codes = encode_line(line, page.charset)
            if warn and len(codes) > COLS:
                import sys
                sys.stderr.write('warning: row %d is %d cells wide, '
                                 'truncated to %d\n' % (r, len(codes), COLS))
            codes = codes[:COLS]
            page.rows[r] = codes + [0x20] * (COLS - len(codes))
        else:
            _, r, art, colour, col, sep = op
            page.draw_mosaic(r, col, art, colour=colour, sep=sep)
    return page


def _kvopts(arg):
    opts = {}
    for tok in arg.split():
        k, _, v = tok.partition('=')
        opts[k.lower()] = v
    return opts


def serialize(page):
    out = []
    if page.title:
        out.append('!title %s' % page.title)
    if page.number:
        out.append('!page %s' % page.number)
    if page.charset != 'english':
        out.append('!charset %s' % page.charset)
    for k, v in sorted(page.meta.items()):
        if k.startswith('_'):
            continue        # internal bookkeeping, not part of the file
        out.append('!meta %s = %s' % (k, v))
    for row in page.rows:
        out.append(decode_line(row, page.charset))
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out) + '\n'


def load(path):
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    if path.lower().endswith('.tti'):
        return load_tti(text)
    return parse(text)


def save(page, path):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(serialize(page))


# ---------------------------------------------------------------------
# .tti (MRG / edit.tf interchange)
# ---------------------------------------------------------------------

def load_tti(text):
    """Read an MRG-style .tti file (OL lines, ESC-escaped control codes)."""
    page = Page()
    for line in text.splitlines():
        if ',' not in line:
            continue
        kind, _, rest = line.partition(',')
        kind = kind.strip().upper()
        if kind == 'OL':
            num, _, data = rest.partition(',')
            try:
                row = int(num)
            except ValueError:
                continue
            codes = []
            esc = False
            for ch in data:
                b = ord(ch) & 0xFF
                if esc:
                    codes.append((b - 0x40) & 0x7F)
                    esc = False
                elif b == 0x1B:
                    esc = True
                else:
                    codes.append(b & 0x7F)
            if 0 <= row < ROWS:
                codes = codes[:COLS]
                page.rows[row] = codes + [0x20] * (COLS - len(codes))
        elif kind == 'PN':
            page.number = rest.strip()
        elif kind == 'DE':
            page.title = rest.strip()
    return page


def dump_tti(page):
    out = ['PN,%s' % (page.number or '10000')]
    if page.title:
        out.append('DE,%s' % page.title)
    for r, row in enumerate(page.rows):
        data = []
        for c in row:
            if c < 0x20:
                data.append('\x1b' + chr(c + 0x40))
            else:
                data.append(chr(c))
        out.append('OL,%d,%s' % (r, ''.join(data)))
    return '\r\n'.join(out) + '\r\n'
