@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "MODE=%~1"
if not "%MODE%"=="" if /I not "%MODE%"=="/regions" (
  echo ERROR: Unknown argument. Use no argument or /regions.
  exit /b 2
)

set "FAILED=0"
for %%F in (
  "docs\repo-manifest.yaml"
  "docs\file-ownership.yaml"
  "docs\task-file-map.yaml"
  "docs\region-marker-policy.md"
  "docs\spec-registry\scaffold-script-contracts.yaml"
  "docs\spec-registry\task-to-file-contract-map.yaml"
  "scripts\bootstrap.bat"
  "scripts\verify-scaffold.bat"
  ".env.example"
  "README.md"
) do (
  if not exist "%%~F" (
    echo MISSING FILE: %%~F
    set "FAILED=1"
  )
)

for %%D in (
  "apps\api"
  "apps\chat-web"
  "apps\admin-web"
  "apps\mock-his"
  "packages\contracts"
  "supabase"
  "config"
  "tests"
  "prompts"
) do (
  if not exist "%%~D" (
    echo MISSING DIRECTORY: %%~D
    set "FAILED=1"
  )
)

if /I "%MODE%"=="/regions" (
  if not exist "config\region-markers\initialization-map.yaml" (
    echo MISSING REGION INITIALIZATION MAP: config\region-markers\initialization-map.yaml
    set "FAILED=1"
  )
)

if "%FAILED%"=="1" exit /b 1
echo Scaffold verification passed %MODE%.
exit /b 0

