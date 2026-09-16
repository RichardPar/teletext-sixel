"""Curses page editor.

Layout is the real 40x25 teletext grid.  Attribute cells are shown as a
reverse-video letter so you can see where they are; on a real receiver
they display as spaces.
"""

import curses
import os
import sys

from . import font, page as P, render, sixel

# ESC-prefixed attribute keys.
ESC_KEYS = {
    'k': P.ALPHA_BLACK, 'r': P.ALPHA_RED, 'g': P.ALPHA_GREEN,
    'y': P.ALPHA_YELLOW, 'b': P.ALPHA_BLUE, 'm': P.ALPHA_MAGENTA,
    'c': P.ALPHA_CYAN, 'w': P.ALPHA_WHITE,
    'K': P.GRAPHICS_BLACK, 'R': P.GRAPHICS_RED, 'G': P.GRAPHICS_GREEN,
    'Y': P.GRAPHICS_YELLOW, 'B': P.GRAPHICS_BLUE, 'M': P.GRAPHICS_MAGENTA,
    'C': P.GRAPHICS_CYAN, 'W': P.GRAPHICS_WHITE,
    'd': P.DOUBLE_HEIGHT, 'n': P.NORMAL_HEIGHT,
    'f': P.FLASH, 's': P.STEADY,
    'p': P.SEPARATED, 'o': P.CONTIGUOUS,
    'h': P.HOLD_MOSAICS, 'e': P.RELEASE_MOSAICS,
    'v': P.CONCEAL, 'z': P.BLACK_BACKGROUND, 'x': P.NEW_BACKGROUND,
}

# Keys that toggle the six mosaic blocks in pixel mode.
PIXEL_KEYS = {'q': 0, 'w': 1, 'a': 2, 's': 3, 'z': 4, 'x': 5}

CONTROL_LABEL = {
    P.ALPHA_BLACK: 'k', P.ALPHA_RED: 'r', P.ALPHA_GREEN: 'g',
    P.ALPHA_YELLOW: 'y', P.ALPHA_BLUE: 'b', P.ALPHA_MAGENTA: 'm',
    P.ALPHA_CYAN: 'c', P.ALPHA_WHITE: 'w',
    P.GRAPHICS_BLACK: 'K', P.GRAPHICS_RED: 'R', P.GRAPHICS_GREEN: 'G',
    P.GRAPHICS_YELLOW: 'Y', P.GRAPHICS_BLUE: 'B', P.GRAPHICS_MAGENTA: 'M',
    P.GRAPHICS_CYAN: 'C', P.GRAPHICS_WHITE: 'W',
    P.FLASH: 'F', P.STEADY: 'S', P.NORMAL_HEIGHT: 'N', P.DOUBLE_HEIGHT: 'D',
    P.CONCEAL: 'V', P.CONTIGUOUS: 'O', P.SEPARATED: 'P',
    P.BLACK_BACKGROUND: 'Z', P.NEW_BACKGROUND: 'X',
    P.HOLD_MOSAICS: 'H', P.RELEASE_MOSAICS: 'E',
    P.START_BOX: '[', P.END_BOX: ']',
}

HELP = [
    'Movement   arrows, Home/End, ^P/^N row, Tab',
    'Typing     printable keys overwrite; Backspace/Del blank a cell',
    'Attributes ESC then:  k r g y b m c w  = alpha colour',
    '                      K R G Y B M C W  = mosaic colour',
    '                      d/n double/normal   f/s flash/steady',
    '                      p/o separated/contiguous   h/e hold/release',
    '                      v conceal   z black bg   x new bg',
    'Pixel mode F5 toggles; then Q W / A S / Z X set mosaic blocks',
    '           space clears the cell, F6 fills it',
    'Rows       ^Y delete row, ^U insert blank row, ^D duplicate row',
    'Files      F2 save   F3 sixel preview   F4 plain-text dump',
    'Quit       F10 or ^X          Help  F1',
]


def run(path, charset='english'):
    if os.path.exists(path):
        pg = P.load(path)
    else:
        pg = P.Page(charset=charset)
        pg.title = os.path.splitext(os.path.basename(path))[0].upper()
    state = {'page': pg, 'path': path, 'row': 0, 'col': 0,
             'pixel': False, 'dirty': False, 'msg': 'F1 for help'}
    try:
        curses.wrapper(_loop, state)
    except curses.error as exc:
        sys.stderr.write('editor: %s\n' % exc)
        return 1
    return 0


