@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SCRIPT=%~dp0clipboard_manager.py"
set "CMD_FILE=%USERPROFILE%\.clipboard_manager\command.txt"
set "PID_FILE=%USERPROFILE%\.clipboard_manager\app.pid"
set "WORKDIR=%~dp0"

where pythonw >nul 2>&1 && set "PY=pythonw" || set "PY="
if not defined PY (
  where python >nul 2>&1 && set "PY=python" || set "PY="
)
if not defined PY (
  echo Python not found. Install Python 3 and add it to PATH.
  exit /b 1
)

if "%~1"=="" goto :help
if /i "%~1"=="help" goto :help
if /i "%~1"=="/?" goto :help
if /i "%~1"=="-h" goto :help
if /i "%~1"=="--help" goto :help
if /i "%~1"=="start" goto :do_start
if /i "%~1"=="on" goto :do_start
if /i "%~1"=="run" goto :do_start
if /i "%~1"=="stop" goto :do_stop
if /i "%~1"=="off" goto :do_stop
if /i "%~1"=="quit" goto :do_stop
if /i "%~1"=="exit" goto :do_stop
if /i "%~1"=="kill" goto :do_stop
if /i "%~1"=="open" goto :do_open
if /i "%~1"=="show" goto :do_open
if /i "%~1"=="close" goto :do_close
if /i "%~1"=="hide" goto :do_close
if /i "%~1"=="toggle" goto :do_toggle
if /i "%~1"=="restart" goto :do_restart
if /i "%~1"=="status" goto :do_status

echo Unknown command: %~1
echo.
goto :help

:help
echo.
echo Clipboard Manager commands
echo.
echo   clipboard start     Start the app in the background
echo   clipboard stop      Quit the app completely
echo   clipboard open      Open the popup window
echo   clipboard close     Close / hide the popup window
echo   clipboard toggle    Toggle the popup window
echo   clipboard restart   Stop then start again
echo   clipboard status    Show if the app is running
echo   clipboard help      Show this help
echo.
echo Aliases:
echo   start: on, run
echo   stop:  off, quit, exit, kill
echo   open:  show
echo   close: hide
echo.
exit /b 0

:do_start
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$script=$env:SCRIPT; $py=$env:PY; $wd=$env:WORKDIR; $pidFile=$env:PID_FILE;" ^
  "function Running { " ^
  "  if (Test-Path -LiteralPath $pidFile) { $p=Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue; if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { return $true } };" ^
  "  return [bool](Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like '*clipboard_manager.py*' -and $_.Name -match 'python' })" ^
  "};" ^
  "if (Running) { Write-Host 'Already running.'; exit 0 };" ^
  "$dir=Split-Path -Parent $pidFile; if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null };" ^
  "Start-Process -FilePath $py -ArgumentList ('\"'+$script+'\"') -WorkingDirectory $wd -WindowStyle Hidden;" ^
  "Start-Sleep -Milliseconds 800;" ^
  "if (Running) { Write-Host 'Clipboard manager started.'; exit 0 };" ^
  "Write-Host 'Failed to start. Try: python clipboard_manager.py'; exit 1"
exit /b %ERRORLEVEL%

:do_stop
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cmdFile=$env:CMD_FILE; $pidFile=$env:PID_FILE;" ^
  "function GetProcs { @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like '*clipboard_manager.py*' -and $_.Name -match 'python' }) };" ^
  "$procs=GetProcs;" ^
  "if (-not $procs -or $procs.Count -eq 0) { Write-Host 'Not running.'; if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }; if (Test-Path $cmdFile) { Remove-Item $cmdFile -Force -ErrorAction SilentlyContinue }; exit 0 };" ^
  "$dir=Split-Path -Parent $cmdFile; if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null };" ^
  "Set-Content -LiteralPath $cmdFile -Value 'quit' -Encoding ascii;" ^
  "Start-Sleep -Milliseconds 900;" ^
  "$procs=GetProcs;" ^
  "if ($procs) { $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } };" ^
  "if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue };" ^
  "if (Test-Path $cmdFile) { Remove-Item $cmdFile -Force -ErrorAction SilentlyContinue };" ^
  "Write-Host 'Clipboard manager stopped.'"
