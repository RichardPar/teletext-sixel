"""`ttx feeds ...` - download feeds and turn them into teletext pages."""

import argparse
import os
import sys
import time

from .. import page as P
from . import article, builder, fetch, rss, sources, weather


def _feed_items(name, args):
    title, url, base = sources.resolve(name)
    if args.from_file:
        with open(args.from_file, 'rb') as fh:
            data = fh.read()
    else:
        data = fetch.get(url, max_age=args.max_age, force=args.refresh_now,
                         timeout=args.timeout)
    items = rss.parse(data, source=name)
    feed_name = rss.feed_title(data)
    if feed_name and title == 'FEED':
        title = feed_name.upper()
    if args.title:
        title = args.title.upper()
    if args.base:
        base = args.base
    return title, base, items


def _image_fetcher(args):
    if args.images == 'none':
        return None

    def get(url):
        try:
            return fetch.get_file(url, max_age=args.max_age,
                                  timeout=args.timeout)
        except (fetch.FetchError, OSError) as exc:
            sys.stderr.write('image: %s\n' % exc)
            return None
    return get


def _article_fetcher(args):
    """Full story text for summaries that are only a teaser."""
    if not args.full_text:
        return None

    def get(url):
        try:
            data = fetch.get(url, max_age=args.max_age, timeout=args.timeout)
        except (fetch.FetchError, OSError) as exc:
            sys.stderr.write('article: %s\n' % exc)
            return None
        return article.extract(data, max_chars=args.article_chars) or None
    return get


WEATHER_NAMES = ('weather', 'uk-weather', 'forecast')


def _weather_pages(args, when):
    """Weather fans out to one feed per location, so it builds its own
    pages rather than going through the news story layout."""
    def get(url):
        try:
            return fetch.get(url, max_age=args.max_age, force=args.refresh_now,
                             timeout=args.timeout)
        except (fetch.FetchError, OSError) as exc:
            sys.stderr.write('weather: %s\n' % exc)
            return None

    places = weather.LOCATIONS
    if args.places:
        wanted = [p.strip().lower() for p in args.places.split(',')]
        places = [(n, i) for n, i in weather.LOCATIONS if n.lower() in wanted]
        missing = [w for w in wanted
                   if w not in [n.lower() for n, _ in weather.LOCATIONS]]
        for m in missing:
            sys.stderr.write('weather: no location %r; known: %s\n'
                             % (m, ', '.join(n for n, _ in weather.LOCATIONS)))
    return weather.build_service(
        get, base=args.base or 400, index_number=args.index,
        limit=args.limit, locations=places, when=when, charset=args.charset,
        image_dir=args.out)


def _build(names, args):
    """Build every requested service; returns (paths, summary)."""
    builder.CLOCK = bool(getattr(args, 'clock', False))
    when = time.time()
    services = []
    all_pages = []
    for name in names:
        if name.lower() in WEATHER_NAMES:
            pages = _weather_pages(args, when)
            if pages:
                all_pages.extend(pages)
                services.append(('UK WEATHER', pages[0][0], len(pages)))
            continue
        try:
            title, base, items = _feed_items(name, args)
        except (fetch.FetchError, ValueError, OSError) as exc:
            sys.stderr.write('ttx feeds: %s\n' % exc)
            continue
        if not items:
            sys.stderr.write('ttx feeds: %s returned no items\n' % name)
            continue
        pages = builder.build_service(
            items, title, base, index_number=args.index,
            limit=args.limit, image_mode=args.images,
            image_rows=args.image_rows, fetch_image=_image_fetcher(args),
            fetch_article=_article_fetcher(args),
            max_paragraphs=args.body_paragraphs,
            when=when, charset=args.charset)
        all_pages.extend(pages)
        services.append((title, base, len(pages)))
    if not all_pages:
        return [], services
    if args.front and services:
        all_pages.insert(0, (args.index,
                             builder.build_front(services, args.index, when,
                                                 charset=args.charset)))
    paths = builder.write_pages(all_pages, args.out)
    return paths, services


def cmd_list(args):
    for name in sorted(sources.FEEDS):
        title, url, base = sources.FEEDS[name]
        print('%-14s %-16s %3d  %s' % (name, title, base, url))
    return 0