def _init_colours():
    curses.start_color()
    curses.use_default_colors()
    # teletext colour order matches curses COLOR_* only by coincidence for
    # some entries, so map explicitly
    order = [curses.COLOR_BLACK, curses.COLOR_RED, curses.COLOR_GREEN,
             curses.COLOR_YELLOW, curses.COLOR_BLUE, curses.COLOR_MAGENTA,
             curses.COLOR_CYAN, curses.COLOR_WHITE]
    for fg in range(8):
        for bg in range(8):
            pair = fg * 8 + bg + 1
            try:
                curses.init_pair(pair, order[fg], order[bg])
            except curses.error:
                pass
    return order


def _pair(fg, bg):
    return curses.color_pair(fg * 8 + bg + 1)


def _loop(stdscr, state):
    _init_colours()
    curses.curs_set(1)
    stdscr.keypad(True)
    while True:
        _draw(stdscr, state)
        try:
            ch = stdscr.getch()
        except KeyboardInterrupt:
            ch = 24
        if not _handle(stdscr, state, ch):
            return


def _draw(stdscr, state):
    pg = state['page']
    stdscr.erase()
    maxy, maxx = stdscr.getmaxyx()
    width = min(P.COLS, maxx - 1)
    for r in range(min(P.ROWS, maxy - 3)):
        cells = render.row_cells(pg.rows[r])
        for c in range(width):
            code = pg.rows[r][c]
            cell = cells[c]
            attr = _pair(cell.fg, cell.bg)
            if code < 0x20:
                ch = CONTROL_LABEL.get(code, '?')
                attr = _pair(code & 7 if code < 8 or 0x10 <= code <= 0x17
                             else 7, 0) | curses.A_REVERSE
            elif font.is_mosaic(cell.code, cell.gfx):
                ch = render._sextant(P.unpack_mosaic(cell.code))
            else:
                ch = P._CODE_TO_UNI[pg.charset].get(cell.code, ' ')
            if cell.flash:
                attr |= curses.A_BLINK
            try:
                stdscr.addstr(r, c, ch, attr)
            except curses.error:
                pass
    code = pg.rows[state['row']][state['col']]
    status = (' %s%s  row %2d col %2d  code %02X  %s  %s' %
              (os.path.basename(state['path']),
               '*' if state['dirty'] else ' ',
               state['row'], state['col'], code,
               'PIXEL' if state['pixel'] else 'TEXT ',
               state['msg']))
    if maxy > P.ROWS:
        try:
            stdscr.addstr(min(P.ROWS, maxy - 2), 0, status[:maxx - 1],
                          curses.A_REVERSE)
        except curses.error:
            pass
    try:
        stdscr.move(state['row'], state['col'])
    except curses.error:
        pass
    stdscr.refresh()


