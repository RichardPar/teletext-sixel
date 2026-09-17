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

If the pages were published as text (`TTX_EMIT=text`), `SFNT.DAT` comes
down with them and the viewer sends it to the terminal once at startup,
before the first page; after that each page is a couple of kilobytes
rather than ten. With sixel pages there is no `SFNT.DAT` and the viewer
skips that step.

BASIC can't run MCR commands, so `TTXVW.CMD` sets the terminal up
(`SET /BUF=TI:255`) and runs the FTP download. When you type `R`, the
viewer leaves a `TTXREF.TMP` marker and exits; `TTXVW` downloads the
pages, deletes the marker and starts the viewer again.

### Building the viewer

You need BASIC-PLUS-2, which comes from RPM (see [Languages on this
system](#languages-on-this-system)). `TAS` lists `...BP2` when it is
installed.

First get `TTXBV.B2S` into `DB0:[203,1]` and make that the default
directory, so that every file the build writes lands beside it:

```
> SET DEF DB0:[203,1]
> FTP
FTP>OPEN <server>/USER=anonymous/PASSWORD=anonymous
FTP>MODE TEXT
FTP>GET TTXBV.B2S
FTP>QUIT
```

`MODE TEXT` matters here as much as it does for the pages: the compiler
reads the source as records, and a binary transfer gives it one long
one. Then compile and link:

```
> BP2
PDP-11 BASIC-PLUS-2 V2.7-D

BASIC2
OLD TTXBV            ! read TTXBV.B2S into the environment
BASIC2
COMPILE              ! syntax check; silence means it compiled
BASIC2
BUILD                ! write TTXBV.OBJ, TTXBV.CMD and TTXBV.ODL
BASIC2
EXIT
> TKB @TTXBV         ! link TTXBV.OBJ into TTXBV.TSK
> RUN TTXBV          ! or @TTXVW, which sets the terminal up first
```

`COMPILE` prints nothing when the program is good. An error names the
line and points at the word it stopped on:

```
Error on line 70

        70      NOMARGIN #0%
................1

?1:        found keyword NOMARGIN when expecting a valid statement
```

Fix it in the editor, fetch the file again and start from `OLD`. To
patch a line without leaving BASIC, type the line number and the new
text (`70 MARGIN #0%, 255%`), or the number alone to delete the line,
then `COMPILE` again and `REPLACE` to write the source back.

`BUILD` writes the Task Builder command file, so `TKB @TTXBV` needs no
arguments. The build leaves five files behind; each run adds a version,
so purge the old ones now and then:

```
> PIP TTXBV.*/PU
```

| file | |
|---|---|
| `TTXBV.B2S` | the source |
| `TTXBV.OBJ` | compiler output |
| `TTXBV.CMD` | Task Builder command file, from `BUILD` |
| `TTXBV.ODL` | overlay description, from `BUILD` |
| `TTXBV.TSK` | the program `TTXVW` runs |

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
| files | `S<page>.DAT`, plus `SNF.DAT`, `SIDX.DAT` and, for text pages, `SFNT.DAT` |
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
| viewer | `TELETEXT.CMD` | `TTXVW` (`TTXBV.TSK`) |
| files | `P<n>.DAT` | `S<n>.DAT` |

The file names use a different prefix as well as a different directory,
so an `MGET` run from the wrong directory can't overwrite the other
service's pages.

## Hourly download

The workstation publishes new pages on the hour
(`scripts/refresh.sh`). The PDP-11 downloads them at five past, so it
never fetches while an upload is in progress.

`TTXFET.BAT` runs `TTXFET.CMD`. That downloads the pages, purges the
versions the download replaced, works out the next hour from the current
time and submits the batch job again for `hh:05`. After 23:00 it submits
for `00:05:TOMORROW`. The time is read from the clock each run, so the
schedule doesn't drift.

The hours carry decimal points (`.SETN H 'HH'.`, `.IF H GT 23.`) because
Indirect reads and writes numbers in octal otherwise: `18` is then a
syntax error, which leaves nothing scheduled at all, and `17+1` comes
back as `20`, an hour late.

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

If the pages stop arriving, look there first: no entry means nothing is
scheduled, and a wrong time means the hour was miscalculated. Drop the
bad entry by its number and submit a new one:

```
> QUE /EN:1/DEL
> SUB /AF:hh:05=DB0:[203,1]TTXFET.BAT
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

Do the same for `TTXVW.CMD`, `TTXBV.B2S`, `TTXFET.CMD` and `TTXFET.BAT`
(`TTXSIX.CMD` too, for the older viewer). Anything that can write a file
will do instead; the pages themselves arrive by FTP, so fetching the
sources the same way is easier than typing them:

```
> FTP
FTP>OPEN <server>/USER=anonymous/PASSWORD=anonymous
FTP>MODE TEXT
FTP>GET TTXBV.B2S
```

Build the viewer as above, then download the pages and start it:

```
> FTP @DB0:[203,1]TTXSIX.FTP
> @DB0:[203,1]TTXVW
```

To go straight into the viewer at login, use `LOGIN.CMD` as the login
command file for the account. It holds:

```
@DB0:[203,1]TTXVW
BYE
```

so quitting the viewer logs the terminal out.

## Languages on this system

The stock RSX-11M-PLUS disk has no compilers. They come from Johnny
Billquist's package manager, which is already installed in `LB:[RPM]`:

```
> @LB:[RPM]RPM LIST              ! what is available
> @LB:[RPM]RPM FETCH BP2         ! one package per FETCH
> @LB:[RPM]RPM INSTALL BP2       ! pulls in BP2RTL as well
> @LB:[RPM]RPM STATUS            ! what is installed
```

`STARTUP.CMD` runs `@RPM$DIR:RPM BOOT`, so installed packages are
re-installed as tasks at every boot. `RPM CONFIG` holds the repository
address and, in `$RPM`, the directory packages are downloaded into -
that has to be a mounted disk.

This system has BASIC-PLUS-2 V2.7D (`BP2`), Oregon Pascal-2 (`PAS`) and
the DECUS C compiler (`CCC`).
