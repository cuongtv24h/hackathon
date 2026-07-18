@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."

if not exist "%ROOT%\.env" (
  echo ERROR: .env is missing. Copy .env.example and configure local values first.
  exit /b 1
)

where py >nul 2>nul || (
  echo ERROR: Python launcher ^(py^) was not found on PATH.
  exit /b 1
)
where npm.cmd >nul 2>nul || (
  echo ERROR: npm was not found on PATH.
  exit /b 1
)

if not exist "%ROOT%\apps\chat-web\node_modules" (
  echo ERROR: Chat Web dependencies are missing. Run npm install in apps\chat-web first.
  exit /b 1
)
if not exist "%ROOT%\apps\admin-web\node_modules" (
  echo ERROR: Admin Web dependencies are missing. Run npm install in apps\admin-web first.
  exit /b 1
)

echo Starting Hospital Assistant local demo in four terminals...
start "HospitalAssistant Mock HIS" /D "%ROOT%" cmd /k "py -m uvicorn apps.mock_his.main:app --host 127.0.0.1 --port 8001"
start "HospitalAssistant API" /D "%ROOT%" cmd /k "py -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload"
start "HospitalAssistant Chat Web" /D "%ROOT%\apps\chat-web" cmd /k "npm.cmd run dev -- --host 127.0.0.1"
start "HospitalAssistant Admin Web" /D "%ROOT%\apps\admin-web" cmd /k "npm.cmd run dev -- --host 127.0.0.1 --port 5174"

echo.
echo Services are starting:
echo   Mock HIS:  http://127.0.0.1:8001/health
echo   API docs:  http://127.0.0.1:8000/api/v1/docs
echo   Chat Web:  http://127.0.0.1:5173
echo   Admin Web: http://127.0.0.1:5174
echo.
echo After the terminals report ready, run scripts\smoke-local.bat.
exit /b 0
