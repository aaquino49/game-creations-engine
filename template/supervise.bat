@echo off
cd /d "%~dp0"
title {{GAME_NAME}} - supervisor
pythonw orchestrator\supervisor.py
