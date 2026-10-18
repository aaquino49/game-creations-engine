@echo off
cd /d "%~dp0"
if exist project\STOP del project\STOP
title {{GAME_NAME}} - AI team orchestrator
echo Starting the {{GAME_NAME}} AI team. Live status: project\STATUS.md
echo To stop: create an empty file project\STOP (stops after the current step) or close this window.
:run
python orchestrator\orchestrator.py %*
if errorlevel 75 if not errorlevel 76 (
  echo Reloading the orchestrator...
  goto run
)
if errorlevel 1 if not exist project\STOP (
  echo The orchestrator stopped unexpectedly. Restarting in 60 seconds - close this window to cancel.
  timeout /t 60 /nobreak >nul
  goto run
)
pause
