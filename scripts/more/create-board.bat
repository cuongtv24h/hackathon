@echo off
REM Create GitHub Project Board tasks from Task Packets

where py >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python launcher py not found
  exit /b 1
)

py "%~dp0create_board_tasks.py" %*