def cmd_build(args):
    paths, services = _build(args.names, args)
    for title, base, count in services:
        sys.stderr.write('%-20s p%-4d %2d pages\n' % (title, base, count))
    for p in paths:
        print(p)
    return 0 if paths else 1


def cmd_carousel(args):
    from .. import cli as maincli
    write, close = maincli._open_output(args)
    built = 0
    paths = []
    try:
        while True:
            if not paths or (time.time() - built) >= args.refresh:
                new_paths, _ = _build(args.names, args)
                if new_paths:
                    paths = new_paths
                    built = time.time()
                elif not paths:
                    if args.once:
                        sys.stderr.write('nothing to show\n')
                        return 1
                    sys.stderr.write('nothing to show; retrying in 60s\n')
                    time.sleep(60)
                    continue
            first = True
            for path in paths:
                pg = P.load(path)
                pg.meta['_dir'] = os.path.dirname(os.path.abspath(path))
                maincli._emit_page(pg, args, write, first=first)
                first = False
                time.sleep(args.delay)
                if (time.time() - built) >= args.refresh:
                    break
            if args.once:
                return 0
    except KeyboardInterrupt:
        return 130
    finally:
        close()


def build_parser():
    ap = argparse.ArgumentParser(
        prog='ttx feeds',
        description='Download RSS/Atom feeds and build teletext pages.')
    sub = ap.add_subparsers(dest='cmd')

    def common(sp):
        sp.add_argument('--out', default='pages/feeds',
                        help='output directory for .ttx pages')
        sp.add_argument('--limit', type=int, default=8,
                        help='stories per service (default 8)')
        sp.add_argument('--images', default='sixel',
                        choices=['sixel', 'mosaic', 'none'],
                        help='sixel: photo composited into the spare colour '
                             'registers, much the better picture; mosaic: '
                             'teletext blocks, self-contained and half the '
                             'bytes; none: text only')
        sp.add_argument('--image-rows', type=int, default=12,
                        help='most character rows a picture may use; the '
                             'actual height follows the image aspect')
        sp.add_argument('--index', type=int, default=100,
                        help='front page number')
        sp.add_argument('--base', type=int, help='override the base page number')
        sp.add_argument('--title', help='override the service name')
        sp.add_argument('--front', action='store_true',
                        help='also write a front page listing the services')
        sp.add_argument('--no-full-text', dest='full_text',
                        action='store_false', default=True,
                        help='do not fetch the linked page to fill a story '
                             'with the article\'s text; show only the feed '
                             'summary (default: full text)')
        sp.add_argument('--clock', action='store_true',
                        help='put the time back in the page header '
                             '(the date is shown either way)')
        sp.add_argument('--places',
                        help='weather: comma-separated locations to show '
                             '(default: all of them)')
        sp.add_argument('--body-paragraphs', type=int, default=2,
                        help='paragraphs of the story to keep '
                             '(default 2; 0 for all of it)')
        sp.add_argument('--article-chars', type=int,
                        default=article.MAX_CHARS,
                        help='how much of a long article to keep '
                             '(default %d characters)' % article.MAX_CHARS)
        sp.add_argument('--charset', default='english',
                        choices=['english', 'ascii'])
        sp.add_argument('--max-age', type=int, default=300,
                        help='seconds a cached download stays fresh')
        sp.add_argument('--refresh-now', action='store_true',
                        help='ignore the cache for this run')
        sp.add_argument('--timeout', type=float, default=20)
        sp.add_argument('--from-file', help='read feed XML from a file instead')

    sp = sub.add_parser('list', help='list the known feeds')
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser('build', help='build pages from feeds')
    sp.add_argument('names', nargs='+', help='feed names or URLs')
    common(sp)
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser('carousel',
                        help='build, then cycle the pages as sixel forever')
    sp.add_argument('names', nargs='+')
    common(sp)
    sp.add_argument('--delay', type=float, default=12,
                    help='seconds each page is shown')
    sp.add_argument('--refresh', type=float, default=900,
                    help='seconds between feed downloads')
    sp.add_argument('--once', action='store_true',
                    help='one pass, then stop')
    from .. import cli as maincli
    maincli._add_render_opts(sp)
    maincli._add_output_opts(sp)
    sp.set_defaults(func=cmd_carousel)
    return ap


def main(argv):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, 'cmd', None):
        ap.print_help()
        return 1
    return args.func(args)
