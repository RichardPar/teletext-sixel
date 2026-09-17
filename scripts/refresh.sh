#!/bin/sh
# Rebuild every page from the feeds and deploy it where the PDP-11 can
# fetch it.  Run hourly from cron; the PDP-11 fetches at five past, so
# it never reads a directory being written.
set -e

HERE=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$HERE/scripts/deploy.conf" ] && . "$HERE/scripts/deploy.conf"
SERVICES=${TTX_SERVICES:-"news science sport weather slashdot"}
# photographs: sixel is the better picture, mosaic is teletext blocks the
# page itself holds, which is what TTX_EMIT=text needs to keep pictures
IMAGES=${TTX_IMAGES:-sixel}

"$HERE/ttx" feeds build $SERVICES --limit 6 --front \
    --images "$IMAGES" --out "$HERE/pages/feeds" --refresh-now

exec "$HERE/scripts/deploy.sh"
