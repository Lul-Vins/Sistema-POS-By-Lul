Set WShell  = CreateObject("WScript.Shell")
Set FSO     = CreateObject("Scripting.FileSystemObject")
carpeta     = FSO.GetParentFolderName(WScript.ScriptFullName)

' ── 1. Verificar entorno virtual ─────────────────────────────
If Not FSO.FileExists(carpeta & "\.venv\Scripts\activate.bat") Then
    MsgBox "No se encontro el entorno virtual .venv" & vbCrLf & _
           "Contacte al administrador del sistema.", vbCritical, "POS — Error"
    WScript.Quit 1
End If

' ── 2. Iniciar servidor Django oculto ────────────────────────
WShell.Run "cmd /c cd /d """ & carpeta & """ && " & _
           "call .venv\Scripts\activate.bat && " & _
           "python manage.py runserver 0.0.0.0:8000", 0, False

' ── 3. Esperar arranque del servidor (6 seg) ─────────────────
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

' ── 5. Abrir POS maximizado y en primer plano ────────────────
'   Segundo param: 3 = SW_SHOWMAXIMIZED (maximizado + al frente)
'   Tercer param:  True = esperar a que se cierre la ventana
WShell.Run """" & br & """ " & _
           "--app=http://127.0.0.1:8000 " & _
           "--user-data-dir=""" & carpeta & "\.chrome_pos"" " & _
           "--no-first-run " & _
           "--start-maximized", 3, True

' ── 6. Al cerrar el POS, apagar el servidor ──────────────────
WShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon ^| findstr ""0.0.0.0:8000 ""') do taskkill /F /PID %a", 0, True
