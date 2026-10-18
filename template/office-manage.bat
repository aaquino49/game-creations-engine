@echo off
rem The Office with manage mode: controls, owner requests and health tools (token-protected). Close this window to close it.
cd /d "%~dp0"
python office\server.py --manage %*
