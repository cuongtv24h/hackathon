@echo off
setlocal EnableExtensions

echo Stopping only terminals started by scripts\start-local.bat...
for %%T in (
  "HospitalAssistant Mock HIS*"
  "HospitalAssistant API*"
  "HospitalAssistant Chat Web*"
  "HospitalAssistant Admin Web*"
) do taskkill /f /fi "WINDOWTITLE eq %%~T" >nul 2>nul

echo Local demo stop request completed.
exit /b 0
