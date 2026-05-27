@echo off
echo ========================================
echo   CPAP-ResMed - Iniciando Aplicacao
echo ========================================
echo.

cd /d "%~dp0"

REM Verifica se o ambiente virtual existe
if not exist "venv" (
    echo [INFO] Criando ambiente virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar ambiente virtual. Verifique se o Python esta instalado.
        pause
        exit /b 1
    )
    echo [OK] Ambiente virtual criado.
    echo.
)

REM Ativa o ambiente virtual
call venv\Scripts\activate.bat

REM Instala dependencias
echo [INFO] Instalando dependencias...
pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.
echo.

REM Inicia o servidor
echo [INFO] Iniciando servidor em http://127.0.0.1:8000
echo.
python -m uvicorn src.visualization.app:app --host 127.0.0.1 --port 8000 --reload
