@echo off
cd /d "%~dp0backend"
echo Installing libraries (first time only)...
python -m pip install -q -r requirements.txt
start "" cmd /c "timeout /t 6 >nul & start http://127.0.0.1:5000"
python app.py
pause
