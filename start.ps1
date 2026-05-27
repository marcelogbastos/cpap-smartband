Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CPAP-ResMed - Iniciando Aplicacao" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

# Verifica se o ambiente virtual existe
if (-Not (Test-Path "venv")) {
    Write-Host "[INFO] Criando ambiente virtual..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] Falha ao criar ambiente virtual." -ForegroundColor Red
        Read-Host "Pressione Enter para sair"
        exit 1
    }
    Write-Host "[OK] Ambiente virtual criado." -ForegroundColor Green
    Write-Host ""
}

# Instala dependencias
Write-Host "[INFO] Instalando dependencias..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERRO] Falha ao instalar dependencias." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}
Write-Host "[OK] Dependencias instaladas." -ForegroundColor Green
Write-Host ""

# Inicia o servidor
Write-Host "[INFO] Iniciando servidor em http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host ""
& ".\venv\Scripts\python.exe" -m uvicorn src.visualization.app:app --host 127.0.0.1 --port 8000 --reload
