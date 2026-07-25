@echo off
cd /d C:\Users\benja\Proyectos\bikemi-thesis
:loop
python collector\poll.py >> data\console.log 2>&1
timeout /t 15 /nobreak >nul
goto loop
