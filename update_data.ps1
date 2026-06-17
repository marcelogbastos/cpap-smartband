param(
    [switch]$Reset,
    [string]$Patient = "marcelo"
)

$ErrorActionPreference = "Continue"

function Write-Title($text) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step($text) {
    Write-Host "[INFO] $text" -ForegroundColor Yellow
}

function Write-OK($text) {
    Write-Host "[OK] $text" -ForegroundColor Green
}

function Write-Error($text) {
    Write-Host "[ERRO] $text" -ForegroundColor Red
}

Set-Location $PSScriptRoot

# Verifica ambiente virtual
if (-Not (Test-Path "venv")) {
    Write-Step "Criando ambiente virtual..."
    python -m venv venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Falha ao criar venv"; exit 1 }
    Write-OK "Ambiente virtual criado."
}

# Ativa venv
& ".\venv\Scripts\Activate.ps1"

# Instala dependências
Write-Step "Verificando dependencias..."
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt 2>$null
if ($LASTEXITCODE -ne 0) { Write-Error "Falha ao instalar dependencias"; exit 1 }
Write-OK "Dependencias OK"

# ===== CPAP =====
Write-Title "Processando dados CPAP (cartao SD)"

$cpapArgs = @()
if ($Reset) { $cpapArgs += "--reset" }

& ".\venv\Scripts\python.exe" -m src.ingestion.processor @cpapArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha no processamento CPAP"
    exit 1
}
Write-OK "CPAP processado com sucesso"

# ===== Smartband =====
Write-Title "Processando dados Smartband (Xiaomi)"

$bandArgs = @("--patient", $Patient)
& ".\venv\Scripts\python.exe" -m src.ingestion.smartband_processor @bandArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha no processamento Smartband"
    exit 1
}
Write-OK "Smartband processado com sucesso"

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "  Todos os dados atualizados com sucesso!" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host ""
