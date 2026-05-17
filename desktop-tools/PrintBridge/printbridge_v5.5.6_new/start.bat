@echo off
cd /d "%~dp0"
call venv\Scripts\python app.py
if errorlevel 1 (
    echo.
    echo  [ERROR] La aplicacion cerro con un error.
    echo  Revisa los mensajes de arriba.
    pause
)
