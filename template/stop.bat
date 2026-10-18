@echo off
cd /d "%~dp0"
type nul > project\STOP
echo Stop requested. The team will stop after the current step finishes.
pause
