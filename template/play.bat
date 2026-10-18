@echo off
cd /d "%~dp0"
if exist builds\{{EXE_NAME}}.exe (start "" builds\{{EXE_NAME}}.exe) else (godot --path game)
