"""Minimal HTTP fetcher with an on-disk cache.

Kept dependency-free (urllib only) so the whole thing runs on a stock
Python install next to the PDP-11.
"""

import errno
import hashlib
import os
import time
import urllib.error
import urllib.request

USER_AGENT = 'ttx-teletext/0.1 (+https://example.invalid/ttx)'
DEFAULT_CACHE = os.path.expanduser('~/.cache/ttx')


class FetchError(Exception):
    pass


def cache_dir(path=None):
    path = path or os.environ.get('TTX_CACHE', DEFAULT_CACHE)
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    return path


def get(url, timeout=20, max_age=300, cache=None, force=False):
    """Fetch a URL, returning bytes.  Cached copies younger than max_age
    are reused; a stale copy is served if the network is unavailable."""
    cdir = cache_dir(cache)
    key = hashlib.sha1(url.encode('utf-8')).hexdigest()
    path = os.path.join(cdir, key)
    if not force and max_age and os.path.exists(path):
        if time.time() - os.path.getmtime(path) < max_age:
            with open(path, 'rb') as fh:
                return fh.read()
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        if os.path.exists(path):
            with open(path, 'rb') as fh:
                return fh.read()
        raise FetchError('%s: %s' % (url, exc))
    tmp = path + '.tmp'
    with open(tmp, 'wb') as fh:
        fh.write(data)
    os.replace(tmp, path)
    return data


def get_file(url, suffix='', **kw):
    """Fetch a URL and return a path to the cached copy (for images)."""
    data = get(url, **kw)
    cdir = cache_dir(kw.get('cache'))
    key = hashlib.sha1(url.encode('utf-8')).hexdigest()
    path = os.path.join(cdir, key + (suffix or _suffix(url, data)))
    if not os.path.exists(path):
        with open(path, 'wb') as fh:
            fh.write(data)
    return path


def _suffix(url, data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return '.png'
    if data[:2] == b'\xff\xd8':
        return '.jpg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    base = url.split('?')[0]
    _, ext = os.path.splitext(base)
    return ext if len(ext) <= 5 else '.bin'
