@echo off
echo ========================================
echo   Actualizando POS Sinag...
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Descargando actualizacion...
copy db.sqlite3 db.sqlite3.bak >nul 2>&1
git fetch origin main
git reset --hard origin/main
if exist db.sqlite3.bak (
    if not exist db.sqlite3 copy db.sqlite3.bak db.sqlite3 >nul
    del db.sqlite3.bak >nul 2>&1
)
if %errorlevel% neq 0 (
    echo ERROR: No se pudo descargar la actualizacion.
    echo Verifica la conexion a internet.
    pause
    exit /b 1
)

echo.
echo [2/3] Aplicando cambios en base de datos...
call .venv\Scripts\activate.bat
python manage.py migrate --no-input
if %errorlevel% neq 0 (
    echo ERROR: Fallo al actualizar la base de datos.
    pause
    exit /b 1
)

echo.
echo [3/3] Listo!
echo ========================================
echo   Actualizacion completada con exito.
echo   Reinicia el POS para aplicar cambios.
echo ========================================
echo.
pause
