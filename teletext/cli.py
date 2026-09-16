"""Command line interface for the teletext page composer."""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import textwrap
import time

from . import decdld, font, imageconv, page as P, render, sixel

__version__ = '0.1'


# ---------------------------------------------------------------------
# output plumbing
# ---------------------------------------------------------------------

def _open_output(args):
    """Return (write(str) -> None, close())."""
    if args.device:
        if args.baud:
            try:
                subprocess.check_call(['stty', '-F', args.device,
                                       str(args.baud), 'raw', '-echo'])
            except (OSError, subprocess.CalledProcessError) as exc:
                sys.stderr.write('warning: could not set line speed: %s\n' % exc)
        fh = open(args.device, 'wb', buffering=0)
        chunk = args.chunk or 256
        delay = (args.throttle or 0) / 1000.0

        def write(text):
            data = text.encode('latin-1', 'replace')
            for i in range(0, len(data), chunk):
                fh.write(data[i:i + chunk])
                if delay:
                    time.sleep(delay)
        return write, fh.close
    if args.output and args.output != '-':
        fh = open(args.output, 'w', encoding='latin-1', newline='')
        return fh.write, fh.close
    out = sys.stdout

    def write(text):
        out.write(text)
        out.flush()
    return write, lambda: None


# --depth names, in registers.  'low' is what a VT340 has; 'high' is what
# a modern terminal will give you if its numColorRegisters allows.
DEPTHS = {'low': 16, 'medium': 64, 'high': 256}


def _depth_limit(args):
    """The register count asked for by --depth, or None for auto."""
    depth = getattr(args, 'depth', None)
    if not depth or depth == 'auto':
        return None
    if depth in DEPTHS:
        return DEPTHS[depth]
    try:
        return max(2, int(depth))
    except ValueError:
        raise ValueError('--depth wants auto, %s or a number, not %r'
                         % ('/'.join(sorted(DEPTHS)), depth))


def _colour_limit(args):
    """How many colour registers we may use.

    --colour-registers wins, then --depth, then whatever the terminal
    said when asked, then the profile for the named terminal.  Writing
    past a terminal's real register count corrupts the picture instead
    of failing, so the automatic path is never optimistic.
    """
    explicit = getattr(args, 'colour_registers', None)
    if explicit:
        return explicit
    asked = _depth_limit(args)
    if asked:
        return asked
    probed = getattr(args, '_probed_registers', None)
    if probed:
        return probed
    return sixel.TERMINALS.get(args.terminal, {}).get('colours', 16)


def _photo_colours(args):
    """Registers left for a composited photograph, after the eight
    teletext colours."""
    return max(0, min(64, _colour_limit(args) - 8))


# A character cell is about this tall when the terminal will not say.
# Only used to guess how many rows an image occupies.
ASSUMED_CELL_PX = 20

DEFAULT_SCALE = 1.5


def _scale(args):
    scale = args.scale or DEFAULT_SCALE
    if args.sx or args.sy:
        return (args.sx or scale, args.sy or scale)
    return (scale, scale)


# Scales to try when fitting a page to the window, largest first.  A page
# is 225 pixels tall per unit of scale, so these are fine steps rather
# than doublings: the difference between fitting a window and not is
# often a quarter.
SCALE_LADDER = (2.0, 1.75, 1.5, 1.25, 1.0)


