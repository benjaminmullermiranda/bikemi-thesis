# One-time setup: registers backup_to_drive.ps1 as a Windows Scheduled Task,
# running every 6 hours regardless of whether Claude Code or the collector's
# own terminal window is open. Run this once, from an elevated PowerShell,
# AFTER `rclone config` has created the "gdrive" remote (see backup_to_drive.ps1).
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"C:\Users\benja\Proyectos\bikemi-thesis\collector\backup_to_drive.ps1`""
# RepetitionDuration ([TimeSpan]::MaxValue) fails to serialize to Task Scheduler's XML
# duration format (HRESULT 0x80041318) - 10 years is effectively indefinite and valid.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 6) -RepetitionDuration (New-TimeSpan -Days 3650)
# DisallowStartIfOnBatteries defaults to $true - on a laptop that runs on battery most
# mornings (docs/collection_status.txt), that silently skips the whole day's backup
# whenever nobody happens to plug in and unlock before the next trigger. A robocopy
# + rclone sync is light enough to run unplugged, so battery state shouldn't gate it.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "BikeMiThesisBackup" -Action $action -Trigger $trigger -Settings $settings -Description "Off-machine backup of BikeMi raw archive to Google Drive (Russo's 2026-08-11 correction)" -Force
Write-Host "Registered. Test immediately with: Start-ScheduledTask -TaskName BikeMiThesisBackup"
