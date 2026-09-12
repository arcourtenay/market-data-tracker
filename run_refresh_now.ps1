$logs = "C:\Users\AdrianCourtenay\OneDrive - Green Ash Partners\GAP-Company - Company\Green Ash Products\GA Special Sits\Systems\Claude\sec-mgmt-tracker\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"C:\Users\AdrianCourtenay\OneDrive - Green Ash Partners\GAP-Company - Company\Green Ash Products\GA Special Sits\Systems\Claude\sec-mgmt-tracker\refresh_data.ps1`"" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$logs\manual_refresh.out.log" `
    -RedirectStandardError "$logs\manual_refresh.err.log"

Write-Host "Started manual production refresh"
