Set WShell  = CreateObject("WScript.Shell")
Set FSO     = CreateObject("Scripting.FileSystemObject")
carpeta     = FSO.GetParentFolderName(WScript.ScriptFullName)

' ── 1. Control de instancia única (via procesos del sistema) ──
Set oWMI   = GetObject("winmgmts:\\.\root\cimv2")
Set oProcs = oWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='wscript.exe'")
Dim nInstancias
nInstancias = 0
For Each oProc In oProcs
    If InStr(LCase(oProc.CommandLine), "pos.vbs") > 0 Then
        nInstancias = nInstancias + 1
    End If
Next
' Si hay mas de 1 wscript corriendo POS.vbs (esta instancia + otra), salir
If nInstancias > 1 Then
    WScript.Quit 0
End If

' ── 2. Verificar entorno virtual ─────────────────────────────
If Not FSO.FileExists(carpeta & "\.venv\Scripts\activate.bat") Then
    MsgBox "No se encontro el entorno virtual .venv" & vbCrLf & _
           "Contacte al administrador del sistema.", vbCritical, "POS — Error"
    WScript.Quit 1
End If

' ── 3. Iniciar servidor Django oculto ────────────────────────
WShell.Run "cmd /c cd /d """ & carpeta & """ && " & _
           "call .venv\Scripts\activate.bat && " & _
           "python manage.py runserver 0.0.0.0:8000", 0, False

WScript.Sleep 6000

' ── 4. Detectar Chrome o Edge ────────────────────────────────
Dim br
br = ""
Dim rutas(3)
rutas(0) = "C:\Program Files\Google\Chrome\Application\chrome.exe"
rutas(1) = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
rutas(2) = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
rutas(3) = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

Dim i
For i = 0 To 3
    If FSO.FileExists(rutas(i)) Then
        br = rutas(i)
        Exit For
    End If
Next

If br = "" Then
    MsgBox "No se encontro Chrome ni Edge instalado." & vbCrLf & _
           "Instale Google Chrome o Microsoft Edge e intente de nuevo.", _
           vbCritical, "POS — Error"
    WShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon ^| findstr ""0.0.0.0:8000 ""') do taskkill /F /PID %a", 0, True
    WScript.Quit 1
End If

' ── 5. Abrir POS (espera hasta que se cierre la ventana) ─────
WShell.Run """" & br & """ " & _
           "--app=http://127.0.0.1:8000 " & _
           "--user-data-dir=""" & carpeta & "\.chrome_pos"" " & _
           "--no-first-run " & _
           "--start-maximized", 3, True

' ── 6. Al cerrar: apagar servidor ────────────────────────────
WShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon ^| findstr ""0.0.0.0:8000 ""') do taskkill /F /PID %a", 0, True
