"""Sixel encoder.

Output targets DEC sixel terminals: VT240/VT241 (mono/4 colour),
VT330 (mono) and VT340 (16 colour registers, 800x480) - the terminals
you are likely to have hanging off a PDP-11.
"""

import os
import re
import select
import sys
import time

DCS = '\x1bP'
ST = '\x1b\\'

# Conservative register counts by terminal family.
TERMINALS = {
    'vt125': {'colours': 4, 'width': 768, 'height': 460},
    'vt240': {'colours': 4, 'width': 800, 'height': 480},
    'vt241': {'colours': 4, 'width': 800, 'height': 480},
    'vt330': {'colours': 4, 'width': 800, 'height': 480},
    'vt340': {'colours': 16, 'width': 800, 'height': 480},
    'xterm': {'colours': 256, 'width': 1000, 'height': 1000},
}


def encode(bitmap, transparent=False, aspect=(1, 1), raster=True,
           background=None, max_colours=None, solid_fill_off=False):
    """Encode an indexed Bitmap as a sixel data string.

    transparent - leave palette index 0 unpainted (P2=1)
    aspect      - (Pan, Pad) pixel aspect ratio for the raster attributes
    background  - if not None, paint the whole area with this index first
    """
    w, h = bitmap.width, bitmap.height
    pix = bitmap.pix
    palette = bitmap.palette
    if max_colours:
        palette = palette[:max_colours]

    out = []
    p2 = 1 if transparent else 0
    out.append('%s0;%d;0q' % (DCS, p2))
    if raster:
        out.append('"%d;%d;%d;%d' % (aspect[0], aspect[1], w, h))

    used = set(pix)
    for idx, rgb in enumerate(palette):
        if idx not in used and idx != background:
            continue
        r, g, b = rgb
        out.append('#%d;2;%d;%d;%d' % (idx,
                                       (r * 100 + 127) // 255,
                                       (g * 100 + 127) // 255,
                                       (b * 100 + 127) // 255))

    for band in range(0, h, 6):
        rows = []
        for k in range(6):
            y = band + k
            rows.append(pix[y * w:(y + 1) * w] if y < h else None)
        # a partial last band must not paint rows past the raster
        full = 0
        for k, row in enumerate(rows):
            if row is not None:
                full |= 1 << k

        counts = {}
        for row in rows:
            if row is None:
                continue
            for v in row:
                counts[v] = counts.get(v, 0) + 1
        present = set(counts)
        if transparent:
            present.discard(0)

        first = True
        base = None
        if not transparent and present and not solid_fill_off:
            # Lay the band's commonest colour down as one run and paint
            # the rest over it.  Sixel passes overwrite, and encoding
            # that colour's actual mask - all the gaps around the text -
            # costs far more than the few bytes this does.
            base = max(present, key=lambda c: counts[c])
            if base < len(palette):
                out.append('#%d' % base)
                out.append('!%d%s' % (w, chr(0x3F + full)) if w > 3
                           else chr(0x3F + full) * w)
                first = False
            else:
                base = None

        for colour in sorted(present):
            if colour >= len(palette) or colour == base:
                continue
            sixels = bytearray(w)
            for k, row in enumerate(rows):
                if row is None:
                    continue
                bit = 1 << k
                for x in range(w):
                    if row[x] == colour:
                        sixels[x] |= bit
            if not first:
                out.append('$')
            first = False
            out.append('#%d' % colour)
            out.append(_rle(sixels))
        out.append('-')

    out.append(ST)
    return ''.join(out)


def _rle(sixels):
    """Run-length encode one band, dropping trailing empty sixels."""
    n = len(sixels)
    while n and sixels[n - 1] == 0:
        n -= 1
    parts = []
    i = 0
    while i < n:
        v = sixels[i]
        j = i + 1
        while j < n and sixels[j] == v:
            j += 1
        run = j - i
        ch = chr(0x3F + v)
        parts.append('!%d%s' % (run, ch) if run > 3 else ch * run)
        i = j
    return ''.join(parts)


def sequence(bitmap, terminal='vt340', clear=False, home=False,
             transparent=False, aspect=(1, 1), max_colours=None):
    """Sixel data wrapped with any cursor/screen setup the terminal needs."""
    pre = []
    if clear:
        pre.append('\x1b[2J')
    if clear or home:
        pre.append('\x1b[H')
    info = TERMINALS.get(terminal, TERMINALS['vt340'])
    data = encode(bitmap, transparent=transparent, aspect=aspect,
                  max_colours=max_colours or info['colours'])
    return ''.join(pre) + data


def fits(bitmap, terminal='vt340'):
    info = TERMINALS.get(terminal)
    if not info:
        return True, ''
    if bitmap.width <= info['width'] and bitmap.height <= info['height']:
        return True, ''
    return False, ('%dx%d exceeds the %s raster of %dx%d'
                   % (bitmap.width, bitmap.height, terminal.upper(),
                      info['width'], info['height']))


def _ask(request, pattern, timeout=0.4):
    """Send a query to the terminal and match its reply, or None."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    try:
        import termios
        import tty
    except ImportError:
        return None
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        return None
    buf = ''
    try:
        tty.setraw(fd)
        sys.stdout.write(request)
        sys.stdout.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], deadline - time.time())
            if not ready:
                break
            buf += os.read(fd, 64).decode('latin-1', 'replace')
            m = re.search(pattern, buf)
            if m:
                return m
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return re.search(pattern, buf)


def detect(timeout=0.4):
    """Ask the terminal whether it does sixel: a DA1 reply listing 4.

    Returns True, False, or None when the question cannot be asked at
    all - output redirected to a file, for instance.
    """
    m = _ask('\x1b[c', r'\x1b\[\?([0-9;]+)c', timeout)
    if not m:
        return None
    return '4' in m.group(1).split(';')


def colour_registers(timeout=0.4):
    """How many sixel colour registers the terminal actually has.

    XTSMGRAPHICS, item 1.  This matters: xterm defaults to 16 registers
    unless numColorRegisters says otherwise, and writing past that count
    corrupts the picture rather than failing cleanly.
    """
    m = _ask('\x1b[?1;1S', r'\x1b\[\?1;([0-9]+);([0-9]+)S', timeout)
    if not m or m.group(1) != '0':
        return None
    try:
        return int(m.group(2))
    except ValueError:
        return None


def graphics_size(timeout=0.4):
    """The terminal's maximum graphics geometry, or None.  XTSMGRAPHICS
    item 2."""
    m = _ask('\x1b[?2;1S', r'\x1b\[\?2;([0-9]+);([0-9]+);([0-9]+)S',
             timeout)
    if not m or m.group(1) != '0':
        return None
    return int(m.group(2)), int(m.group(3))


ADVICE = """this terminal did not report sixel support in its DA1 reply.
xterm has to be told it is a VT340:
    xterm -ti vt340 -tn xterm-256color
or put this in your X resources:
    XTerm*decTerminalID: 340
    XTerm*numColorRegisters: 256
"""


def cell_size(timeout=0.4):
    """The terminal's character cell in pixels, as (width, height).

    CSI 16 t; xterm answers CSI 6 ; height ; width t.  Knowing this is
    what lets a page mix sixel images with ordinary text and still work
    out how many text rows are left over.
    """
    m = _ask('\x1b[16t', r'\x1b\[6;([0-9]+);([0-9]+)t', timeout)
    if not m:
        return None
    height, width = int(m.group(1)), int(m.group(2))
    if not (0 < width < 100 and 0 < height < 200):
        return None
    return width, height


_TOKEN_RE = re.compile(
    r'\x1bP[0-9;]*q'          # the introducer
    r'|"[0-9;]+'               # raster attributes
    r'|#[0-9]+(?:;[0-9;]+)?'   # a colour definition or selection
    r'|![0-9]+[?-~]'           # a run-length token
    r'|\x1b\\'                # the terminator
    r'|[?-~$-]'                # one sixel, a carriage return, a band end
)


def wrap(data, width=480):
    """Break sixel data into lines a record-oriented filesystem can hold.

    RSX files have a maximum record length and a page is one line of
    several thousand characters.  Breaks fall only between whole tokens
    - never inside a run-length count or a colour definition, where a
    newline would change the picture rather than just move it.
    """
    lines = []
    line = []
    length = 0
    pos = 0
    for m in _TOKEN_RE.finditer(data):
        if m.start() != pos:            # anything unrecognised travels
            line.append(data[pos:m.start()])   # with the token before it
            length += m.start() - pos
        token = m.group(0)
        if length + len(token) > width and line:
            lines.append(''.join(line))
            line, length = [], 0
        line.append(token)
        length += len(token)
        pos = m.end()
    if pos < len(data):
        line.append(data[pos:])
    if line:
        lines.append(''.join(line))
    return '\n'.join(lines) + '\n'
