@echo off
title ESP32 PC Link - Agent
echo ============================================
echo   ESP32 PC Link - PC Agent
echo   Iniciando servidor de control...
echo ============================================
cd /d "%~dp0"
py -3 main.py
pause
