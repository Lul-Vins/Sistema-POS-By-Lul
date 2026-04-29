' ================================================================
'  CLIENTE POS — Abre el POS desde una PC cajero en la red local
'  CONFIGURAR: cambiar IP_SERVIDOR por la IP del PC del dueño
' ================================================================

IP_SERVIDOR = "192.168.1.100"   ' <-- cambiar por la IP real del servidor
PUERTO      = "8000"

Set WShell = CreateObject("WScript.Shell")
Set FSO    = CreateObject("Scripting.FileSystemObject")

URL = "http://" & IP_SERVIDOR & ":" & PUERTO

' Detectar Chrome o Edge
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
           "Instale Google Chrome o Microsoft Edge.", vbCritical, "POS — Error"
    WScript.Quit 1
End If

' Carpeta de perfil dedicada al POS en este equipo
carpeta = WShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\POS_cliente"

' Abrir POS maximizado y en primer plano
WShell.Run """" & br & """ " & _
           "--app=" & URL & " " & _
           "--user-data-dir=""" & carpeta & """ " & _
           "--no-first-run " & _
           "--start-maximized", 3, False
