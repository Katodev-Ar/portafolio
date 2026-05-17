@echo off
cd /d "%~dp0"
echo Directorio actual: %cd%
echo.
echo Verificando archivos...
if exist "venv\Scripts\python.exe" (echo [OK] Python en venv) else (echo [ERROR] No se encuentra venv\Scripts\python.exe)
if exist "app.py" (echo [OK] app.py existe) else (echo [ERROR] app.py no encontrado)
if exist "web\index.html" (echo [OK] web\index.html existe) else (echo [ERROR] web\index.html no encontrado)
echo.
echo Ejecutando app.py y mostrando errores...
echo ==========================================
venv\Scripts\python.exe app.py
echo ==========================================
echo.
echo La app cerro. Codigo de salida: %errorlevel%
pause
