@echo off
cd /d "%~dp0"
title {{GAME_NAME}} - supervisor
pythonw "%~dp0orchestrator\supervisor.py"
