$root = "C:\Users\AdrianCourtenay\OneDrive - Green Ash Partners\GAP-Company - Company\Green Ash Products\GA Special Sits\Systems\Claude\sec-mgmt-tracker"
$backend = "$root\backend"
$frontend = "$root\frontend"
$venvPython = "C:\Users\AdrianCourtenay\.venvs\sec-mgmt-tracker-backend\Scripts\python.exe"
$logs = "$root\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$backendListening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $backendListening) {
    Start-Process -FilePath $venvPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" `
        -WorkingDirectory $backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$logs\backend.out.log" `
        -RedirectStandardError "$logs\backend.err.log"
    Write-Host "Started backend"
} else {
    Write-Host "Backend already running"
}

$frontendListening = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if (-not $frontendListening) {
    Start-Process -FilePath "C:\Program Files\nodejs\node.exe" `
        -ArgumentList "`"$frontend\node_modules\next\dist\bin\next`" dev" `
        -WorkingDirectory $frontend `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$logs\frontend.out.log" `
        -RedirectStandardError "$logs\frontend.err.log"
    Write-Host "Started frontend"
} else {
    Write-Host "Frontend already running"
}
