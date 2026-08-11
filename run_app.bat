@echo off
REM Launcher for Campaign Link Hub (Windows)
cd /d "%~dp0"

REM Activate venv if present
if exist "venv\Scripts\activate.bat" (
  call "venv\Scripts\activate.bat"
) else (
  echo Warning: virtual environment not found at %~dp0venv\
)

nREM Ensure we run from project directory
set FLASK_APP=app.py

nREM Run the app (uses app.py entrypoint)
python app.py

necho Server stopped. Press any key to close...
pause > nul
