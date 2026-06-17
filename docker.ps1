param(
    [ValidateSet("start","stop","restart","build","logs","status")]
    [string]$Action = "start"
)

Set-Location $PSScriptRoot

switch ($Action) {
    "start" {
        Write-Host "[INFO] Iniciando dashboard (Docker)..." -ForegroundColor Yellow
        docker compose up -d
        if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Falha ao iniciar." -ForegroundColor Red; exit 1 }
        Write-Host "[OK] Rodando em http://localhost:8000" -ForegroundColor Green
    }
    "stop" {
        Write-Host "[INFO] Parando container..." -ForegroundColor Yellow
        docker compose down
        Write-Host "[OK] Container parado." -ForegroundColor Green
    }
    "restart" {
        Write-Host "[INFO] Reiniciando..." -ForegroundColor Yellow
        docker compose restart
        Write-Host "[OK] Reiniciado." -ForegroundColor Green
    }
    "build" {
        Write-Host "[INFO] Rebuilding imagem (pode demorar)..." -ForegroundColor Yellow
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Falha no build." -ForegroundColor Red; exit 1 }
        Write-Host "[OK] Build concluido. Rodando em http://localhost:8000" -ForegroundColor Green
    }
    "logs" {
        docker compose logs -f --tail=100
    }
    "status" {
        docker compose ps
    }
}
