@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "docs\repo-manifest.yaml" (
  echo ERROR: Run from the repository root containing docs\repo-manifest.yaml.
  exit /b 1
)

for %%D in (
  "apps\api\gateway"
  "apps\api\foundation"
  "apps\api\ai\providers"
  "apps\api\ai\orchestrator"
  "apps\api\ai\guardrails"
  "apps\api\ai\rag"
  "apps\api\capabilities\emergency\prefilter"
  "apps\api\capabilities\emergency\protocols"
  "apps\api\logging\conversation"
  "apps\api\logging\audit"
  "apps\chat-web\src\widget"
  "apps\chat-web\src\standalone"
  "apps\chat-web\src\shared"
  "apps\chat-web\src\features"
  "apps\admin-web\src\features"
  "apps\mock-his"
  "packages\contracts"
  "supabase\migrations"
  "supabase\policies"
  "supabase\seed"
  "config\runtime"
  "config\deployment"
  "config\emergency"
  "config\prompts"
  "config\hospital"
  "config\region-markers"
  "tests\contracts"
  "tests\contract"
  "tests\unit"
  "tests\integration"
  "tests\data-validation"
  "tests\e2e"
  "tests\fault"
  "tests\nfr"
  "tests\release"
  "prompts\_shared"
  "prompts\sprint-0\task-packets"
  "prompts\sprint-0\review"
  "prompts\sprint-0\fix"
  "prompts\sprint-0\audit"
  "prompts\sprint-1\task-packets"
  "prompts\sprint-1\review"
  "prompts\sprint-1\fix"
  "prompts\sprint-1\audit"
  "prompts\sprint-2\task-packets"
  "prompts\sprint-2\review"
  "prompts\sprint-2\fix"
  "prompts\sprint-2\audit"
  "prompts\sprint-3\task-packets"
  "prompts\sprint-3\review"
  "prompts\sprint-3\fix"
  "prompts\sprint-3\audit"
) do (
  if not exist "%%~D" mkdir "%%~D"
)

echo Scaffold bootstrap completed without overwriting files.
exit /b 0
