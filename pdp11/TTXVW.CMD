.ENABLE QUIET
.ENABLE SUBSTITUTION
.; Start the BASIC-PLUS-2 teletext viewer, TTXBV.TSK.
.; BASIC cannot run MCR commands, so this sets the terminal up, fetches
.; the pages when there are none, and fetches them again whenever the
.; viewer exits after R (it leaves TTXREF.TMP behind to ask for that).
SET DEF DB0:[203,1]
SET /BUF=TI:255
SET /TTSYNC=TI:
.TESTFILE SIDX.DAT
.IF <FILERR> = 1 .GOTO VIEW
.DISABLE QUIET
FTP @DB0:[203,1]TTXSIX.FTP
.ENABLE QUIET
.VIEW:
.TESTFILE TTXREF.TMP
.IF <FILERR> = 1 PIP TTXREF.TMP;*/DE
RUN DB0:[203,1]TTXBV
.TESTFILE TTXREF.TMP
.IF <FILERR> <> 1 .GOTO DONE
PIP TTXREF.TMP;*/DE
.DISABLE QUIET
FTP @DB0:[203,1]TTXSIX.FTP
.ENABLE QUIET
.GOTO VIEW
.DONE:
.DISABLE QUIET
