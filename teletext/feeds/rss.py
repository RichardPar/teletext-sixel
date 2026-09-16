"""RSS 2.0 / Atom parsing with the standard library only."""

import html
import re
import xml.etree.ElementTree as ET

MEDIA_NS = 'http://search.yahoo.com/mrss/'
ATOM_NS = 'http://www.w3.org/2005/Atom'

_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


class Item(object):
    __slots__ = ('title', 'summary', 'link', 'published', 'image', 'source')

    def __init__(self, title='', summary='', link='', published='',
                 image=None, source=''):
        self.title = title
        self.summary = summary
        self.link = link
        self.published = published
        self.image = image
        self.source = source

    def __repr__(self):
        return '<Item %r>' % self.title[:40]


def clean(text):
    if not text:
        return ''
    text = _TAG_RE.sub(' ', text)
    text = html.unescape(text)
    return _WS_RE.sub(' ', text).strip()


def _local(el):
    """The tag without its namespace.

    RSS 2.0 puts its elements in no namespace, RSS 1.0 puts them in the
    RDF one and Atom in its own, but they all use the same words.
    Matching on the local name reads all three without a special case
    for each - Slashdot is RDF, the BBC is RSS 2.0.
    """
    return el.tag.rsplit('}', 1)[-1] if isinstance(el.tag, str) else ''


def _child(el, name):
    for kid in el:
        if _local(kid) == name:
            return kid
    return None


def _child_text(el, name):
    kid = _child(el, name)
    return kid.text if kid is not None and kid.text else ''


def parse(data, source=''):
    """Parse RSS 2.0, RSS 1.0/RDF or Atom into a list of Items."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError('not valid RSS or Atom: %s' % exc)
    if _local(root) == 'feed':
        return _parse_atom(root, source)
    return _parse_rss(root, source)


def feed_title(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return ''
    channel = _child(root, 'channel')
    for node in (channel, root):
        if node is None:
            continue
        text = _child_text(node, 'title')
        if text:
            return clean(text)
    return ''


def _parse_rss(root, source):
    items = []
    for el in root.iter():
        if _local(el) != 'item':
            continue
        image = None
        best = None
        for kid in el:
            if _local(kid) not in ('thumbnail', 'content'):
                continue
            url = kid.get('url')
            if not url:
                continue
            try:
                width = int(kid.get('width') or 0)
            except ValueError:
                width = 0
            if best is None or width > best[0]:
                best = (width, url)
        if best:
            image = best[1]
        if image is None:
            enc = _child(el, 'enclosure')
            if enc is not None and (enc.get('type') or '').startswith('image'):
                image = enc.get('url')
        items.append(Item(
            title=clean(_child_text(el, 'title')),
            summary=clean(_child_text(el, 'description')
                          or _child_text(el, 'encoded')),
            link=(_child_text(el, 'link') or el.get(
                '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about')
                or '').strip(),
            published=(_child_text(el, 'pubDate')
                       or _child_text(el, 'date')).strip(),
            image=image,
            source=source))
    return items


def _parse_atom(root, source):
    items = []
    for el in root.findall('{%s}entry' % ATOM_NS):
        link = ''
        for l in el.findall('{%s}link' % ATOM_NS):
            if l.get('rel') in (None, 'alternate'):
                link = l.get('href') or ''
                break
        summary = _text(el, '{%s}summary' % ATOM_NS) or \
            _text(el, '{%s}content' % ATOM_NS)
        image = None
        m = el.find('{%s}thumbnail' % MEDIA_NS)
        if m is not None:
            image = m.get('url')
        items.append(Item(
            title=clean(_text(el, '{%s}title' % ATOM_NS)),
            summary=clean(summary),
            link=link.strip(),
            published=(_text(el, '{%s}updated' % ATOM_NS) or '').strip(),
            image=image,
            source=source))
    return items


def _text(el, path):
    node = el.find(path)
    return node.text if node is not None and node.text else ''
