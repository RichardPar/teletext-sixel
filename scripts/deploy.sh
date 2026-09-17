#!/bin/sh
# Publish the pages in pages/feeds as sixel .DAT files and deploy them to
# the FTP directory the PDP-11 fetches from, removing any page that is no
# longer published.
#
#   scripts/deploy.sh               publish and deploy
#   scripts/deploy.sh --dry-run     publish, then show what would change
#
# Settings come from the environment, or from scripts/deploy.conf (not
# kept in the repository, so the host address stays out of it):
#
#   TTX_HOST      user@host of the FTP server, reached over SSH
#   TTX_REMOTE    the FTP directory      (default /var/ftp/public/sixel)
#   TTX_PAGES     pages to publish       (default pages/feeds)
#   TTX_PREFIX    file name prefix       (default S)
#
# The upload goes to a hidden .incoming directory beside the pages and is
# moved into place in a single step at the end, so a fetch that starts
# while this runs never sees half a service - and the viewer's MGET S*.DAT
# does not match anything inside .incoming.
set -e

HERE=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$HERE/scripts/deploy.conf" ] && . "$HERE/scripts/deploy.conf"

REMOTE=${TTX_REMOTE:-/var/ftp/public/sixel}
PAGES=${TTX_PAGES:-$HERE/pages/feeds}
PREFIX=${TTX_PREFIX:-S}
# sixel draws each page as a picture; text sends it as characters in the
# soft font published beside the pages, which is four to fifteen times
# less to shift down a 9600 baud line
EMIT=${TTX_EMIT:-sixel}
STAGE=$HERE/.publish
DRY=
[ "$1" = "--dry-run" ] && DRY=1

if [ -z "$TTX_HOST" ]; then
    echo "deploy: set TTX_HOST (user@host) or put it in scripts/deploy.conf" >&2
    exit 2
fi

# --record 132 keeps every line under the 173 characters at which RSX
# wraps terminal output; a wrap inside a run-length token corrupts the
# picture.  --depth low is a VT340's 16 colour registers.
rm -rf "$STAGE"
"$HERE/ttx" publish "$PAGES" --out "$STAGE" --prefix "$PREFIX" \
    --scale 1.5 --depth low --clear --record 132 --emit "$EMIT" \
    > /dev/null

COUNT=$(ls "$STAGE"/"$PREFIX"*.DAT | wc -l)
if [ "$COUNT" -eq 0 ]; then
    echo "deploy: nothing was published from $PAGES" >&2
    exit 1
fi

SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"

if [ -n "$DRY" ]; then
    echo "would deploy $COUNT pages to $TTX_HOST:$REMOTE"
    $SSH "$TTX_HOST" "cd '$REMOTE' && ls $PREFIX*.DAT 2>/dev/null" |
        tr -d '\r' | while read -r f; do
            [ -f "$STAGE/$f" ] || echo "would remove $f"
        done
    exit 0
fi

$SSH "$TTX_HOST" "mkdir -p '$REMOTE/.incoming' && rm -f '$REMOTE/.incoming/'*"
scp -q -o BatchMode=yes -o ConnectTimeout=15 \
    "$STAGE"/"$PREFIX"*.DAT "$TTX_HOST:$REMOTE/.incoming/"

# one remote command: drop the pages that are not in the new set, then
# move the new set into place
$SSH "$TTX_HOST" "cd '$REMOTE' &&
    for f in $PREFIX*.DAT; do
        [ -e \"\$f\" ] || continue
        [ -e \".incoming/\$f\" ] || { rm -f \"\$f\"; echo \"removed \$f\"; }
    done &&
    chmod a+r .incoming/*.DAT &&
    mv -f .incoming/*.DAT . &&
    rmdir .incoming"

echo "$(date '+%Y-%m-%d %H:%M') deployed $COUNT pages to $TTX_HOST:$REMOTE"
