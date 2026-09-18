Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
curDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = curDir

Dim pyExe
pyExe = ""

' 1. Check local virtual environments (.venv or venv)
If FSO.FileExists(curDir & "\.venv\Scripts\pythonw.exe") Then
    pyExe = curDir & "\.venv\Scripts\pythonw.exe"
ElseIf FSO.FileExists(curDir & "\venv\Scripts\pythonw.exe") Then
    pyExe = curDir & "\venv\Scripts\pythonw.exe"
End If

' 2. Check %LOCALAPPDATA% Python paths dynamically
If pyExe = "" Then
    localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
    Dim candidates(5)
    candidates(0) = localAppData & "\Python\pythoncore-3.14-64\pythonw.exe"
    candidates(1) = localAppData & "\Python\bin\pythonw.exe"
    candidates(2) = localAppData & "\Programs\Python\Python313\pythonw.exe"
    candidates(3) = localAppData & "\Programs\Python\Python312\pythonw.exe"
    candidates(4) = localAppData & "\Programs\Python\Python311\pythonw.exe"
    candidates(5) = localAppData & "\Programs\Python\Python310\pythonw.exe"
    
    Dim i
    For i = 0 To UBound(candidates)
        If FSO.FileExists(candidates(i)) Then
            pyExe = candidates(i)
            Exit For
        End If
    Next
End If

' 3. Check system PATH via where command
If pyExe = "" Then
    On Error Resume Next
    Set oExec = WshShell.Exec("cmd.exe /c where pythonw.exe")
    If Not oExec Is Nothing Then
        Do While Not oExec.StdOut.AtEndOfStream
            line = Trim(oExec.StdOut.ReadLine())
            If line <> "" And FSO.FileExists(line) And InStr(LCase(line), "windowsapps") = 0 Then
                pyExe = line
                Exit Do
            End If
        Loop
    End If
    On Error GoTo 0
End If

' 4. Fallback to generic "pythonw.exe"
If pyExe = "" Then
    pyExe = "pythonw.exe"
End If

script = Chr(34) & curDir & "\main.py" & Chr(34)
WshShell.Run Chr(34) & pyExe & Chr(34) & " " & script, 0, False
