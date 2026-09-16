"""UK weather pages from the BBC's 3-day forecast feeds.

Each location has an RSS feed whose three items are today and the next
two days.  The title carries the day, the conditions and both
temperatures; the description carries wind, humidity and the rest as
comma-separated pairs.

Location ids are GeoNames ids.  Every one in LOCATIONS has been checked
against the name the feed reports - 2640729 looks like Plymouth and is
in fact Oxford.
"""

import os
import re
import sys
import time

from .. import font, imageconv, page as P, render
from . import rss, ukmap
from .builder import _escape, header, now_string, nav, rule

FEED_URL = 'https://weather-broker-cdn.api.bbci.co.uk/en/forecast/rss/3day/%s'

# Where the map sits on its page, in character cells.
MAP_TOP, MAP_LEFT, MAP_ROWS, MAP_COLS = 4, 1, 20, 20

# name, GeoNames id - ordered roughly south to north, as a forecast is read
LOCATIONS = [
    ('London', 2643743),
    ('Cambridge', 2653941),
    ('Southampton', 2637487),
    ('Plymouth', 2640194),
    ('Bristol', 2654675),
    ('Cardiff', 2653822),
    ('Swansea', 2636432),
    ('Norwich', 2641181),
    ('Birmingham', 2655603),
    ('Nottingham', 2641170),
    ('Manchester', 2643123),
    ('Liverpool', 2644210),
    ('Leeds', 2644688),
    ('Newcastle', 2641673),
    ('Belfast', 2655984),
    ('Glasgow', 2648579),
    ('Edinburgh', 2650225),
    ('Aberdeen', 2657832),
    ('Inverness', 2646088),
]

_DAY_RE = re.compile(r'^\s*([^:]+):\s*(.+?)\s*,\s*(?:Minimum|Maximum)\s', re.S)
_MIN_RE = re.compile(r'Minimum Temperature:\s*(-?\d+)')
_MAX_RE = re.compile(r'Maximum Temperature:\s*(-?\d+)')

# Conditions as the BBC writes them are too long for a 14-column field.
ABBREVIATIONS = [
    ('Sunny Intervals', 'Sunny ints'),
    ('Partly Cloudy', 'Partly cloudy'),
    ('Light Rain Showers', 'Lt showers'),
    ('Heavy Rain Showers', 'Hvy showers'),
    ('Light Snow Showers', 'Lt snow'),
    ('Heavy Snow Showers', 'Hvy snow'),
    ('Thundery Showers', 'Thundery'),
    ('Light Rain', 'Light rain'),
    ('Heavy Rain', 'Heavy rain'),
    ('Drizzle', 'Drizzle'),
    ('Thick Cloud', 'Thick cloud'),
    ('White Cloud', 'White cloud'),
    ('Clear Sky', 'Clear'),
    ('Mist', 'Mist'),
    ('Fog', 'Fog'),
    ('Sunny', 'Sunny'),
]

# The feed spells directions out; a forecast table wants the compass.
COMPASS = {
    'northerly': 'N', 'north-easterly': 'NE', 'easterly': 'E',
    'south-easterly': 'SE', 'southerly': 'S', 'south-westerly': 'SW',
    'westerly': 'W', 'north-westerly': 'NW',
    'north north-easterly': 'NNE', 'east north-easterly': 'ENE',
    'east south-easterly': 'ESE', 'south south-easterly': 'SSE',
    'south south-westerly': 'SSW', 'west south-westerly': 'WSW',
    'west north-westerly': 'WNW', 'north north-westerly': 'NNW',
}


def compass(direction):
    return COMPASS.get((direction or '').strip().lower(), (direction or '')[:3])


# condition -> (teletext colour, symbol name)
_KINDS = (
    ('thunder', 'magenta', 'thunder'),
    ('snow', 'white', 'snow'),
    ('sleet', 'white', 'snow'),
    ('hail', 'white', 'snow'),
    ('shower', 'cyan', 'rain'),
    ('rain', 'cyan', 'rain'),
    ('drizzle', 'cyan', 'rain'),
    ('mist', 'white', 'fog'),
    ('fog', 'white', 'fog'),
    ('sunny', 'yellow', 'sun'),
    ('clear', 'yellow', 'sun'),
    ('cloud', 'white', 'cloud'),
)

# Mosaic weather symbols, 8 pixels across and 6 down: four cells by two.
SYMBOLS = {
    'sun': ['..####..',
            '.######.',
            '########',
            '########',
            '.######.',
            '..####..'],
    'cloud': ['..####..',
              '.######.',
              '########',
              '########',
              '........',
              '........'],
    'rain': ['..####..',
             '.######.',
             '########',
             '.#..#..#',
             '#..#..#.',
             '.#..#..#'],
    'snow': ['..####..',
             '.######.',
             '########',
             '.#.#.#.#',
             '#.#.#.#.',
             '.#.#.#.#'],
    'thunder': ['..####..',
                '.######.',
                '########',
                '...##...',
                '..##....',
                '.####...'],
    'fog': ['........',
            '########',
            '........',
            '########',
            '........',
            '########'],
}


