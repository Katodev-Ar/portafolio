@echo off
REM ============================================================
REM  BalloonClassifier — Instalador automático de dependencias
REM ============================================================

cd /d "%~dp0"
title BalloonClassifier — Instalador

echo.
echo  ============================================================
echo   BalloonClassifier — Instalacion de dependencias
echo  ============================================================
echo.

REM -- Verificar Python --
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no encontrado.
    echo  Instala Python 3.10+ desde https://python.org
    echo  Marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
echo  [OK] Python encontrado:
python --version
echo.

REM -- Actualizar pip --
echo  Actualizando pip...
python -m pip install --upgrade pip --quiet
echo  [OK] pip actualizado.
echo.

REM -- Instalar PyTorch CPU --
echo  [1/3] Instalando PyTorch y Torchvision (CPU)...
echo  (Esto puede tardar varios minutos, ~200 MB)
echo.
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo la instalacion de PyTorch.
    pause
    exit /b 1
)
echo.
echo  [OK] PyTorch instalado.
echo.

REM -- Instalar resto de dependencias --
echo  [2/3] Instalando dependencias de vision e interfaz...
python -m pip install opencv-python Pillow numpy scikit-learn matplotlib PyQt6 PyQt6-Charts
if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)
echo.
echo  [OK] Dependencias instaladas.
echo.

REM -- Verificar todo --
echo  [3/3] Verificando instalacion...
python -c "import torch, torchvision, cv2, PIL, numpy, sklearn, matplotlib; from PyQt6.QtCharts import QChart; print('  [OK] Todas las dependencias verificadas correctamente')"
if errorlevel 1 (
    echo.
    echo  [ERROR] Alguna dependencia no se instalo bien.
    echo  Intenta ejecutar este archivo de nuevo.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo   Instalacion completada con exito.
echo   Ahora puedes usar Iniciar.bat para abrir la aplicacion.
echo  ============================================================
echo.
pause
