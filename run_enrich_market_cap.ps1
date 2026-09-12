$backend = "C:\Users\AdrianCourtenay\OneDrive - Green Ash Partners\GAP-Company - Company\Green Ash Products\GA Special Sits\Systems\Claude\sec-mgmt-tracker\backend"
$venvPython = "C:\Users\AdrianCourtenay\.venvs\sec-mgmt-tracker-backend\Scripts\python.exe"
$logs = "C:\Users\AdrianCourtenay\OneDrive - Green Ash Partners\GAP-Company - Company\Green Ash Products\GA Special Sits\Systems\Claude\sec-mgmt-tracker\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

Start-Process -FilePath $venvPython `
    -ArgumentList "-m", "app.enrich_market_cap" `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$logs\enrich_market_cap.out.log" `
    -RedirectStandardError "$logs\enrich_market_cap.err.log"

Write-Host "Started market cap enrichment"
