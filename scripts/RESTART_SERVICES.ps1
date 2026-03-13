# Restart Backend and Frontend Only
# Preserves the Scheduler running in background

$ProjectRoot = Get-Location

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "   PNCP SERVICE RESTART (Keep Automation)" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Kill existing services
function Kill-Port ($port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($conns) {
            $pids = $conns.OwningProcess | Select-Object -Unique
            foreach ($pid_val in $pids) {
                # Skip if it's 0 or current process (unlikely for 3000/8000)
                if ($pid_val -gt 0) {
                   Stop-Process -Id $pid_val -Force -ErrorAction SilentlyContinue
                   Write-Host "Killed process on port $port (PID: $pid_val)" -ForegroundColor Red
                }
            }
        }
    } catch {
        Write-Host "No process found on port $port or access denied." -ForegroundColor Gray
    }
}

Write-Host "[1/4] Restarting Backend & Database (Docker)..." -ForegroundColor Yellow
docker-compose -f "$ProjectRoot\infra\compose\docker-compose.yml" restart

Write-Host "[2/4] Stopping Frontend (3000)..."
Kill-Port 3000

Start-Sleep -Seconds 2

# 3. Restart Frontend
Write-Host "[3/4] Restarting Frontend..." -ForegroundColor Yellow
$FrontendCmd = "cd '$ProjectRoot\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "$FrontendCmd" -WindowStyle Normal

# (Removed old step 4)

Write-Host ""
Write-Host "✅ Services Restarted" -ForegroundColor Green
Write-Host "Scheduler is assumed to be running."
