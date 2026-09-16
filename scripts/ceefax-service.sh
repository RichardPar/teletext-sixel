#!/bin/sh
# Run a small Ceefax service on a terminal attached to a serial line.
#
#   scripts/ceefax-service.sh /dev/ttyS0 9600
#
# Pages are rebuilt every 15 minutes and cycled every 12 seconds.
set -e

DEV=${1:-/dev/ttyS0}
BAUD=${2:-9600}
HERE=$(dirname "$0")/..

exec "$HERE/ttx" feeds carousel news world sport tech \
    --out "$HERE/pages/feeds" \
    --limit 6 --images mosaic --front \
    --delay 12 --refresh 900 \
    --scale 2 --terminal vt340 --transparent --clear \
    --device "$DEV" --baud "$BAUD"
