#!/usr/bin/env python3
"""Rebuild the front page (100.ttx) from the per-service summary lines
`ttx feeds build` prints to stderr.

Needed because a feed whose default base page collides with another (e.g.
register and weather both default to page 400) has to be built in its own
`ttx feeds build` call with its own --base, outside the single call that
--front covers - so the front page has to be stitched together afterwards
from every build's summary instead.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from teletext import page as P
from teletext.feeds import builder

LINE = re.compile(r'^(.*?)\s*p(\d+)\s+(\d+) pages\s*$')


def main(argv):
    if len(argv) < 2:
        sys.stderr.write('usage: front_page.py OUTDIR LOGFILE ...\n')
        return 2
    outdir, logs = argv[0], argv[1:]
    services = []
    for log in logs:
        with open(log) as fh:
            for line in fh:
                m = LINE.match(line.rstrip('\n'))
                if m:
                    title, base, count = m.groups()
                    services.append((title, int(base), int(count)))
    if not services:
        sys.stderr.write('front_page: no services found in %s\n' % ', '.join(logs))
        return 1
    pg = builder.build_front(services)
    P.save(pg, os.path.join(outdir, '100.ttx'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
