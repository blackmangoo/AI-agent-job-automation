Write-Host "Closing all Chrome processes..."
Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Launching Chrome with remote debugging port..."
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222", "--restore-last-session"

Write-Host "Chrome restarted!"
