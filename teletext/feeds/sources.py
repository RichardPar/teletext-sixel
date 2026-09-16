"""Known feeds, with Ceefax-ish page numbers."""

FEEDS = {
    # name:        (title,            url,                                                    base page)
    'news':        ('BBC NEWS',       'http://feeds.bbci.co.uk/news/rss.xml',                  101),
    'uk':          ('BBC UK',         'http://feeds.bbci.co.uk/news/uk/rss.xml',               110),
    'world':       ('BBC WORLD',      'http://feeds.bbci.co.uk/news/world/rss.xml',            120),
    'politics':    ('BBC POLITICS',   'http://feeds.bbci.co.uk/news/politics/rss.xml',         130),
    'business':    ('BBC BUSINESS',   'http://feeds.bbci.co.uk/news/business/rss.xml',         140),
    'tech':        ('BBC TECHNOLOGY', 'http://feeds.bbci.co.uk/news/technology/rss.xml',       150),
    'science':     ('BBC SCIENCE',    'http://feeds.bbci.co.uk/news/science_and_environment/rss.xml', 160),
    'health':      ('BBC HEALTH',     'http://feeds.bbci.co.uk/news/health/rss.xml',           170),
    'entertainment': ('BBC ARTS',     'http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml', 180),
    'sport':       ('BBC SPORT',      'http://feeds.bbci.co.uk/sport/rss.xml',                 300),
    'football':    ('BBC FOOTBALL',   'http://feeds.bbci.co.uk/sport/football/rss.xml',        310),
    'cricket':     ('BBC CRICKET',    'http://feeds.bbci.co.uk/sport/cricket/rss.xml',         320),
    # weather is not an RSS news feed: it fans out to the BBC's per-city
    # forecast feeds and builds its own pages (see weather.py)
    'weather':     ('UK WEATHER',     'https://weather-broker-cdn.api.bbci.co.uk/en/forecast/rss/3day/', 400),
    'register':    ('THE REGISTER',   'https://www.theregister.com/headlines.atom',            400),
    'slashdot':    ('SLASHDOT',       'http://rss.slashdot.org/Slashdot/slashdotMain',         410),
    'lwn':         ('LWN.NET',        'https://lwn.net/headlines/rss',                         420),
}


def resolve(name):
    """Return (title, url, base) for a feed name or a bare URL."""
    key = name.lower()
    if key in FEEDS:
        return FEEDS[key]
    if '://' in name:
        return ('FEED', name, 500)
    raise ValueError('unknown feed %r (try: %s)'
                     % (name, ', '.join(sorted(FEEDS))))
