' CarLooking — silent background launcher (no console window)
' To auto-start with Windows:
'   1. Press Win+R, type: shell:startup, press Enter
'   2. Copy this .vbs file into that folder
'
' To stop: open Task Manager -> find pythonw.exe -> End Task

Dim WshShell
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Code\CarLooking"
WshShell.Run """C:\Code\CarLooking\.venv\Scripts\pythonw.exe"" webapp.py", 0, False
Set WshShell = Nothing
