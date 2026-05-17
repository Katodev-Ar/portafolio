@echo off
echo ========================================
echo  BLOOM TRANSLATOR v2 - COMPILADOR
echo ========================================
echo.

echo [1/5] Verificando PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    pip install pyinstaller
)
echo PyInstaller OK.
echo.

echo [2/5] Verificando dependencias...
pip install -r requirements_desktop.txt >nul 2>&1
echo Dependencias OK.
echo.

echo [3/5] Verificando carpeta templates...
if not exist "templates\translator.html" (
    echo ERROR: templates\translator.html no encontrado!
    pause
    exit /b 1
)
echo templates OK.
echo.

echo [4/5] Compilando...
pyinstaller --onefile --windowed ^
  --add-data "templates;templates" ^
  --name "BloomTranslator" ^
  --icon=icon.ico ^
  app_desktop.py 2>nul

REM Si no hay icon.ico, compilar sin icono
if errorlevel 1 (
    echo Intentando sin icono...
    pyinstaller --onefile --windowed ^
      --add-data "templates;templates" ^
      --name "BloomTranslator" ^
      app_desktop.py
)

if errorlevel 1 (
    echo ERROR: Fallo en la compilacion
    pause
    exit /b 1
)
echo.

echo [5/5] Copiando archivos adicionales...
if exist "credentials.json" (
    copy credentials.json dist\credentials.json
    echo credentials.json copiado.
) else (
    echo NOTA: credentials.json no encontrado (necesario para Modo Staff)
)
echo.

echo ========================================
echo  COMPILACION COMPLETADA
echo ========================================
echo.
echo Ejecutable: dist\BloomTranslator.exe
echo.
echo IMPORTANTE: Junto al .exe deben estar:
echo   - credentials.json  (para modo Staff/Drive)
echo   - (El servidor de licencias debe correr en localhost:7777)
echo.
pause
