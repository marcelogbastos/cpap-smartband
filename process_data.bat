@echo off
echo ========================================
echo   CPAP-ResMed - Processamento de Dados
echo ========================================
echo.

cd /d "%~dp0"

REM Verifica se o ambiente virtual existe
if not exist "venv" (
    echo [ERRO] Ambiente virtual nao encontrado. Execute start.bat primeiro.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [INFO] Processando dados CPAP...
echo.

python src\ingestion\processor.py %*

echo.
pause
