@echo off
title BloomStitch v5.5 — Instalador
color 0B
echo.
echo  ============================================
echo    BloomStitch v5.5  ^|  by BloomScans
echo  ============================================
echo.
echo [1/2] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python no encontrado.
    echo  Instala Python desde https://python.org
    echo  Marca "Add Python to PATH" al instalar.
    pause & exit /b 1
)
python --version
echo  OK

echo.
echo [2/2] Instalando dependencias...
python -m pip install Pillow --upgrade -q
echo  Pillow OK
python -m pip install tkinterdnd2 --upgrade -q
echo  tkinterdnd2 OK (Drag and Drop)
echo.
echo  ============================================
echo   Todo listo.
echo   Ejecuta BloomStitch.bat para iniciar.
echo  ============================================
echo.
pause
