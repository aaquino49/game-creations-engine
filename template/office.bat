@echo off
rem The Office: a cute live view of the AI team (optional; read-only). Close this window to close it.
cd /d "%~dp0"
python office\server.py %*
