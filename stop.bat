@echo off
REM MedicalRAG stopper (ASCII-only)
title MedicalRAG Stop
echo Stopping backend/frontend windows...
taskkill /FI "WINDOWTITLE eq MedicalRAG-Backend*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq MedicalRAG-Frontend*" /T /F >nul 2>nul
echo Stopped.
echo (Infra containers untouched. To stop them: docker compose -f deploy/docker-compose.yml down)
timeout /t 3 >nul
