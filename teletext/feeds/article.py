"""Pull the article text out of a story's own web page.

A feed item carries a one-sentence summary; the story itself is on the
linked page.  This walks the HTML with html.parser and keeps the
paragraphs, preferring the ones inside <main> or <article> and skipping
scripts, navigation and page chrome, so a story page can be filled with
the article rather than two lines of teaser.
"""

import re
from html.parser import HTMLParser

# Tags whose text is never part of the story.
_SKIP = ('script', 'style', 'nav', 'header', 'footer', 'aside', 'form',
         'noscript', 'svg', 'template', 'iframe', 'figure', 'figcaption',
         'button', 'select', 'table')
# Tags that each contribute one paragraph.
_BLOCKS = ('p', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre')
# The story proper sits inside one of these when the page has them.
_ROOTS = ('main', 'article')

# A story page shows its text on one screen: a dozen or so lines under
# the images, which is a couple of thousand characters at most.  Keeping
# much more than that only fattens the page file for text nobody sees.
# --article-chars moves the line.
MAX_CHARS = 2000
# Less body than this and the extraction has failed: the caller falls
# back to the feed summary rather than showing fragments.
MIN_CHARS = 160

_WS = re.compile(r'\s+')


class _Extractor(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self._skip = 0
        self._root = 0
        self._buf = None
        self.all = []
        self.rooted = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag in _ROOTS:
            self._root += 1
        elif tag in _BLOCKS and not self._skip:
            self._flush()
            self._buf = []

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _ROOTS:
            self._root = max(0, self._root - 1)
        elif tag in _BLOCKS and not self._skip:
            self._flush()

    def handle_data(self, data):
        if self._buf is not None and not self._skip:
            self._buf.append(data)

    def _flush(self):
        if self._buf is None:
            return
        text = _WS.sub(' ', ''.join(self._buf)).strip()
        if text:
            self.all.append(text)
            if self._root:
                self.rooted.append(text)
        self._buf = None


def extract(html, max_chars=MAX_CHARS):
    """The story's paragraphs as a list, or [] if the page has none."""
    if isinstance(html, bytes):
        html = html.decode('utf-8', 'replace')
    ex = _Extractor()
    ex.feed(html)
    ex.close()
    paras = ex.rooted if len(ex.rooted) >= 2 else ex.all
    out = []
    total = 0
    for para in paras:
        if total >= max_chars:
            break
        if total + len(para) > max_chars:
            room = max_chars - total
            para = para[:room].rsplit(' ', 1)[0] if ' ' in para[:room] \
                else para[:room]
            if len(para) < 40:
                break
        out.append(para)
        total += len(para) + 1
    if total < MIN_CHARS:
        return []
    return out
