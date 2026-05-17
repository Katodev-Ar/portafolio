Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 15 Name, @{Name="RAM(MB)";Expression={[math]::Round($_.WorkingSet / 1MB, 2)}} | Format-Table -AutoSize
Write-Host "--- RAM COMMIT ---"
Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory, TotalVirtualMemorySize, FreeVirtualMemory | Format-List
Write-Host "--- WSL ---"
wsl --status 2>&1
