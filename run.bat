@echo off
set DIR=%~dp0
cd /d "%DIR%"

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

python run.py
pause
