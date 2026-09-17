# PDP-11 viewer

These files show the published pages on a PDP-11 running RSX-11M-PLUS
with a VT340 console. Tested on a PiDP-11.

| file | purpose |
|---|---|
| `TTXBV.B2S` | the viewer, in BASIC-PLUS-2 |
| `TTXVW.CMD` | starts `TTXBV` and downloads the pages when asked |
| `TTXSIX.CMD` | the older viewer, an Indirect command file |
| `TTXSIX.FTP` | FTP script that downloads the pages |
| `TTXFET.CMD` | downloads the pages, then schedules the next run |
| `TTXFET.BAT` | batch job that runs `TTXFET.CMD` |
| `LOGIN.CMD` | starts `TTXVW` at login and logs out when you quit |

All of them go in `DB0:[203,1]`.

## Using the viewer

```
> @DB0:[203,1]TTXVW
```

The viewer reads `SIDX.DAT`, the page list that `ttx publish` writes
alongside the pages, and shows the first page in it. After each page,
type:

| input | action |
|---|---|
| Return or `N` | next page in the list |
| a page number | show that page |
| `P` | previous page in the list |
| `I` | first page in the list |
| `R` | download all pages again, then start from the first page |
| `Q` or Ctrl-Z | quit |

Nothing in the viewer knows the page numbers: it steps through
whatever the list holds, wrapping round at the end. A page number
that isn't in the list shows `SNF.DAT`, and Return then carries on
with the next page after that number. If there is no page list yet,
`TTXVW` downloads the pages first.

BASIC can't run MCR commands, so `TTXVW.CMD` sets the terminal up
(`SET /BUF=TI:255`) and runs the FTP download. When you type `R`, the
viewer leaves a `TTXREF.TMP` marker and exits; `TTXVW` downloads the
pages, deletes the marker and starts the viewer again.

### Building the viewer

BASIC-PLUS-2 comes from RPM (`@LB:[RPM]RPM FETCH BP2`, then
`RPM INSTALL BP2`). With `TTXBV.B2S` in `DB0:[203,1]`:

```
> BP2
BASIC2
OLD TTXBV
COMPILE
BUILD
EXIT
> TKB @TTXBV
```

## The Indirect viewer

```
> @DB0:[203,1]TTXSIX
```

Page 100 is shown first. After each page, type:

| input | action |
|---|---|
| a page number | show that page |
| `N` / `P` | next / previous page number |
| `I` or just Return | back to page 100 |
| `R` | download all pages again, then show page 100 |
| `Q` or Ctrl-Z | quit |

A page number that isn't held shows `SNF.DAT`. Page 199 lists every
page that has been published. If there are no pages on the disk yet,
the viewer downloads them before showing the first one.

## Where the pages come from

| | |
|---|---|
| FTP login | anonymous |
| FTP directory | `sixel` (`/var/ftp/public/sixel/` on the server) |
| files | `S<page>.DAT`, plus `SNF.DAT` |
| transfer mode | `MODE TEXT` |
| local directory | `DB0:[203,1]` |

The FTP server's address is on the `OPEN` line of `TTXSIX.FTP`. Set it
for your network before installing the file.

`MODE TEXT` matters: in text mode the FTP client turns each line into an
RMS record. A binary transfer stores the whole page as one record that
can't be typed.

The pages are wrapped into lines of at most 132 characters when they are
published (see the main README), which keeps them under RSX's
173-character terminal line limit.

A separate text-only teletext service uses the same FTP server and the
same PDP-11:

| | text service | this service |
|---|---|---|
| FTP directory | `/var/ftp/public/` | `/var/ftp/public/sixel/` |
| RSX directory | `DB0:[201,1]` | `DB0:[203,1]` |
| viewer | `TELETEXT.CMD` | `TTXSIX.CMD` |
| files | `P<n>.DAT` | `S<n>.DAT` |

The file names use a different prefix as well as a different directory,
so an `MGET` run from the wrong directory can't overwrite the other
service's pages.

## Hourly download

The workstation publishes new pages on the hour
(`scripts/refresh.sh`). The PDP-11 downloads them at five past, so it
never fetches while an upload is in progress.

`TTXFET.BAT` runs `TTXFET.CMD`. That downloads the pages, works out the
next hour from the current time and submits the batch job again for
`hh:05`. After 23:00 it submits for `00:05:TOMORROW`. The time is read
from the clock each run, so the schedule doesn't drift.

Start it once:

```
> SUB /AF:hh:05=DB0:[203,1]TTXFET.BAT
```

Check the queue:

```
> QUE BATCH:/LI
  [1,1]     TTXFET    ENTRY:1     BLOCKED UNTIL 15-SEP-26 21:15
            1 DB0:[203,1]TTXFET.BAT;1
```

## Installing

Create the directory and set it as the default:

```
> UFD DB0:[203,1]
> SET DEF DB0:[203,1]
```

If there is no other way to copy files onto the system, type each one in
at the console:

```
> PIP TTXSIX.FTP=TI:
  (paste the file)
  ^Z
```

Do the same for `TTXSIX.CMD`, `TTXFET.CMD` and `TTXFET.BAT`. Then
download the pages and start the viewer:

```
> FTP @DB0:[203,1]TTXSIX.FTP
> @DB0:[203,1]TTXSIX
```

To go straight into the viewer at login, use `LOGIN.CMD` as the login
command file for the account.
