@echo off
setlocal

cd /d "%~dp0"

set ACTION=%1
if "%ACTION%"=="" set ACTION=start

if "%ACTION%"=="start"   goto start
if "%ACTION%"=="stop"    goto stop
if "%ACTION%"=="restart" goto restart
if "%ACTION%"=="build"   goto build
if "%ACTION%"=="logs"    goto logs
if "%ACTION%"=="status"  goto status

echo Uso: docker.bat [start^|stop^|restart^|build^|logs^|status]
exit /b 1

:start
echo [INFO] Iniciando dashboard (Docker)...
docker compose up -d
if errorlevel 1 ( echo [ERRO] Falha ao iniciar. & pause & exit /b 1 )
echo [OK] Rodando em http://localhost:8000
goto end

:stop
echo [INFO] Parando container...
docker compose down
echo [OK] Container parado.
goto end

:restart
echo [INFO] Reiniciando...
docker compose restart
echo [OK] Reiniciado.
goto end

:build
echo [INFO] Rebuilding imagem (pode demorar)...
docker compose up -d --build
if errorlevel 1 ( echo [ERRO] Falha no build. & pause & exit /b 1 )
echo [OK] Build concluido. Rodando em http://localhost:8000
goto end

:logs
docker compose logs -f --tail=100
goto end

:status
docker compose ps
goto end

:end
endlocal
