@echo off
cd /d "%~dp0"
REM Usa pythonw para abrir SIN ventana de consola
start "" pythonw bloomstitch.py 2>nul
if %errorlevel% neq 0 (
    REM Fallback: python normal (puede aparecer consola brevemente)
    start "" python bloomstitch.py
)
