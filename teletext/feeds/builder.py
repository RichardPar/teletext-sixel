"""Turn feed items into teletext pages."""

import os
import textwrap
import time

from .. import imageconv, page as P

BODY_WIDTH = 40
# Double height is twice as tall, not twice as wide: a headline still has
# all 40 columns, less the two cells holding {yellow}{double}.
HEAD_WIDTH = 38
INDEX_WIDTH = 34         # after '{cyan}NNN {white}'
INDEX_CONT = 36          # continuation line, indented by four
# A summary shorter than this is a teaser, not a story: when the linked
# page can be fetched, its article text becomes the body instead.
TEASER_CHARS = 240


# A page sent down a 9600 baud line is a minute old by the time it has
# finished painting, and every page in a carousel would show a different
# minute.  The date is what is worth knowing; --clock puts the time back.
CLOCK = False


def now_string(when=None, clock=None):
    fmt = '%a %d %b %H:%M' if (CLOCK if clock is None else clock) else '%a %d %b'
    return time.strftime(fmt, time.localtime(when))


def _escape(text):
    """Make feed text safe for the markup parser and the G0 set."""
    out = []
    for ch in text.replace('{', '(').replace('}', ')'):
        if ch in '‘’‛':
            ch = "'"
        elif ch in '“”':
            ch = '"'
        elif ch in '–—':
            ch = '-'
        elif ch == '…':
            ch = '...'
        elif ch == ' ':
            ch = ' '
        elif ord(ch) > 0x7F and ch not in '£½¼¾÷':
            ch = '?'
        out.append(ch)
    return ''.join(out)


def header(pg, number, title, when=None, colour='cyan', clock=None):
    """Row 0: page number, service name, clock.

    Three attribute cells are spent on colour, so only 37 of the 40
    columns are available for text.
    """
    left = 'P%s' % number
    stamp = now_string(when, clock)
    budget = P.COLS - 3
    mid = _escape(title)[:max(0, budget - len(left) - len(stamp) - 2)]
    pad = budget - len(left) - len(mid) - len(stamp) - 1
    text = '{%s}%s {white}%s%s{yellow}%s' % (
        colour, left, mid, ' ' * max(1, pad), stamp)
    pg.write(0, 0, text)


def rule(pg, row, colour='red'):
    pg.put(row, 0, P.TOKENS['g' + colour])
    for c in range(1, P.COLS):
        pg.put(row, c, P.mosaic_code(0x0C))     # middle band of blocks


def nav(pg, row=24, prev=None, nxt=None, index=None, main=None, extra=None):
    """The bottom bar, on the four FASTEXT colours.

    Every key names a page you can actually type: the service's own
    index rather than its name, and the front page as MAIN.
    """
    links = []
    if prev:
        links.append(('PREV', prev))
    if nxt:
        links.append(('NEXT', nxt))
    if index:
        links.append(('INDEX', index))
    if main:
        links.append(('MAIN', main))
    elif extra:
        links.append((_escape(str(extra)).upper(), ''))
    P.fastext_bar(pg, links, row)


def logo_art(text, charset='english'):
    """A word as mosaic pixel art, taken from the teletext font.

    Each character is nine rows tall, which is exactly three rows of
    mosaics, so a word drawn this way lines up with the character grid
    underneath it.
    """
    from .. import font
    rows = []
    for y in range(font.CELL_H):
        line = []
        for ch in text:
            code = P._UNI_TO_CODE.get(charset, P._UNI_TO_CODE['english']).get(
                ch, 0x20)
            bits = font.char_bitmap(code, charset)
            for x in range(font.CELL_W):
                line.append('#' if (bits[y] >> (font.CELL_W - 1 - x)) & 1
                            else '.')
        rows.append(''.join(line))
    return rows