def _fit_scale(args):
    """The largest scale at which a whole page fits the window.

    A page at scale 2 is 450 pixels tall: 23 rows on a VT340's 20-pixel
    cell, which is what its 800x480 screen holds, but 33 rows on a
    14-pixel one, where the top would scroll away.  Never larger than
    DEFAULT_SCALE - this fits downwards, it does not magnify.
    """
    cell = getattr(args, '_cell_px', None)
    cell_h = cell[1] if cell else ASSUMED_CELL_PX
    rows = shutil.get_terminal_size((80, 24)).lines
    for scale in SCALE_LADDER:
        if scale > DEFAULT_SCALE:
            continue
        need = -(-P.ROWS * render.cell_size(scale)[1] // cell_h) + 1
        if need <= rows:
            return scale
    return SCALE_LADDER[-1]


def _render_page(pg, args, flash_on=True):
    bm = render.render(pg, scale=_scale(args), flash_on=flash_on,
                       reveal=args.reveal,
                       rounding=not getattr(args, 'no_rounding', False))
    if args.mono:
        bm = bm.to_mono(ink=P.COLOUR_NAMES.index(args.ink))
    elif pg.meta.get('image') and not getattr(args, 'no_images', False):
        bm = _composite_meta_image(bm, pg, args)
    return bm


def _composite_meta_image(bm, pg, args):
    """Blit a photo declared with !meta image into the rendered page."""
    path = pg.meta['image']
    if not os.path.isabs(path):
        path = os.path.join(pg.meta.get('_dir', '.'), path)
    try:
        img = imageconv.load(path)
    except (ValueError, OSError) as exc:
        sys.stderr.write('image: %s\n' % exc)
        return bm
    cw, ch = render.cell_size(_scale(args))
    box = pg.meta.get('imagebox', '13,1,10,38')
    try:
        row, col, rows, cols = [int(v) for v in box.split(',')]
    except ValueError:
        sys.stderr.write('image: bad imagebox %r\n' % box)
        return bm
    spare = _colour_limit(args) - 8
    if spare < 2:
        return bm
    want = getattr(args, 'photo_colours', None)
    if not want:
        # a VT340 can spare 8 registers; a modern terminal has plenty
        want = _photo_colours(args)
    # the box lies on the same whole-pixel cells the text was drawn in
    return imageconv.composite(
        bm, img, (col * cw, row * ch, cols * cw, rows * ch),
        ncolours=min(spare, want))


def _sixel_string(bm, args, first=True):
    """A whole page as one sixel image."""
    limit = _colour_limit(args)
    if limit and len(bm.colours_used()) > limit:
        sys.stderr.write('note: reducing %d colours to the %d registers '
                         'available\n' % (len(bm.colours_used()), limit))
        bm = bm.reduce(limit)
    ok, why = sixel.fits(bm, args.terminal)
    if not ok and not args.force:
        sys.stderr.write('warning: %s (use --scale 1 or --force)\n' % why)
    return sixel.sequence(bm, terminal=args.terminal,
                          clear=args.clear and first,
                          home=args.home or args.clear,
                          transparent=args.transparent,
                          aspect=(args.pan, args.pad),
                          max_colours=limit)


def _emit(bm, args, write, first=True):
    if getattr(args, 'png', None):
        imageconv.write_png(bm, args.png)
        sys.stderr.write('wrote %s\n' % args.png)
        return
    write(_sixel_string(bm, args, first=first))


def _cell(args):
    spec = getattr(args, 'cell', None) or '10x20'
    try:
        w, h = (int(v) for v in spec.lower().split('x'))
    except ValueError:
        raise ValueError('--cell wants WxH, like 10x20, not %r' % spec)
    return w, h


def _page_string(pg, args, flash_on=True, first=True):
    """One page of output: the whole page as a single sixel image, or as
    characters when the terminal is holding the soft font."""
    if getattr(args, 'emit', 'sixel') == 'text':
        if pg.meta.get('image') and not getattr(args, 'no_images', False):
            sys.stderr.write('note: %s has a photograph, which text mode '
                             'cannot show\n' % (pg.number or 'page'))
        return decdld.page_text(pg, rows=args.text_rows,
                                designate=first, home=True)
    bm = _render_page(pg, args, flash_on=flash_on)
    if getattr(args, 'png', None):
        imageconv.write_png(bm, args.png)
        sys.stderr.write('wrote %s\n' % args.png)
        return ''
    return _sixel_string(bm, args, first=first)


def _emit_page(pg, args, write, first=True, flash_on=True):
    write(_page_string(pg, args, flash_on=flash_on, first=first))


# ---------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------

def cmd_render(args):
    write, close = _open_output(args)
    try:
        pages = []
        for path in _expand_files(args.files):
            pg = P.load(path)
            pg.meta['_dir'] = os.path.dirname(os.path.abspath(path))
            pages.append(pg)
        rounds = 0
        while True:
            for i, pg in enumerate(pages):
                _emit_page(pg, args, write,
                           first=(rounds == 0 and i == 0),
                           flash_on=not args.flash_off)
                if len(pages) > 1 or args.loop:
                    if args.delay:
                        time.sleep(args.delay)
            rounds += 1
            if not args.loop:
                break
            if args.repeat and rounds >= args.repeat:
                break
    finally:
        close()
    return 0


def _expand_files(paths):
    """Expand any directory argument into the pages inside it, in page
    number order, so 'ttx view pages/feeds' does what it looks like."""
    out = []
    for path in paths:
        if os.path.isdir(path):
            found = sorted(glob.glob(os.path.join(path, '*.ttx'))
                           + glob.glob(os.path.join(path, '*.tti')))
            if not found:
                sys.stderr.write('%s: no .ttx or .tti pages\n' % path)
            out.extend(found)
        else:
            out.append(path)
    return out


def _getkey(timeout=None):
    """One keypress from the terminal, or None if timeout expires."""
    import select as _select
    try:
        import termios
        import tty
    except ImportError:
        return sys.stdin.read(1) or 'q'
    if not sys.stdin.isatty():
        return sys.stdin.read(1) or 'q'
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ready, _, _ = _select.select([fd], [], [], timeout)
        if not ready:
            return None
        return os.read(fd, 8).decode('latin-1', 'replace')
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def cmd_view(args):
    """Show pages in this terminal, one keypress at a time."""
    files = _expand_files(args.files)
    if not files:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = sorted(glob.glob(os.path.join(here, 'pages', '*.ttx')))
        demo = _demo_page()
        if demo and demo not in files:
            files.insert(0, demo)
    if not files:
        sys.stderr.write('no pages to show\n')
        return 1

    if not sys.stdout.isatty():
        # not a terminal: just emit every page, like render does
        write, close = sys.stdout.write, lambda: None
        try:
            for n, path in enumerate(files):
                pg = P.load(path)
                pg.meta['_dir'] = os.path.dirname(os.path.abspath(path))
                _emit_page(pg, args, write, first=(n == 0))
        finally:
            close()
        return 0

    if not args.no_probe:
        able = sixel.detect()
        if able is False:
            sys.stderr.write('ttx: ' + sixel.ADVICE)
            sys.stderr.write('showing anyway; press q to stop\n')
            time.sleep(2)
        regs = sixel.colour_registers()
        if regs:
            args._probed_registers = min(regs, 256)
            sys.stderr.write('terminal reports %d colour registers\n' % regs)
        elif not args.colour_registers and args.depth == 'auto':
            # unknown: a VT340's 16 registers is the safe assumption,
            # because overrunning the real count corrupts the picture
            args._probed_registers = 16
            sys.stderr.write(
                'terminal did not report its colour register count; using 16.'
                '\nPress d for more depth, or start with --depth high.\n')
            time.sleep(2)
        # the cell size turns an image's pixel height into terminal rows,
        # which is what decides how much story text fits underneath it
        args._cell_px = sixel.cell_size()
        if args.scale is None:
            args.scale = _fit_scale(args)
            cell = getattr(args, '_cell_px', None)
            rows = shutil.get_terminal_size((80, 24)).lines
            sys.stderr.write(
                'window %d rows, cell %s: showing pages at scale %d\n'
                % (rows, '%dx%dpx' % cell if cell else 'unknown',
                   args.scale))
        size = sixel.graphics_size()
        if size:
            cw, ch = render.cell_size(_scale(args))
            bm_w, bm_h = P.COLS * cw, P.ROWS * ch
            if bm_w > size[0] or bm_h > size[1]:
                sys.stderr.write(
                    'note: %dx%d is larger than this terminal\'s %dx%d '
                    'graphics area; try --scale 1\n'
                    % (bm_w, bm_h, size[0], size[1]))
                time.sleep(2)

    pages = []
    for path in files:
        pg = P.load(path)
        pg.meta['_dir'] = os.path.dirname(os.path.abspath(path))
        pages.append((path, pg))

    i = 0
    flash_on = True
    try:
        sys.stdout.write('\x1b[?25l')            # hide the cursor
        while True:
            path, pg = pages[i]
            cols, lines = shutil.get_terminal_size((80, 24))
            out = ['\x1b[2J\x1b[H',
                   _page_string(pg, args, flash_on=flash_on)]
            status = (' %d/%d  %s   %d regs/%d photo   space next, p prev, '
                      'd depth, r reveal, f flash, q quit '
                      % (i + 1, len(pages), os.path.basename(path),
                         _colour_limit(args), _photo_colours(args)))
            out.append('\x1b[%d;1H\x1b[7m%-*.*s\x1b[0m'
                       % (lines, cols, cols, status))
            sys.stdout.write(''.join(out))
            sys.stdout.flush()

            key = _getkey(args.delay or None)
            if key is None:                       # timed out: auto-advance
                i = (i + 1) % len(pages)
                continue
            key = key[:1]
            if key in ('q', '\x1b', '\x03'):
                return 0
            if key in (' ', 'n', '\r', '\n', '\x0e'):
                i = (i + 1) % len(pages)
            elif key in ('p', 'b', '\x10'):
                i = (i - 1) % len(pages)
            elif key == 'd':
                order = ['auto', 'low', 'medium', 'high']
                cur = args.depth if args.depth in order else 'auto'
                args.depth = order[(order.index(cur) + 1) % len(order)]
                args.colour_registers = None
            elif key == 'r':
                args.reveal = not args.reveal
            elif key == 'f':
                flash_on = not flash_on
    except KeyboardInterrupt:
        return 130
    finally:
        sys.stdout.write('\x1b[?25h\x1b[%d;1H\n' %
                         shutil.get_terminal_size((80, 24)).lines)
        sys.stdout.flush()


def cmd_preview(args):
    pg = P.load(args.file)
    if args.pixels:
        bm = _render_page(pg, args)
        sys.stdout.write(_halfblock(bm))
    else:
        sys.stdout.write(render.ansi_preview(pg, reveal=args.reveal) + '\n')
    return 0


def _halfblock(bm):
    """Preview a bitmap with Unicode half blocks and 24-bit colour."""
    out = []
    pal = bm.palette
    for y in range(0, bm.height, 2):
        line = []
        for x in range(bm.width):
            top = pal[bm.pix[y * bm.width + x]]
            if y + 1 < bm.height:
                bot = pal[bm.pix[(y + 1) * bm.width + x]]
            else:
                bot = (0, 0, 0)
            line.append('\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm▀'
                        % (top + bot))
        out.append(''.join(line) + '\x1b[0m')
    return '\n'.join(out) + '\n'


def cmd_text(args):
    pg = P.load(args.file)
    sys.stdout.write(pg.to_text() + '\n')
    return 0


def cmd_new(args):
    pg = P.Page(number=args.number, title=args.title or 'NEW PAGE')
    pg.write(0, 0, '{blue}%s{white} TELETEXT' % args.number)
    pg.write(2, 0, '{yellow}{double}%s' % (args.title or 'NEW PAGE'))
    pg.write(24, 0, '{red}Red{white} {green}Green{white} '
                    '{yellow}Yellow{white} {cyan}Cyan')
    if args.file == '-':
        sys.stdout.write(P.serialize(pg))
    else:
        if os.path.exists(args.file) and not args.force:
            sys.stderr.write('%s exists (use --force)\n' % args.file)
            return 1
        P.save(pg, args.file)
        sys.stderr.write('wrote %s\n' % args.file)
    return 0


def cmd_edit(args):
    from . import editor
    return editor.run(args.file, charset=args.charset)


def cmd_image(args):
    img = imageconv.load(args.file)
    if args.as_ == 'sixel':
        target_w = args.width or min(img.width, 640)
        scale = target_w / float(img.width)
        img = img.resize(target_w, max(1, int(img.height * scale)), fit=False)
        bm = imageconv.quantize(img, args.colours)
        write, close = _open_output(args)
        try:
            _emit(bm, args, write)
        finally:
            close()
        return 0

    pg = P.Page()
    top = args.top
    rows = args.rows if args.rows else P.ROWS - top
    if args.fit_rows and args.mode == 'colour':
        rows = imageconv.rows_for(img, P.COLS - 2, rows)
        top = max(top, (P.ROWS - 1 - rows) if args.top == 0 else top)
    imageconv.to_page(img, rows=rows, top=top, mode=args.mode,
                      colour=args.ink, fit=not args.stretch,
                      dither=not args.no_dither, sep=args.separated,
                      brightness=args.brightness, contrast=args.contrast,
                      dither_strength=args.dither_strength,
                      equalise_amount=args.equalise,
                      hold=not args.no_hold, target=pg)
    if args.caption:
        pg.write(0, 0, args.caption)
    if args.output and args.output != '-':
        P.save(pg, args.output)
        sys.stderr.write('wrote %s\n' % args.output)
    else:
        sys.stdout.write(P.serialize(pg))
    return 0


def cmd_chars(args):
    """Render a character-set / mosaic reference page."""
    pg = P.Page(charset=args.charset)
    pg.write(0, 0, '{blue}CHARSET{white} %s' % args.charset.upper())
    row = 2
    for base in range(0x20, 0x80, 0x10):
        pg.put(row, 0, P.ALPHA_CYAN)
        pg.write(row, 1, '%02X' % base)
        pg.put(row, 4, P.ALPHA_WHITE)
        for i in range(16):
            pg.put(row, 5 + i * 2, base + i)
        row += 1
    row += 1
    pg.write(row, 0, '{yellow}Contiguous mosaics')
    row += 1
    for block in range(4):
        pg.put(row, 0, P.GRAPHICS_WHITE)
        for i in range(16):
            pg.put(row, 1 + i * 2, P.mosaic_code(block * 16 + i))
        pg.put(row, 34, P.GRAPHICS_CYAN)
        pg.put(row, 35, P.SEPARATED)
        for i in range(4):
            pg.put(row, 36 + i, P.mosaic_code(block * 16 + i))
        row += 1
    args_out = args
    bm = _render_page(pg, args_out)
    if args.ttx:
        sys.stdout.write(P.serialize(pg))
        return 0
    write, close = _open_output(args)
    try:
        _emit(bm, args, write)
    finally:
        close()
    return 0


def _demo_page():
    """The bundled demo page.  It sits inside the package: pages/ is
    where built feed pages go, and those builds were wiping it."""
    here = os.path.dirname(os.path.abspath(__file__))
    packaged = os.path.join(here, 'demo.ttx')
    if os.path.exists(packaged):
        return packaged
    loose = os.path.join(os.path.dirname(here), 'pages', 'demo.ttx')
    return loose if os.path.exists(loose) else None


def cmd_demo(args):
    path = _demo_page()
    if not path:
        sys.stderr.write('ttx: the bundled demo page is missing\n')
        return 1
    args.files = [path]
    return cmd_render(args)


INDEX_ROWS = (5, 21)          # the rows an index page lists into


def _index_pages(entries, start, taken, charset='english'):
    """Directory pages listing every page published.

    A set of pages is no use to someone at a terminal typing numbers
    unless something tells them which numbers exist, and a service's
    own front page only lists its services.  Long lists continue onto
    further pages, each pointing at the next.
    """
    first_row, last_row = INDEX_ROWS
    per_page = last_row - first_row + 1
    chunks = [entries[i:i + per_page]
              for i in range(0, len(entries), per_page)] or [[]]

    numbers = []
    n = start
    for _ in chunks:
        while str(n) in taken:
            n += 1
        numbers.append(n)
        taken.add(str(n))
        n += 1

    pages = []
    for i, chunk in enumerate(chunks):
        pg = P.Page(charset=charset, number=str(numbers[i]),
                    title='PAGE INDEX')
        pg.write(0, 0, '{cyan}P%d {white}PAGE INDEX' % numbers[i])
        pg.put(1, 0, P.GRAPHICS_RED)
        for c in range(1, P.COLS):
            pg.put(1, c, P.mosaic_code(0x0C))
        pg.write(2, 0, '{yellow}{double}PAGE INDEX')
        row = first_row
        for number, title in chunk:
            pg.write(row, 0, '{cyan}%-4s {white}%s' % (number, title[:33]))
            row += 1
        bits = []
        if len(chunks) > 1:
            nxt = numbers[(i + 1) % len(numbers)]
            bits.append('{yellow}%d More' % nxt)
            pg.write(23, 0, '{green}Index %d of %d' % (i + 1, len(chunks)))
        bits.append('{cyan}Type a page number')
        pg.write(24, 0, ' '.join(bits)[:60])
        pages.append((numbers[i], pg))
    return pages


def cmd_publish(args):
    """Write pages as P<number>.DAT files a PDP-11 can fetch and TYPE.

    One sixel page is a single line of several thousand characters,
    which a record-oriented filesystem like RSX's cannot hold, so the
    data is wrapped at points where a break cannot change the picture.
    """
    files = _expand_files(args.files)
    if not files:
        sys.stderr.write('nothing to publish\n')
        return 1
    try:
        os.makedirs(args.out, exist_ok=True)
    except OSError as exc:
        sys.stderr.write('ttx: %s\n' % exc)
        return 1

    def emit(number, pg):
        data = _page_string(pg, args, first=True)
        if not data:
            return None
        out = os.path.join(args.out, '%s%s.DAT' % (args.prefix, number))
        with open(out, 'w', encoding='latin-1', newline='\n') as fh:
            fh.write(sixel.wrap(data, args.record) if args.wrap else data)
        return out

    written = []
    entries = []
    for path in files:
        pg = P.load(path)
        pg.meta['_dir'] = os.path.dirname(os.path.abspath(path))
        number = str(pg.number or os.path.splitext(os.path.basename(path))[0])
        number = ''.join(c for c in number if c.isdigit()) or '100'
        out = emit(number, pg)
        if out is None:
            continue
        entries.append((number, pg.title or os.path.basename(path)))
        written.append((number, out, os.path.getsize(out)))

    if args.index and entries:
        taken = set(n for n, _, _ in written)
        entries.sort(key=lambda e: (len(e[0]), e[0]))
        for number, pg in _index_pages(entries, args.index, taken):
            out = emit(str(number), pg)
            if out:
                written.append((str(number), out, os.path.getsize(out)))

    # a page for numbers that do not exist, which the viewer falls back to
    if args.not_found:
        pg = P.Page(number='000', title='PAGE NOT FOUND')
        pg.write(0, 0, '{cyan}P%s {white}TELETEXT' % '---')
        pg.write(2, 0, '{red}{double}PAGE NOT FOUND')
        pg.write(5, 0, '{white}That page is not held.')
        pg.write(7, 0, '{yellow}100 {white}is the index.')
        data = _page_string(pg, args, first=True)
        out = os.path.join(args.out, '%sNF.DAT' % args.prefix)
        with open(out, 'w', encoding='latin-1', newline='\n') as fh:
            fh.write(sixel.wrap(data, args.record) if args.wrap else data)
        written.append(('NF', out, os.path.getsize(out)))

    total = sum(n for _, _, n in written)
    for number, out, size in written:
        sys.stderr.write('%-5s %-40s %6d bytes  %5.1fs @9600\n'
                         % (number, out, size, size / 960.0))
    sys.stderr.write('%d pages, %d bytes\n' % (len(written), total))
    for _, out, _ in written:
        print(out)
    return 0


def cmd_softfont(args):
    """Send the teletext shapes to the terminal as a soft character set."""
    cell = _cell(args)
    data = decdld.font_download(cell=cell, charset=args.charset)
    write, close = _open_output(args)
    try:
        write(data)
    finally:
        close()
    sys.stderr.write('%d bytes: %.1fs at 9600 baud, once per session\n'
                     % (len(data), len(data) / 960.0))
    return 0


def cmd_selftest(args):
    import unittest
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(here, 'tests'), top_level_dir=here)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def cmd_feeds(args):
    from .feeds import cli as feedcli
    return feedcli.main(args.rest)