class Forecast(object):
    __slots__ = ('day', 'condition', 'high', 'low', 'detail')

    def __init__(self, day, condition, high, low, detail=None):
        self.day = day
        self.condition = condition
        self.high = high
        self.low = low
        self.detail = detail or {}

    def __repr__(self):
        return '<Forecast %s %s %s/%s>' % (self.day, self.condition,
                                           self.high, self.low)

    def kind(self):
        """(colour, symbol) for these conditions."""
        low = self.condition.lower()
        for word, colour, symbol in _KINDS:
            if word in low:
                return colour, symbol
        return 'white', 'cloud'

    def short(self, width=14):
        text = self.condition
        for long_form, short_form in ABBREVIATIONS:
            if text.lower().startswith(long_form.lower()):
                text = short_form
                break
        return _escape(text)[:width]


def parse(data):
    """The three days of one location's feed."""
    out = []
    for item in rss.parse(data):
        m = _DAY_RE.match(item.title)
        if not m:
            continue
        day, condition = m.group(1).strip(), m.group(2).strip()
        low = _MIN_RE.search(item.title) or _MIN_RE.search(item.summary)
        high = _MAX_RE.search(item.title) or _MAX_RE.search(item.summary)
        detail = {}
        for part in item.summary.split(','):
            key, _, value = part.partition(':')
            if value:
                detail[key.strip()] = value.strip()
        out.append(Forecast(day, condition,
                            int(high.group(1)) if high else None,
                            int(low.group(1)) if low else None,
                            detail))
    return out


def _temp(value):
    return '--' if value is None else '%d' % value


def reading(cast):
    """The temperature worth showing.

    Overnight the feed gives a minimum and no maximum, so a page that
    only ever shows maxima is blank all evening.
    """
    return cast.high if cast.high is not None else cast.low


def build_summary(places, number, base, index_number=100, when=None,
                  day=0, charset='english'):
    """One page: every location's conditions and temperatures for a day.

    places is [(name, [Forecast, ...]), ...].
    """
    pg = P.Page(charset=charset, number=str(number), title='UK WEATHER')
    label = 'UK WEATHER'
    header(pg, number, label, when)
    rule(pg, 1)
    when_name = 'TODAY'
    for _, casts in places:
        if len(casts) > day:
            when_name = casts[day].day.upper()
            break
    pg.write(2, 0, '{yellow}{double}%s' % when_name[:38])
    daytime = any(c[1][day].high is not None for c in
                  [(n, cs) for n, cs in places if len(cs) > day])
    heads = 'Max Min' if daytime else '    Min'
    pg.write(4, 0, '{cyan}%-12s %-13s %s' % ('', 'Conditions', heads))

    row = 5
    last = 23
    dropped = []
    for name, casts in places:
        if len(casts) <= day:
            continue
        if row > last:
            dropped.append(name)
            continue
        cast = casts[day]
        colour, _ = cast.kind()
        if daytime:
            pg.write(row, 0, '{white}%-12s {%s}%-13s {yellow}%3s {cyan}%3s'
                     % (name[:12], colour, cast.short(13), _temp(cast.high),
                        _temp(cast.low)))
        else:
            pg.write(row, 0, '{white}%-12s {%s}%-13s     {cyan}%3s'
                     % (name[:12], colour, cast.short(13), _temp(cast.low)))
        row += 1
    if dropped:
        sys.stderr.write('weather: no room on page %s for %s; use --places '
                         'to choose\n' % (number, ', '.join(dropped)))
    nav(pg, 24, nxt=number + 1, index=base, main=index_number)
    pg.meta['role'] = 'weather'
    return pg


