#!/bin/sh
# Rebuild every page from the feeds and deploy it where the PDP-11 can
# fetch it.  Run hourly from cron; the PDP-11 fetches at five past, so
# it never reads a directory being written.
set -e

HERE=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$HERE/scripts/deploy.conf" ] && . "$HERE/scripts/deploy.conf"
SERVICES=${TTX_SERVICES:-"news sport weather slashdot"}

"$HERE/ttx" feeds build $SERVICES --limit 6 --front \
    --out "$HERE/pages/feeds" --refresh-now

exec "$HERE/scripts/deploy.sh"
