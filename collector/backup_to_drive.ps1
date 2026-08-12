# Off-machine copy of the raw archive, per Russo's 2026-08-11 correction:
# "A private GitHub repository is version history, not a backup."
# Requires one-time setup: `rclone config` -> new remote named "gdrive" (Google
# Drive, scope 2 = drive.file is enough since rclone only touches what it creates).
# Registered as a Windows Scheduled Task (see register_backup_task.ps1) so it runs
# unattended, independent of any Claude Code session or the collector process.
Set-Location C:\Users\benja\Proyectos\bikemi-thesis
$log = "data\backup.log"
"[$(Get-Date -Format o)] backup start" | Out-File -Append -Encoding utf8 $log
rclone sync data\raw gdrive:bikemi-thesis-backup/raw --checksum --log-file=$log --log-level INFO
rclone sync data\static gdrive:bikemi-thesis-backup/static --checksum --log-file=$log --log-level INFO
rclone copy data\metadata.csv gdrive:bikemi-thesis-backup --log-file=$log --log-level INFO
"[$(Get-Date -Format o)] backup done" | Out-File -Append -Encoding utf8 $log