# ---------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------

def _add_output_opts(sp):
    sp.add_argument('-o', '--output', help='write to a file instead of stdout')
    sp.add_argument('--device', help='write to a serial device, e.g. /dev/ttyS0')
    sp.add_argument('--baud', type=int, help='set line speed on --device')
    sp.add_argument('--chunk', type=int, default=256,
                    help='bytes per write when throttling (default 256)')
    sp.add_argument('--throttle', type=float, default=0,
                    help='milliseconds to pause between chunks')


def _add_render_opts(sp):
    sp.add_argument('--scale', type=float, default=None,
                    help='character cell size: 1 is 6x9, 1.5 is 9x14 (default), 2 is 12x18')
    sp.add_argument('--sx', type=int, help='horizontal scale override')
    sp.add_argument('--sy', type=int, help='vertical scale override')
    sp.add_argument('--terminal', default='vt340',
                    choices=sorted(sixel.TERMINALS),
                    help='target terminal (limits colour registers)')
    sp.add_argument('--mono', action='store_true',
                    help='collapse to one ink colour (VT125/VT240)')
    sp.add_argument('--ink', default='white', choices=P.COLOUR_NAMES,
                    help='ink colour for --mono')
    sp.add_argument('--transparent', action='store_true',
                    help='do not paint the background (P2=1)')
    sp.add_argument('--clear', action='store_true',
                    help='clear the screen before the first image')
    sp.add_argument('--home', action='store_true', help='home the cursor first')
    sp.add_argument('--reveal', action='store_true', help='reveal concealed text')
    sp.add_argument('--flash-off', action='store_true',
                    help='render flashing text as blank')
    sp.add_argument('--pan', type=int, default=1, help='aspect ratio numerator')
    sp.add_argument('--pad', type=int, default=1, help='aspect ratio denominator')
    sp.add_argument('--force', action='store_true',
                    help='emit even if it will not fit the terminal raster')
    sp.add_argument('--emit', default='sixel', choices=['sixel', 'text'],
                    help='sixel draws the page as graphics; text sends it '
                         'as characters for a terminal holding the soft '
                         'font (see the softfont command)')
    sp.add_argument('--text-rows', type=int, default=24,
                    help='lines the terminal has, for --mode text '
                         '(a VT340 shows 24 of the 25 teletext rows)')
    sp.add_argument('--cell', default='10x20',
                    help='the terminal character cell, for the soft font')
    sp.add_argument('--no-rounding', action='store_true',
                    help='switch off the character rounding a real '
                         'teletext chip applies to diagonals')
    sp.add_argument('--png', help='write a PNG instead of sixel (for testing)')
    sp.add_argument('--no-images', action='store_true',
                    help='ignore !meta image photos')
    sp.add_argument('--depth', default='auto',
                    help='picture depth: auto, low (16 registers, a VT340), '
                         'medium (64), high (256) or a number')
    sp.add_argument('--colour-registers', type=int,
                    help='colour registers the terminal really has '
                         '(xterm defaults to 16 unless numColorRegisters '
                         'says otherwise)')
    sp.add_argument('--photo-colours', type=int,
                    help='colour registers a composited photo may use '
                         '(default: all the terminal can spare, up to 64)')


