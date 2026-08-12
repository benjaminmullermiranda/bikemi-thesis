# One-time setup: registers backup_to_drive.ps1 as a Windows Scheduled Task,
# running every 6 hours regardless of whether Claude Code or the collector's
# own terminal window is open. Run this once, from an elevated PowerShell,
# AFTER `rclone config` has created the "gdrive" remote (see backup_to_drive.ps1).
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"C:\Users\benja\Proyectos\bikemi-thesis\collector\backup_to_drive.ps1`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 6) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName "BikeMiThesisBackup" -Action $action -Trigger $trigger -Description "Off-machine backup of BikeMi raw archive to Google Drive (Russo's 2026-08-11 correction)" -Force
Write-Host "Registered. Test immediately with: Start-ScheduledTask -TaskName BikeMiThesisBackup"
