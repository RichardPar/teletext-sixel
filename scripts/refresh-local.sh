#!/bin/sh
# Rebuild every page from the feeds and deploy it straight into the local
# FTP directory (see deploy-local.sh). Run hourly from cron; the PDP-11
# fetches at five past, so it never reads a directory being written.
set -e

HERE=$(cd "$(dirname "$0")/.." && pwd)
SERVICES=${TTX_SERVICES:-"news science sport weather slashdot"}
# photographs: sixel is the better picture, mosaic is teletext blocks the
# page itself holds, which is what TTX_EMIT=text needs to keep pictures
IMAGES=${TTX_IMAGES:-sixel}
LOG1=$(mktemp)
LOG2=$(mktemp)
trap 'rm -f "$LOG1" "$LOG2"' EXIT

"$HERE/ttx" feeds build $SERVICES --limit 6 --images "$IMAGES" \
    --out "$HERE/pages/feeds" --refresh-now 2> "$LOG1"
cat "$LOG1" >&2

# register defaults to page 400, the same base weather uses, so it has to
# be built separately with its own base to avoid overwriting weather's
# pages.
"$HERE/ttx" feeds build register --limit 6 --base 430 \
    --images "$IMAGES" --out "$HERE/pages/feeds" --refresh-now 2> "$LOG2"
cat "$LOG2" >&2

# --front only lists the services built in the same invocation, so with
# register built separately above, the front page has to be stitched
# together from both builds' summaries afterwards.
python3 "$HERE/scripts/front_page.py" "$HERE/pages/feeds" "$LOG1" "$LOG2"

"$HERE/scripts/deploy-local.sh"
