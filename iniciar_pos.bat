@echo off
cd /d "%~dp0"
title POS — Iniciando...

REM ── Verificar entorno virtual ─────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo  [ERROR] No se encontro el entorno virtual .venv
    echo  Contacte al administrador del sistema.
    echo.
    pause
    exit /b 1
)

REM ── Activar entorno virtual ───────────────────────────────────
call .venv\Scripts\activate.bat

REM ── Iniciar servidor Django en segundo plano ──────────────────
echo  Iniciando servidor, por favor espere...
start /B "" python manage.py runserver 0.0.0.0:8000

REM ── Esperar arranque (6 seg) ──────────────────────────────────
timeout /t 6 /nobreak >nul

REM ── Detectar Chrome o Edge instalado ─────────────────────────
set "BR="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe"       set "BR=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not defined BR if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "BR=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not defined BR if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe"      set "BR=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if not defined BR if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" set "BR=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

if not defined BR (
    echo.
    echo  [ERROR] No se encontro Chrome ni Edge instalado.
    echo  Instale Google Chrome o Microsoft Edge e intente de nuevo.
    echo.
    pause
    goto :cerrar
)

REM ── Abrir POS en modo app (sin pestanas ni barra de navegacion)
title POS — En ejecucion  (no cerrar esta ventana)
start /WAIT "" "%BR%" ^
    --app=http://127.0.0.1:8000 ^
    --user-data-dir="%~dp0.chrome_pos" ^
    --no-first-run ^
    --start-maximized

REM ── Al cerrar la ventana del POS, apagar el servidor ─────────
:cerrar
title POS — Cerrando...
echo  Cerrando servidor...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr "0.0.0.0:8000 "') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul
