@echo off
REM MedicalRAG launcher (ASCII-only: cmd parses .bat in ANSI codepage)
title MedicalRAG Launcher
cd /d "%~dp0"

REM ---- locate uv ----
set "UV_CMD=uv"
where uv >nul 2>nul
if errorlevel 1 (
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
    ) else (
        echo [ERROR] uv not found. Install it from https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
)

REM ---- 1/4 docker engine (start Docker Desktop if needed) ----
echo [1/4] Checking Docker engine...
docker info >nul 2>nul
if errorlevel 1 (
    if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        echo       Docker Desktop not running, starting it...
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    ) else (
        echo [ERROR] Docker Desktop not installed.
        pause
        exit /b 1
    )
    set /a WAITED=0
:waitdocker
    docker info >nul 2>nul
    if not errorlevel 1 goto dockerready
    timeout /t 5 /nobreak >nul
    set /a WAITED+=5
    if %WAITED% LSS 120 goto waitdocker
    echo [WARN] Docker engine not ready in 120s, skip infra.
    goto services
)
:dockerready

REM ---- 2/4 infra containers (expect 5) ----
set RUNNING=0
for /f %%i in ('docker compose -f deploy/docker-compose.yml ps --status running -q 2^>nul') do set /a RUNNING+=1
echo [2/4] Infra containers running: %RUNNING%/5
if %RUNNING% LSS 5 (
    echo       Starting missing containers, first pull may take minutes...
    docker compose -f deploy/docker-compose.yml up -d
)

:services
REM ---- 3/4 backend API on 8100 (8000 is occupied on this machine) ----
echo [3/4] Starting backend API on port 8100 ...
start "MedicalRAG-Backend" cmd /k "cd /d ""%~dp0backend"" && %UV_CMD% run uvicorn app.main:app --port 8100"

REM ---- 4/4 frontend on 5180, proxied to 8100 ----
echo [4/4] Starting frontend on port 5180 ...
start "MedicalRAG-Frontend" cmd /k "cd /d ""%~dp0frontend"" && set API_TARGET=http://127.0.0.1:8100&& npm run dev -- --port 5180 --strictPort"

echo.
echo Services starting. Browser opens in 15 seconds...
timeout /t 15 /nobreak >nul
start http://localhost:5180
echo.
echo Done: http://localhost:5180
echo Stop: close the two service windows, or run stop.bat
timeout /t 8 >nul
