@echo off
cd /d "%~dp0"
if not exist .venv (
    echo Creating virtual environment...
    py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
echo Starting FloodSense DT API server on http://localhost:8000...
uvicorn backend.main:app --reload --port 8000
pause