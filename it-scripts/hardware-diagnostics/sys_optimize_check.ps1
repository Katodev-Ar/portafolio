$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== INFORMACION DEL SISTEMA ===" -ForegroundColor Cyan
# CPU
$cpu = Get-CimInstance Win32_Processor
Write-Host "Procesador: $($cpu.Name)"
Write-Host "Nucleos/Hilos: $($cpu.NumberOfCores) / $($cpu.NumberOfLogicalProcessors)"
Write-Host "Uso actual de CPU: $($cpu.LoadPercentage)%"

# RAM
$ram = Get-CimInstance Win32_OperatingSystem
$totalRam = [math]::Round($ram.TotalVisibleMemorySize / 1MB, 2)
$freeRam = [math]::Round($ram.FreePhysicalMemory / 1MB, 2)
$usedRam = $totalRam - $freeRam
$ramSpeed = (Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Speed -Maximum).Maximum
Write-Host "RAM Total: $totalRam GB"
Write-Host "RAM En Uso: $usedRam GB ($([math]::Round(($usedRam/$totalRam)*100, 1))%)"
Write-Host "Velocidad RAM: $ramSpeed MHz"

# GPU
$gpu = Get-CimInstance Win32_VideoController
Write-Host "GPU 1: $($gpu[0].Name)"
if ($gpu.Count -gt 1) { Write-Host "GPU 2: $($gpu[1].Name)" }

# Motherboard & BIOS
$board = Get-CimInstance Win32_BaseBoard
$bios = Get-CimInstance Win32_BIOS
Write-Host "Placa Madre: $($board.Manufacturer) $($board.Product)"
Write-Host "BIOS Version: $($bios.SMBIOSBIOSVersion) - Fecha: $($bios.ReleaseDate)"

Write-Host "`n=== PLAN DE ENERGIA ===" -ForegroundColor Cyan
$powerPlan = powercfg /getactivescheme
Write-Host "Plan Activo: $powerPlan"

Write-Host "`n=== PROGRAMAS DE INICIO (POSIBLE BLOATWARE) ===" -ForegroundColor Cyan
$startup = Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location
if ($startup) {
    $startup | Format-Table -AutoSize
} else {
    Write-Host "No se encontraron programas de inicio (o faltan permisos)."
}

Write-Host "`n=== TOP 5 PROCESOS QUE CONSUMEN MAS RAM ===" -ForegroundColor Cyan
Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 5 Name, @{Name="RAM(MB)";Expression={[math]::Round($_.WorkingSet / 1MB, 2)}} | Format-Table -AutoSize

Write-Host "`n=== TOP 5 PROCESOS QUE CONSUMEN MAS CPU ===" -ForegroundColor Cyan
Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 Name, @{Name="CPU(s)";Expression={[math]::Round($_.CPU, 2)}} | Format-Table -AutoSize
