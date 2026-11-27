@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist pixi.toml cd ..

rem Run Maker blijft actief in de achtergrond tot de browsersessie stopt.
set "launch=$ErrorActionPreference = 'Stop'; $project = (Get-Location).Path; $LASTEXITCODE = 1;"
set "launch=%launch% $logs = Join-Path $project '.pixi\run-maken-logs';"
set "launch=%launch% $log = Join-Path $logs ('run-maken-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $PID);"
set "launch=%launch% $errorLog = $log + '.error.log'; try {"
set "launch=%launch% New-Item -ItemType Directory -Path $logs -Force | Out-Null;"
set "launch=%launch% $pixi = (Get-Command 'pixi.exe' -CommandType Application -ErrorAction SilentlyContinue).Source; if (-not $pixi) { throw 'Installeer eerst Pixi. Open daarna run-maken.bat opnieuw. Zie Eenmalig installeren in README.md.' };"
set "launch=%launch% Add-Type -AssemblyName System.Windows.Forms; [Windows.Forms.Application]::EnableVisualStyles();"
set "launch=%launch% $form = New-Object Windows.Forms.Form; $form.Text = 'Waterlagen - Runmaker starten'; $form.Icon = New-Object Drawing.Icon((Join-Path $project 'tools/runscript_maken/web/waterlagen.ico')); $form.StartPosition = 'CenterScreen'; $form.FormBorderStyle = 'FixedDialog'; $form.ControlBox = $false; $form.ClientSize = '450,90';"
set "launch=%launch% $label = New-Object Windows.Forms.Label; $label.Location = '20,16'; $label.Size = '420,40'; $form.Controls.Add($label);"
set "launch=%launch% $clock = New-Object Windows.Forms.Label; $clock.Location = '20,60'; $clock.AutoSize = $true; $form.Controls.Add($clock);"
set "launch=%launch% $timer = [Diagnostics.Stopwatch]::StartNew(); $frames = [char[]](0x25D0,0x25D3,0x25D1,0x25D2); $i = 0;"
rem Bereid de lokale omgeving voor voordat de datastorekiezer opent.
set "launch=%launch% $environment = Join-Path $project '.pixi\envs\default';"
set "launch=%launch% if (-not (Test-Path -LiteralPath (Join-Path $environment 'python.exe') -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $environment 'conda-meta\history') -PathType Leaf)) {"
set "launch=%launch% $form.Text = 'Waterlagen - Eerste installatie'; $label.Text = 'Pixi installeert de software voor Waterlagen. Dit kan enkele minuten duren.';"
set "launch=%launch% $bar = New-Object Windows.Forms.ProgressBar; $bar.Location = '20,62'; $bar.Size = '410,12'; $bar.Style = 'Marquee'; $bar.MarqueeAnimationSpeed = 30; $form.Controls.Add($bar); $clock.Visible = $false;"
set "launch=%launch% $form.TopMost = $true; $form.Show(); $form.Activate(); $form.TopMost = $false; [Windows.Forms.Application]::DoEvents();"
set "launch=%launch% $errorLog = $log + '.install.error.log'; $install = Start-Process -FilePath $pixi -ArgumentList 'install','--locked' -WindowStyle Hidden -PassThru -RedirectStandardOutput ($log + '.install.log') -RedirectStandardError $errorLog; $null = $install.Handle;"
set "launch=%launch% while (-not $install.WaitForExit(100)) { [Windows.Forms.Application]::DoEvents() };"
set "launch=%launch% if ($install.ExitCode -ne 0) { throw ('De Waterlagen-omgeving kon niet worden klaargezet (Pixi-foutcode ' + $install.ExitCode + ').') };"
set "launch=%launch% $form.Hide(); $bar.Dispose(); $clock.Visible = $true; $form.Text = 'Waterlagen - Runmaker starten'; };"
set "launch=%launch% $errorLog = $log + '.error.log'; $label.Text = 'Waterlagen laden en de lokale kaartserver starten...';"
set "launch=%launch% $proc = Start-Process -FilePath $pixi -ArgumentList 'run','--locked','python','tools\runscript_maken.py' -WindowStyle Hidden -PassThru -RedirectStandardOutput ($log + '.log') -RedirectStandardError ($log + '.error.log'); $null = $proc.Handle;"
set "launch=%launch% while (-not $proc.HasExited) {"
set "launch=%launch% $lines = @(Get-Content -LiteralPath ($log + '.log') -Tail 8 -ErrorAction SilentlyContinue);"
set "launch=%launch% if ($lines -like 'Run maken: http*') { break };"
set "launch=%launch% if (-not $form.Visible -and $lines -contains 'Waterlagen laden...') { $timer.Restart(); $form.Show() };"
set "launch=%launch% $clock.Text = [string]$frames[$i] + '   ' + [int]$timer.Elapsed.TotalSeconds + ' s'; $i = ($i + 1) -band 3;"
set "launch=%launch% [Windows.Forms.Application]::DoEvents(); $null = $proc.WaitForExit(180); };"
set "launch=%launch% $form.Dispose(); $proc.WaitForExit(); $exitCode = $proc.ExitCode;"
set "launch=%launch% if ($exitCode -ne 0) { throw ('Waterlagen is gestopt met foutcode ' + $exitCode + '.') };"
set "launch=%launch% } catch {"
set "launch=%launch% $message = $_.Exception.Message; if ($form) { $form.Dispose() };"
set "launch=%launch% try { Add-Content -LiteralPath $errorLog -Value $message } catch {};"
set "launch=%launch% $null = (New-Object -ComObject WScript.Shell).Popup(($message + [Environment]::NewLine + 'Logbestand: ' + $errorLog), 0, 'Run maken kon niet starten', 16);"
set "launch=%launch% }"

start "" /min "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -Command "%launch%"
popd