def draw_logo(pg, text, row=2, colour='cyan', charset='english'):
    """Centre a mosaic word on the page; returns the row below it."""
    from .. import font
    art = logo_art(text, charset)
    cells = (len(art[0]) + 1) // 2
    col = max(1, (P.COLS - cells) // 2)
    pg.draw_mosaic(row, col, art, colour=colour)
    return row + (len(art) + 2) // 3


def _ellipsise(pg, row):
    """Mark a truncated paragraph, so a reader can tell the text was cut
    rather than the feed being terse."""
    if not 0 <= row < P.ROWS:
        return
    line = pg.rows[row]
    end = P.COLS
    while end > 0 and line[end - 1] == 0x20:
        end -= 1
    at = min(end, P.COLS - 3)
    for i, ch in enumerate('...'):
        pg.put(row, at + i, ord(ch))


def build_index(items, title, base, when=None, index_number=100,
                columns=1, charset='english'):
    """Headline list page: page number then the headline, wrapped onto a
    second line when it does not fit, because a 34-column truncation
    loses the point of most headlines."""
    pg = P.Page(charset=charset, number=str(base), title='%s INDEX' % title)
    header(pg, base, title, when)
    rule(pg, 1)
    pg.write(2, 0, '{yellow}{double}%s' % _escape(title)[:HEAD_WIDTH])
    row = 5
    last = 22
    # Share the rows out: a headline gets up to three lines when the list
    # is short, two when it is long, rather than the last stories being
    # pushed off the page altogether.
    per_item = max(1, min(3, (last - row + 1) // max(1, len(items))))
    for i, item in enumerate(items):
        if row > last:
            break
        num = base + 1 + i
        words = _escape(item.title)
        lines = textwrap.wrap(words, INDEX_WIDTH)
        if len(lines) > 1:
            lines = [lines[0]] + textwrap.wrap(
                words[len(lines[0]):].strip(), INDEX_CONT)
        allowed = min(per_item, last - row + 1)
        if len(lines) > allowed:
            lines = lines[:allowed]
            # the first line shares its row with '{cyan}NNN {white}', so
            # only INDEX_WIDTH cells fit there; continuations get 36
            budget = INDEX_WIDTH if allowed == 1 else INDEX_CONT
            if len(lines[-1]) > budget - 3:
                lines[-1] = lines[-1][:budget - 3].rstrip()
            lines[-1] += '...'
        pg.write(row, 0, '{cyan}%d {white}%s' % (num, lines[0]))
        row += 1
        for cont in lines[1:]:
            pg.write(row, 4, cont)
            row += 1
    nav(pg, 24, nxt=base + 1, main=index_number,
        extra=title.split()[-1])
    pg.meta['role'] = 'index'
    return pg


def build_story(item, number, title, index_number, prev=None, nxt=None,
                when=None, image_path=None, image_mode='mosaic',
                image_rows=12, charset='english', article=None,
                max_paragraphs=2, base=None):
    pg = P.Page(charset=charset, number=str(number), title=_escape(item.title)[:32])
    header(pg, number, title, when)
    rule(pg, 1)

    row = 2
    lines = textwrap.wrap(_escape(item.title).upper(), HEAD_WIDTH)
    head = lines[:3]
    if len(lines) > 3 and len(head[-1]) < HEAD_WIDTH - 2:
        head[-1] += '...'
    for line in head:
        pg.write(row, 0, '{yellow}{double}%s' % line)
        row += 2

    row += 1
    # The body is the article's own text when we have it, the feed
    # summary when we do not.  Either way it stays in the default font -
    # normal height, plain white - the double-height headline above has
    # done the shouting.
    paragraphs = [_escape(p) for p in (article or [item.summary]) if p.strip()]
    if max_paragraphs:
        # a story page is a summary, not the whole article: the opening
        # paragraphs are the news, the rest is detail nobody reads off a
        # television screen
        paragraphs = paragraphs[:max_paragraphs]
    body = textwrap.wrap(' '.join(paragraphs), BODY_WIDTH)

    # Decide how much room the picture wants before laying the body out,
    # so the text gives way to the picture rather than the picture being
    # squashed into a fixed slot and padded with black bars.
    picture = None
    if image_path:
        try:
            picture = imageconv.load(image_path)
        except (ValueError, OSError):
            picture = None
    pic_rows = 0
    if picture is not None:
        # keep room for the summary first - a news page whose text stops
        # mid-sentence reads worse than a slightly smaller picture
        free = 23 - row - min(len(body), 5)
        if free >= 5:
            pic_rows = imageconv.rows_for(picture, P.COLS - 2,
                                          min(image_rows, free))

    body_end = 22 - pic_rows
    for n, line in enumerate(body):
        if row > body_end:
            if n < len(body):
                _ellipsise(pg, row - 1)
            break
        pg.write(row, 0, line)
        row += 1

    if pic_rows:
        top = 23 - pic_rows
        if image_mode == 'mosaic':
            imageconv.to_page(picture, rows=pic_rows, top=top,
                              mode='colour', target=pg)
        elif image_mode == 'sixel':
            # composited into the rendered bitmap using the spare colour
            # registers; see imageconv.composite()
            pg.meta['image'] = image_path
            pg.meta['imagebox'] = '%d,%d,%d,%d' % (top, 1, pic_rows,
                                                   P.COLS - 2)

    nav(pg, 24, prev=prev, nxt=nxt, index=base, main=index_number)
    pg.meta['role'] = 'story'
    if item.link:
        pg.meta['link'] = item.link
    return pg


def build_service(items, title, base, index_number=100, limit=8,
                  image_mode='mosaic', image_rows=12, fetch_image=None,
                  fetch_article=None, when=None, charset='english',
                  max_paragraphs=2):
    """Build an index page plus one page per story.

    fetch_image(url) -> local path, or None.  Only called when the story
    actually has a picture, which is what makes a sixel worth sending.

    fetch_article(url) -> list of paragraphs, or None.  Only called when
    a story's summary is a teaser too short to fill the page; the
    article's text then becomes the body.
    """
    items = items[:limit]
    pages = [(base, build_index(items, title, base, when=when,
                                index_number=index_number, charset=charset))]
    for i, item in enumerate(items):
        number = base + 1 + i
        path = None
        if image_mode != 'none' and item.image and fetch_image:
            path = fetch_image(item.image)
        article = None
        if fetch_article and item.link and len(item.summary) < TEASER_CHARS:
            article = fetch_article(item.link) or None
        pages.append((number, build_story(
            item, number, title, index_number,
            prev=(number - 1 if i else base),
            nxt=(number + 1 if i + 1 < len(items) else base),
            when=when, image_path=path, image_mode=image_mode,
            image_rows=image_rows, charset=charset, article=article,
            max_paragraphs=max_paragraphs, base=base)))
    return pages


def build_front(services, number=100, when=None, charset='english'):
    """A front page listing every service that was built."""
    pg = P.Page(charset=charset, number=str(number), title='HECNET')
    header(pg, number, 'HECNET', when)
    rule(pg, 1)
    row = draw_logo(pg, 'HECNET', 2, 'cyan', charset) + 1
    for title, base, count in services:
        if row > 21:
            break
        pg.write(row, 0, '{yellow}%-3d {white}%-22s {green}%d pages'
                 % (base, title[:22], count))
        row += 1
    pg.write(23, 0, '{cyan}Pages refresh automatically')
    links = [(title.split()[-1][:5], base) for title, base, _ in services[:4]]
    P.fastext_bar(pg, links, 24)
    pg.meta['role'] = 'front'
    return pg


def write_pages(pages, outdir):
    os.makedirs(outdir, exist_ok=True)
    written = []
    for number, pg in pages:
        path = os.path.join(outdir, '%s.ttx' % number)
        P.save(pg, path)
        written.append(path)
    return written