def _handle(stdscr, state, ch):
    pg = state['page']
    row, col = state['row'], state['col']
    state['msg'] = ''

    if ch in (curses.KEY_F10, 24):          # F10 / ^X
        if state['dirty'] and not _confirm(stdscr, 'Save before quitting?'):
            return False
        if state['dirty']:
            _save(state)
        return False
    if ch == curses.KEY_F1:
        _help(stdscr)
        return True
    if ch == curses.KEY_F2:
        _save(state)
        return True
    if ch == curses.KEY_F3:
        _sixel_preview(stdscr, state)
        return True
    if ch == curses.KEY_F4:
        _text_preview(stdscr, state)
        return True
    if ch == curses.KEY_F5:
        state['pixel'] = not state['pixel']
        return True
    if ch == curses.KEY_F6:
        pg.put(row, col, P.mosaic_code(0x3F))
        state['dirty'] = True
        return True

    if ch == curses.KEY_LEFT:
        state['col'] = max(0, col - 1)
        return True
    if ch == curses.KEY_RIGHT:
        state['col'] = min(P.COLS - 1, col + 1)
        return True
    if ch == curses.KEY_UP:
        state['row'] = max(0, row - 1)
        return True
    if ch == curses.KEY_DOWN:
        state['row'] = min(P.ROWS - 1, row + 1)
        return True
    if ch == curses.KEY_HOME:
        state['col'] = 0
        return True
    if ch == curses.KEY_END:
        state['col'] = P.COLS - 1
        return True
    if ch == 9:                             # Tab
        state['col'] = min(P.COLS - 1, col + 8)
        return True
    if ch == 16:                            # ^P
        state['row'] = max(0, row - 1)
        return True
    if ch == 14:                            # ^N
        state['row'] = min(P.ROWS - 1, row + 1)
        return True
    if ch in (10, 13):
        state['row'] = min(P.ROWS - 1, row + 1)
        state['col'] = 0
        return True
    if ch in (curses.KEY_BACKSPACE, 127, 8):
        if col > 0:
            state['col'] = col - 1
            pg.put(row, state['col'], 0x20)
            state['dirty'] = True
        return True
    if ch == curses.KEY_DC:
        pg.put(row, col, 0x20)
        state['dirty'] = True
        return True
    if ch == 25:                            # ^Y delete row
        pg.rows.pop(row)
        pg.rows.append([0x20] * P.COLS)
        state['dirty'] = True
        return True
    if ch == 21:                            # ^U insert row
        pg.rows.insert(row, [0x20] * P.COLS)
        del pg.rows[P.ROWS:]
        state['dirty'] = True
        return True
    if ch == 4:                             # ^D duplicate row
        pg.rows.insert(row, list(pg.rows[row]))
        del pg.rows[P.ROWS:]
        state['dirty'] = True
        return True

    if ch == 27:                            # ESC prefix
        stdscr.timeout(400)
        nxt = stdscr.getch()
        stdscr.timeout(-1)
        if nxt == -1:
            state['msg'] = 'ESC cancelled'
            return True
        key = chr(nxt) if 0 < nxt < 256 else ''
        if key in ESC_KEYS:
            pg.put(row, col, ESC_KEYS[key])
            state['col'] = min(P.COLS - 1, col + 1)
            state['dirty'] = True
            state['msg'] = 'attribute %02X' % ESC_KEYS[key]
        else:
            state['msg'] = 'no attribute for ESC %r' % key
        return True

    if 32 <= ch < 127:
        key = chr(ch)
        if state['pixel']:
            if key in PIXEL_KEYS:
                code = pg.rows[row][col]
                v = P.unpack_mosaic(code) if code >= 0x20 else 0
                pg.put(row, col, P.mosaic_code(v ^ (1 << PIXEL_KEYS[key])))
                state['dirty'] = True
                return True
            if key == ' ':
                pg.put(row, col, P.mosaic_code(0))
                state['col'] = min(P.COLS - 1, col + 1)
                state['dirty'] = True
                return True
        codes = P.encode_line(key, pg.charset)
        if codes:
            pg.put(row, col, codes[0])
            state['col'] = min(P.COLS - 1, col + 1)
            state['dirty'] = True
        return True
    return True


def _save(state):
    path = state['path']
    pg = state['page']
    if path.lower().endswith('.tti'):
        with open(path, 'w', encoding='latin-1', newline='') as fh:
            fh.write(P.dump_tti(pg))
    else:
        P.save(pg, path)
    state['dirty'] = False
    state['msg'] = 'saved %s' % os.path.basename(path)


def _confirm(stdscr, question):
    maxy, maxx = stdscr.getmaxyx()
    stdscr.addstr(maxy - 1, 0, (question + ' [y/N] ')[:maxx - 1],
                  curses.A_REVERSE)
    stdscr.refresh()
    ch = stdscr.getch()
    return ch in (ord('y'), ord('Y'))


def _help(stdscr):
    stdscr.erase()
    stdscr.addstr(0, 0, 'ttx editor', curses.A_BOLD)
    for i, line in enumerate(HELP):
        try:
            stdscr.addstr(i + 2, 0, line)
        except curses.error:
            break
    stdscr.addstr(len(HELP) + 3, 0, 'press any key', curses.A_REVERSE)
    stdscr.refresh()
    stdscr.getch()


def _text_preview(stdscr, state):
    curses.endwin()
    sys.stdout.write('\x1b[2J\x1b[H')
    sys.stdout.write(render.ansi_preview(state['page']) + '\n')
    sys.stdout.write('press Enter to return ')
    sys.stdout.flush()
    sys.stdin.readline()
    stdscr.redrawwin()


def _sixel_preview(stdscr, state):
    curses.endwin()
    bm = render.render(state['page'], scale=2)
    sys.stdout.write('\x1b[2J\x1b[H')
    sys.stdout.write(sixel.encode(bm))
    sys.stdout.write('\npress Enter to return ')
    sys.stdout.flush()
    sys.stdin.readline()
    stdscr.redrawwin()
