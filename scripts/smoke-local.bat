@echo off
setlocal EnableExtensions

set "PS=powershell -NoProfile -ExecutionPolicy Bypass -Command"

%PS% "function Check([string]$Name,[string]$Url) { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 $Url; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { Write-Host ('PASS  ' + $Name + ' ' + $r.StatusCode); return $true }; Write-Host ('FAIL  ' + $Name + ' ' + $r.StatusCode); return $false } catch { Write-Host ('FAIL  ' + $Name + ' unavailable'); return $false } }; $ok=(Check 'Mock HIS' 'http://127.0.0.1:8001/health') -and (Check 'API docs' 'http://127.0.0.1:8000/api/v1/docs') -and (Check 'Chat Web' 'http://127.0.0.1:5173') -and (Check 'Admin Web' 'http://127.0.0.1:5174'); if (-not $ok) { exit 1 }"
exit /b %ERRORLEVEL%
