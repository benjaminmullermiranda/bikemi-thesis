Set-Location C:\Users\benja\Proyectos\bikemi-thesis
while ($true) {
    cmd /c "python collector\poll.py >> data\console.log 2>&1"
    Start-Sleep -Seconds 15
}
