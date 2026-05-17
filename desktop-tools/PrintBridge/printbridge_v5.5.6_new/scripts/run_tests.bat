@echo off
REM PrintBridge — Script de ejecución local de tests
REM Mejora 8 del Roadmap Técnico: CI Pipeline
REM
REM Uso:
REM   run_tests.bat              → todos los tests
REM   run_tests.bat fast         → excluye tests lentos (sin slow/network)
REM   run_tests.bat coverage     → con reporte de cobertura HTML
REM   run_tests.bat specific     → pide clase/función específica
REM   run_tests.bat audit        → solo auditoría de dependencias

setlocal EnableDelayedExpansion
cd /d "%~dp0.."

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║           PrintBridge — Test Runner Local               ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

REM Verificar que Python esté disponible
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instalar desde python.org
    exit /b 1
)

REM Verificar que pytest esté instalado
python -m pytest --version >nul 2>&1
if errorlevel 1 (
    echo [AVISO] pytest no encontrado. Instalando dependencias de test...
    pip install pytest pytest-timeout pytest-cov httpx
)

set MODE=%1
if "%MODE%"=="" set MODE=all

if "%MODE%"=="fast" goto :fast
if "%MODE%"=="coverage" goto :coverage
if "%MODE%"=="specific" goto :specific
if "%MODE%"=="audit" goto :audit
if "%MODE%"=="all" goto :all

echo [ERROR] Modo desconocido: %MODE%
echo Opciones: all, fast, coverage, specific, audit
exit /b 1

:all
echo [MODO] Todos los tests (incluye win32_only)
echo.
python -m pytest tests/ -v --tb=short --timeout=30 -q
goto :end

:fast
echo [MODO] Tests rapidos (excluye slow y network)
echo.
python -m pytest tests/ -v --tb=short --timeout=30 -m "not slow and not network" -q
goto :end

:coverage
echo [MODO] Tests con cobertura HTML
echo.
python -m pytest tests/ ^
    -v --tb=short --timeout=30 ^
    --cov=. ^
    --cov-omit="tests/*,web/*,*.bat,scripts/*" ^
    --cov-report=html:htmlcov ^
    --cov-report=term-missing:skip-covered ^
    -q
if not errorlevel 1 (
    echo.
    echo [OK] Reporte HTML generado en: htmlcov\index.html
    start htmlcov\index.html
)
goto :end

:specific
echo [MODO] Test especifico
set /p TEST_FILTER="Ingresa nombre de clase o funcion (ej: TestRateLimitS04): "
echo.
python -m pytest tests/ -v --tb=long --timeout=30 -k "%TEST_FILTER%"
goto :end

:audit
echo [MODO] Auditoria de vulnerabilidades en dependencias
echo.
pip-audit --requirement requirements.txt --format columns --skip-editable
goto :end

:end
echo.
if errorlevel 1 (
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║  [FALLO] Algunos tests fallaron — ver salida arriba     ║
    echo ╚══════════════════════════════════════════════════════════╝
) else (
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║  [OK] Todos los tests pasaron correctamente             ║
    echo ╚══════════════════════════════════════════════════════════╝
)
echo.
exit /b %errorlevel%
