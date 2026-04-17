@echo off
echo Checking port 5001...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5001.*LISTENING"') do (
    echo Killing process %%a on port 5001
    taskkill /F /PID %%a
)
echo Starting server...
python run.py
