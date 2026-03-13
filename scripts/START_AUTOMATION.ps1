# Start Lifecycle Script for PNCP Automation

# Ensure we're in the right directory
$ProjectRoot = Get-Location
if (Test-Path "$ProjectRoot\.venv\Scripts\python.exe") {
    $PythonExe = "$ProjectRoot\.venv\Scripts\python.exe"
    Write-Host "Using Virtual Environment Python: $PythonExe" -ForegroundColor Green
} else {
    $PythonExe = (Get-Command python).Source
    Write-Host "Using System Python: $PythonExe" -ForegroundColor Yellow
}

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "   PNCP AUTOMATION STARTUP SEQUENCE" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Start Backend & Database (Docker)
Write-Host "[1/3] Starting Backend & Database (Docker)..." -ForegroundColor Yellow
$DockerCmd = "docker-compose -f ""$ProjectRoot\infra\compose\docker-compose.yml"" up -d"
Write-Host "Executing: $DockerCmd" -ForegroundColor Gray
Invoke-Expression $DockerCmd

# 2. Wait for backend to be ready
Write-Host "Waiting 10 seconds for backend to initialize..."
Start-Sleep -Seconds 10

# 3. Start Frontend
Write-Host "[2/3] Starting Frontend (Next.js)..." -ForegroundColor Yellow
$FrontendCmd = "cd '$ProjectRoot\frontend'; npm run dev"
Write-Host "Executing: $FrontendCmd" -ForegroundColor Gray
Start-Process powershell -ArgumentList "-NoExit", "-Command", "$FrontendCmd" -WindowStyle Normal

# 4. Start Scheduler
Write-Host "[3/3] Starting PNCP Scheduler (1h interval)..." -ForegroundColor Yellow
$SchedulerCmd = "cd '$ProjectRoot'; & '$PythonExe' execution/scheduler.py"
Write-Host "Executing: $SchedulerCmd" -ForegroundColor Gray
Start-Process powershell -ArgumentList "-NoExit", "-Command", "$SchedulerCmd" -WindowStyle Normal

Write-Host ""
Write-Host "✅ ALL SYSTEMS ORCHESTRATED" -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:3000/licitacoes" -ForegroundColor Gray
Write-Host "Backend:  http://127.0.0.1:8000/docs" -ForegroundColor Gray
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "The scheduler will perform an IMMEDIATE collection run once the backend is ready."
