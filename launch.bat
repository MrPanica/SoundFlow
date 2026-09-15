@echo off
title SoundFlow Studio
cd /d "%~dp0"
python run.py
if errorlevel 1 (
    echo.
    echo SoundFlow Studio crashed or exited with error.
    pause
)
