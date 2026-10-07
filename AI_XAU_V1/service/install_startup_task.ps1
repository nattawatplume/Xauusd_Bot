$ErrorActionPreference = 'Stop'
$servicePath = Split-Path -Parent $MyInvocation.MyCommand.Path
$bridgeScript = Join-Path $servicePath 'start_ai_bridge.ps1'
$taskName = 'XAU AI Bridge'
$powershellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$bridgeScript`""
$action = New-ScheduledTaskAction -Execute $powershellExe -Argument $arguments -WorkingDirectory $servicePath
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Installed '$taskName' to start after this Windows user logs in and restart after a failure." -ForegroundColor Green
Write-Host 'Log in to the VPS user session, start MT5, and verify the EA and AI bridge before disconnecting.' -ForegroundColor Yellow