def _add_loop_opts(sp):
    sp.add_argument('--loop', action='store_true', help='cycle forever')
    sp.add_argument('--repeat', type=int, help='stop after N passes')
    sp.add_argument('--delay', type=float, default=0,
                    help='seconds between pages')


def build_parser():
    ap = argparse.ArgumentParser(
        prog='ttx',
        description='Compose teletext pages and emit them as sixel graphics.')
    ap.add_argument('--version', action='version', version='ttx ' + __version__)
    sub = ap.add_subparsers(dest='cmd')

    sp = sub.add_parser('render', help='render pages to sixel')
    sp.add_argument('files', nargs='+')
    _add_loop_opts(sp)
    _add_render_opts(sp)
    _add_output_opts(sp)
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser('view',
                        help='show pages in this terminal, a keypress apart')
    sp.add_argument('files', nargs='*',
                    help='pages to show (default: the bundled ones)')
    sp.add_argument('--delay', type=float, default=0,
                    help='auto-advance after N seconds')
    sp.add_argument('--no-probe', action='store_true',
                    help='skip the sixel capability check')
    _add_render_opts(sp)
    sp.set_defaults(func=cmd_view, terminal='xterm')

    sp = sub.add_parser('preview', help='preview in the local terminal')
    sp.add_argument('file')
    sp.add_argument('--pixels', action='store_true',
                    help='24-bit half-block preview instead of sextants')
    _add_render_opts(sp)
    sp.set_defaults(func=cmd_preview)

    sp = sub.add_parser('text', help='dump a page as plain text')
    sp.add_argument('file')
    sp.set_defaults(func=cmd_text)

    sp = sub.add_parser('new', help='create a skeleton page')
    sp.add_argument('file')
    sp.add_argument('--number', default='100')
    sp.add_argument('--title')
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser('edit', help='interactive page editor')
    sp.add_argument('file')
    sp.add_argument('--charset', default='english', choices=['english', 'ascii'])
    sp.set_defaults(func=cmd_edit)

    sp = sub.add_parser('image', help='convert an image to a page or to sixel')
    sp.add_argument('file')
    sp.add_argument('--as', dest='as_', default='page',
                    choices=['page', 'sixel'])
    sp.add_argument('--mode', default='colour', choices=['colour', 'mono'])
    sp.add_argument('--rows', type=int, help='mosaic rows to fill')
    sp.add_argument('--top', type=int, default=0, help='first row to use')
    sp.add_argument('--stretch', action='store_true',
                    help='ignore the aspect ratio')
    sp.add_argument('--no-dither', action='store_true')
    sp.add_argument('--dither-strength', type=float, default=0.35,
                    help='fraction of the error diffused (0-1, default 0.35)')
    sp.add_argument('--equalise', type=float, default=0.8,
                    help='histogram equalisation, 0 to switch it off')
    sp.add_argument('--no-hold', action='store_true',
                    help='do not use hold mosaics over colour changes')
    sp.add_argument('--fit-rows', action='store_true',
                    help='shrink the row count to the image aspect ratio')
    sp.add_argument('--separated', action='store_true',
                    help='use separated mosaics')
    sp.add_argument('--brightness', type=float, default=1.0)
    sp.add_argument('--contrast', type=float, default=1.0)
    sp.add_argument('--caption', help='markup written into row 0')
    sp.add_argument('--colours', type=int, default=16,
                    help='palette size for --as sixel')
    sp.add_argument('--width', type=int, help='pixel width for --as sixel')
    _add_render_opts(sp)
    _add_output_opts(sp)
    sp.set_defaults(func=cmd_image)

    sp = sub.add_parser('chars', help='render a character set reference page')
    sp.add_argument('--charset', default='english', choices=['english', 'ascii'])
    sp.add_argument('--ttx', action='store_true', help='emit .ttx source')
    _add_render_opts(sp)
    _add_output_opts(sp)
    sp.set_defaults(func=cmd_chars)

    sp = sub.add_parser('demo', help='render the bundled demo page')
    _add_loop_opts(sp)
    _add_render_opts(sp)
    _add_output_opts(sp)
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser('feeds', help='fetch news feeds and build pages')
    sp.add_argument('rest', nargs=argparse.REMAINDER)
    sp.set_defaults(func=cmd_feeds)

    sp = sub.add_parser('publish',
                        help='write pages as .DAT files for a PDP-11 to '
                             'fetch and TYPE')
    sp.add_argument('files', nargs='+')
    sp.add_argument('--out', default='publish',
                    help='directory to write into (an FTP directory, say)')
    sp.add_argument('--prefix', default='P',
                    help='filename prefix, P by default: P101.DAT')
    sp.add_argument('--no-wrap', dest='wrap', action='store_false',
                    default=True,
                    help='leave the sixel as one long line')
    sp.add_argument('--record', type=int, default=480,
                    help='longest record to write (default 480)')
    sp.add_argument('--no-not-found', dest='not_found', action='store_false',
                    default=True, help='do not write PNF.DAT')
    sp.add_argument('--index', type=int, default=199, metavar='N',
                    help='page number for the generated directory of every '
                         'page published (default 199; it moves up if that '
                         'number is taken, and continues onto further pages '
                         'when the list is long)')
    sp.add_argument('--no-index', dest='index', action='store_const',
                    const=0, help='do not generate a directory page')
    _add_render_opts(sp)
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser('softfont',
                        help='download the teletext font to the terminal')
    sp.add_argument('--cell', default='10x20',
                    help='character cell in pixels (a VT340 holds 10x20)')
    sp.add_argument('--charset', default='english', choices=['english', 'ascii'])
    _add_output_opts(sp)
    sp.set_defaults(func=cmd_softfont)

    sp = sub.add_parser('selftest', help='run the unit tests')
    sp.set_defaults(func=cmd_selftest)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, 'cmd', None):
        ap.print_help()
        return 1
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as exc:
        sys.stderr.write('ttx: %s\n' % exc)
        return 1