exit /b 0

:do_open
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$script=$env:SCRIPT; $py=$env:PY; $wd=$env:WORKDIR; $cmdFile=$env:CMD_FILE; $pidFile=$env:PID_FILE;" ^
  "function Running { " ^
  "  if (Test-Path -LiteralPath $pidFile) { $p=Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue; if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { return $true } };" ^
  "  return [bool](Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like '*clipboard_manager.py*' -and $_.Name -match 'python' })" ^
  "};" ^
  "if (-not (Running)) {" ^
  "  Write-Host 'Not running. Starting...';" ^
  "  $dir=Split-Path -Parent $pidFile; if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null };" ^
  "  Start-Process -FilePath $py -ArgumentList ('\"'+$script+'\"') -WorkingDirectory $wd -WindowStyle Hidden;" ^
  "  Start-Sleep -Milliseconds 1000;" ^
  "  if (-not (Running)) { Write-Host 'Failed to start.'; exit 1 }" ^
  "};" ^
  "$dir=Split-Path -Parent $cmdFile; if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null };" ^
  "Set-Content -LiteralPath $cmdFile -Value 'open' -Encoding ascii;" ^
  "Write-Host 'Popup opened.'"
exit /b %ERRORLEVEL%

:do_close
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cmdFile=$env:CMD_FILE; $pidFile=$env:PID_FILE;" ^
  "function Running { " ^
  "  if (Test-Path -LiteralPath $pidFile) { $p=Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue; if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { return $true } };" ^
  "  return [bool](Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like '*clipboard_manager.py*' -and $_.Name -match 'python' })" ^
  "};" ^
  "if (-not (Running)) { Write-Host 'Not running.'; exit 0 };" ^
  "$dir=Split-Path -Parent $cmdFile; if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null };" ^
  "Set-Content -LiteralPath $cmdFile -Value 'close' -Encoding ascii;" ^
  "Write-Host 'Popup closed.'"
exit /b 0

:do_toggle
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$script=$env:SCRIPT; $py=$env:PY; $wd=$env:WORKDIR; $cmdFile=$env:CMD_FILE; $pidFile=$env:PID_FILE;" ^
  "function Running { " ^
  "  if (Test-Path -LiteralPath $pidFile) { $p=Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue; if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { return $true } };" ^
  "  return [bool](Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like '*clipboard_manager.py*' -and $_.Name -match 'python' })" ^
  "};" ^
  "if (-not (Running)) {" ^
  "  Write-Host 'Not running. Starting...';" ^
  "  $dir=Split-Path -Parent $pidFile; if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null };" ^
  "  Start-Process -FilePath $py -ArgumentList ('\"'+$script+'\"') -WorkingDirectory $wd -WindowStyle Hidden;" ^
  "  Start-Sleep -Milliseconds 1000;" ^
  "  if (-not (Running)) { Write-Host 'Failed to start.'; exit 1 };" ^
  "  Set-Content -LiteralPath $cmdFile -Value 'open' -Encoding ascii;" ^
  "  Write-Host 'Popup opened.'; exit 0" ^
  "};" ^
  "Set-Content -LiteralPath $cmdFile -Value 'toggle' -Encoding ascii;" ^
  "Write-Host 'Popup toggled.'"
exit /b %ERRORLEVEL%

:do_restart
call "%~f0" stop
ping -n 2 127.0.0.1 >nul
call "%~f0" start
exit /b %ERRORLEVEL%

:do_status
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pidFile=$env:PID_FILE;" ^
  "if (Test-Path -LiteralPath $pidFile) { $p=(Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1); if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { Write-Host ('Running (PID ' + $p + ')'); exit 0 } };" ^
  "$procs=@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like '*clipboard_manager.py*' -and $_.Name -match 'python' });" ^
  "if ($procs.Count -gt 0) { Write-Host ('Running (PID ' + (($procs | ForEach-Object ProcessId) -join ', ') + ')'); exit 0 };" ^
  "Write-Host 'Not running.'; exit 1"
exit /b %ERRORLEVEL%
