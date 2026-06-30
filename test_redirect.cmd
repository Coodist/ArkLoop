@echo off
setlocal
set "ps=%TEMP%\test_ps.ps1"
>"%ps%" echo Write-Host 'hello'
>>"%ps%" echo Write-Host 'world'
type "%ps%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ps%"
pause
