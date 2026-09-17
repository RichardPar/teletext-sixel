.ENABLE QUIET
.ENABLE SUBSTITUTION
SET DEF DB0:[203,1]
FTP @DB0:[203,1]TTXSIX.FTP
.; each download writes a new version of every page; the old ones are
.; last hour's news, so keep only the newest
PIP DB0:[203,1]S*.DAT;*/PU
.; the hour, as a decimal number.  Indirect reads and writes numbers
.; in octal unless they carry a decimal point, so without the dots 18
.; is a syntax error and 17+1 comes back as 20.
.SETS T <TIME>
.SETS HH T[1:2]
.SETN H 'HH'.
.SETN H H+1
.SETS WHEN ""
.IF H GT 23. .SETN H 0
.IF H = 0 .SETS WHEN ":TOMORROW"
.SETS NH "'H'"
.IF H LT 10. .SETS NH "0'H'"
SUB /AF:'NH':05'WHEN'=DB0:[203,1]TTXFET.BAT
