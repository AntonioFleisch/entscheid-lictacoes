$ports = @(8000, 3000)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) { 
        Write-Host "Killing process on port $port PID $($conn.OwningProcess)"
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue 
    }
}
Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*scheduler.py*" } | ForEach-Object { 
    Write-Host "Killing scheduler PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue 
}
Write-Host "Cleanup complete."
