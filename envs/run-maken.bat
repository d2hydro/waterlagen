@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist pixi.toml cd ..

rem Run Maker blijft actief in de achtergrond tot de browsersessie stopt.
set "launch=$ErrorActionPreference = 'Stop'; $project = (Get-Location).Path; $LASTEXITCODE = 1;"
set "launch=%launch% $logs = Join-Path $project '.pixi\run-maken-logs';"
set "launch=%launch% $log = Join-Path $logs ('run-maken-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $PID);"
set "launch=%launch% try {"
set "launch=%launch% New-Item -ItemType Directory -Path $logs -Force | Out-Null;"
set "launch=%launch% $pixi = (Get-Command 'pixi.exe' -CommandType Application).Source;"
set "launch=%launch% $ErrorActionPreference = 'Continue';"
set "launch=%launch% & $pixi run --locked python 'tools\runscript_maken.py' > ($log + '.log') 2> ($log + '.error.log');"
set "launch=%launch% $exitCode = $LASTEXITCODE; $ErrorActionPreference = 'Stop';"
set "launch=%launch% if ($exitCode -ne 0) { throw ('Waterlagen is gestopt met foutcode ' + $exitCode + '.') };"
set "launch=%launch% } catch {"
set "launch=%launch% $message = $_.Exception.Message;"
set "launch=%launch% try { Add-Content -LiteralPath ($log + '.error.log') -Value $message } catch {};"
set "launch=%launch% $null = (New-Object -ComObject WScript.Shell).Popup(($message + [Environment]::NewLine + 'Logbestand: ' + $log + '.error.log'), 0, 'Run maken kon niet starten', 16);"
set "launch=%launch% }"

start "" /min "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -Command "%launch%"
popd