def build_place(name, casts, number, index_number, base, prev=None, nxt=None,
                when=None, charset='english'):
    """Three days for one location, with a mosaic symbol for each."""
    pg = P.Page(charset=charset, number=str(number),
                title='WEATHER %s' % name.upper())
    header(pg, number, 'WEATHER', when)
    rule(pg, 1)
    pg.write(2, 0, '{yellow}{double}%s' % _escape(name).upper()[:38])

    row = 5
    for cast in casts[:3]:
        if row > 20:
            break
        colour, symbol = cast.kind()
        pg.write(row, 0, '{cyan}%s' % _escape(cast.day)[:20])
        pg.write(row + 1, 0, '{%s}%s' % (colour, cast.short(20)))
        if cast.high is None:
            pg.write(row + 1, 26, '{cyan}%s{white} C min' % _temp(cast.low))
        else:
            pg.write(row + 1, 24, '{yellow}%s{white}/{cyan}%s{white} C'
                     % (_temp(cast.high), _temp(cast.low)))
        art = SYMBOLS.get(symbol, SYMBOLS['cloud'])
        pg.draw_mosaic(row, 35, art, colour=colour)
        detail = cast.detail
        bits = []
        if detail.get('Wind Speed'):
            bits.append('Wind %s %s' % (compass(detail.get('Wind Direction')),
                                        detail['Wind Speed']))
        if detail.get('Humidity'):
            bits.append('Humidity %s' % detail['Humidity'])
        if bits:
            pg.write(row + 2, 0, '{white}%s' % _escape(', '.join(bits))[:39])
        row += 4

    pg.write(23, 0, '{cyan}Source: BBC Weather')
    nav(pg, 24, prev=prev, nxt=nxt, index=base, main=index_number)
    pg.meta['role'] = 'weather'
    return pg


def build_map_page(places, number, index_number=100, when=None,
                   image_dir=None, day=0, charset='english', size=None):
    """The map page: the country with temperatures on it, and a list of
    every location down the right-hand side.

    The map is drawn to a PNG next to the pages and referenced with
    !meta image, so it goes out through the same path as a photograph -
    quantised into the colour registers the terminal has spare.
    """
    if not image_dir:
        return None
    pg = P.Page(charset=charset, number=str(number), title='UK WEATHER MAP')
    header(pg, number, 'UK WEATHER', when)
    rule(pg, 1)

    marks = []
    row = 4
    for name, casts in places:
        if len(casts) <= day:
            continue
        cast = casts[day]
        colour, _ = cast.kind()
        rgb = render.PALETTE[P.COLOUR_NAMES.index(colour)]
        value = reading(cast)
        if value is not None:
            marks.append((name, '%d' % value, rgb))
        if row <= 22:
            pg.write(row, 22, '{%s}%-11s%3s' % (colour, name[:11],
                                                _temp(value)))
            row += 1

    # Draw at the pixel size the box has at the default scale, so the
    # labels are the teletext font at 1:1 rather than a downscale of it.
    if size is None:
        cw, ch = render.cell_size(1.5)
        size = (MAP_COLS * cw, MAP_ROWS * ch)
    img = ukmap.draw(size[0], size[1], marks, charset=charset)
    path = os.path.join(image_dir, 'ukmap-%s.png' % number)
    try:
        os.makedirs(image_dir, exist_ok=True)
        # the map has only a handful of colours: quantising to 16 keeps
        # them exact and the sixel small
        imageconv.write_png(imageconv.quantize(img, 16, dither=False), path)
    except OSError as exc:
        sys.stderr.write('weather: could not write the map: %s\n' % exc)
        return None
    # relative to the page, which is where it sits: the pages directory
    # can then be copied somewhere else and the map goes with it
    pg.meta['image'] = os.path.basename(path)
    pg.meta['imagebox'] = '%d,%d,%d,%d' % (MAP_TOP, MAP_LEFT, MAP_ROWS,
                                           MAP_COLS)
    pg.meta['role'] = 'weather'
    # the map is the service's own front page, so it has no INDEX key
    nav(pg, 24, nxt=number + 1, main=index_number)
    return pg


def build_service(fetch_feed, base=400, index_number=100, limit=8,
                  locations=None, when=None, charset='english',
                  image_dir=None):
    """Summary pages for today and tomorrow, then a page per location.

    fetch_feed(url) -> bytes.  Locations that fail to download are left
    out rather than shown blank.
    """
    when = when or time.time()
    places = []
    for name, lid in (locations or LOCATIONS):
        try:
            data = fetch_feed(FEED_URL % lid)
        except Exception:
            continue
        if not data:
            continue
        try:
            casts = parse(data)
        except ValueError:
            continue
        if casts:
            places.append((name, casts))
    if not places:
        return []

    pages = []
    mapped = build_map_page(places, base, index_number, when,
                            image_dir=image_dir, charset=charset)
    if mapped is not None:
        pages.append((base, mapped))
    number = base + len(pages)
    pages.append((number, build_summary(places, number, base, index_number,
                                        when, day=0, charset=charset)))
    if any(len(c) > 1 for _, c in places):
        pages.append((base + len(pages),
                      build_summary(places, base + len(pages), base,
                                    index_number, when, day=1,
                                    charset=charset)))
    number = base + len(pages)
    detail = places[:limit]
    for i, (name, casts) in enumerate(detail):
        pages.append((number + i, build_place(
            name, casts, number + i, index_number, base,
            prev=(number + i - 1 if i else base),
            nxt=(number + i + 1 if i + 1 < len(detail) else base),
            when=when, charset=charset)))
    return pages
