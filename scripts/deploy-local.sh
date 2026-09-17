#!/bin/sh
# Local equivalent of deploy.sh for when the FTP directory is on this same
# machine: render the pages and copy them straight into place instead of
# going over SSH.
#
#   scripts/deploy-local.sh               publish and deploy
#   scripts/deploy-local.sh --dry-run     publish, then show what would change
#
#   TTX_REMOTE    the FTP directory (default /var/ftp/public/sixel)
#   TTX_PAGES     pages to publish  (default pages/feeds)
#   TTX_PREFIX    file name prefix  (default S)
set -e

HERE=$(cd "$(dirname "$0")/.." && pwd)

REMOTE=${TTX_REMOTE:-/var/ftp/public/sixel}
PAGES=${TTX_PAGES:-$HERE/pages/feeds}
PREFIX=${TTX_PREFIX:-S}
STAGE=$HERE/.publish
DRY=
[ "$1" = "--dry-run" ] && DRY=1

rm -rf "$STAGE"
"$HERE/ttx" publish "$PAGES" --out "$STAGE" --prefix "$PREFIX" \
    --scale 1.5 --depth low --clear --record 132 > /dev/null

COUNT=$(ls "$STAGE"/"$PREFIX"*.DAT 2>/dev/null | wc -l)
if [ "$COUNT" -eq 0 ]; then
    echo "deploy-local: nothing was published from $PAGES" >&2
    exit 1
fi

mkdir -p "$REMOTE"

if [ -n "$DRY" ]; then
    echo "would deploy $COUNT pages to $REMOTE"
    for f in "$REMOTE"/"$PREFIX"*.DAT; do
        [ -e "$f" ] || continue
        b=$(basename "$f")
        [ -e "$STAGE/$b" ] || echo "would remove $b"
    done
    exit 0
fi

INCOMING="$REMOTE/.incoming"
rm -rf "$INCOMING"
mkdir -p "$INCOMING"
cp "$STAGE"/"$PREFIX"*.DAT "$INCOMING"/

for f in "$REMOTE"/"$PREFIX"*.DAT; do
    [ -e "$f" ] || continue
    b=$(basename "$f")
    [ -e "$INCOMING/$b" ] || { rm -f "$f"; echo "removed $b"; }
done
chmod a+r "$INCOMING"/*.DAT
mv -f "$INCOMING"/*.DAT "$REMOTE"/
rmdir "$INCOMING"

echo "$(date '+%Y-%m-%d %H:%M') deployed $COUNT pages to $REMOTE"
