@echo off
title CarLooking
cd /d %~dp0
echo Starting CarLooking...
.venv\Scripts\python.exe webapp.py
pause
