' Runs a .bat file without showing a console window (used by scheduled tasks).
CreateObject("WScript.Shell").Run """" & WScript.Arguments(0) & """", 0, True
