$backend = "C:\Users\AdrianCourtenay\OneDrive - Green Ash Partners\GAP-Company - Company\Green Ash Products\GA Special Sits\Systems\Claude\sec-mgmt-tracker\backend"
$venvPython = "C:\Users\AdrianCourtenay\.venvs\sec-mgmt-tracker-backend\Scripts\python.exe"
$logs = "C:\Users\AdrianCourtenay\OneDrive - Green Ash Partners\GAP-Company - Company\Green Ash Products\GA Special Sits\Systems\Claude\sec-mgmt-tracker\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$env:DATABASE_URL = "postgresql://market_data_tracker_db_user:1anIDMviY2E2nVqNikNIy0QMnzmrgOgi@dpg-daiq67e7bikc739luetg-a.ohio-postgres.render.com/market_data_tracker_db"
$env:SEC_USER_AGENT = "Green Ash Partners adrian@greenash-partners.com"

Start-Process -FilePath $venvPython `
    -ArgumentList "-u", "-m", "app.ingest", "--days-back", "180" `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$logs\backfill_spac.out.log" `
    -RedirectStandardError "$logs\backfill_spac.err.log"

Write-Host "Started 180-day SPAC/management-change backfill against production"
