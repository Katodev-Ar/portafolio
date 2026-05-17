# FIX: Remove NVMe as system disk, then clean it

Write-Host "=== PASO 1: Verificando entradas de firmware UEFI ===" -ForegroundColor Cyan
$bcdFirmware = bcdedit /enum firmware 2>&1
$bcdFirmware | ForEach-Object { Write-Host "  $_" }

Write-Host ""
Write-Host "=== PASO 2: Verificando bootmgr actual ===" -ForegroundColor Cyan
$bcdMgr = bcdedit /enum "{bootmgr}" 2>&1
$bcdMgr | ForEach-Object { Write-Host "  $_" }

Write-Host ""
Write-Host "=== PASO 3: Poniendo Disco 2 offline ===" -ForegroundColor Cyan
try {
    Set-Disk -Number 2 -IsOffline $true -ErrorAction Stop
    Write-Host "  Disco 2 ahora OFFLINE" -ForegroundColor Green
    Start-Sleep -Seconds 2
} catch {
    Write-Host "  Error al poner offline: $($_.Exception.Message)" -ForegroundColor Yellow
    
    # Try via diskpart
    Write-Host "  Intentando via diskpart..." -ForegroundColor Yellow
    @"
select disk 2
offline disk
"@ | Out-File "C:\Users\corba\Downloads\Compu\dp_offline.txt" -Encoding ASCII
    diskpart /s "C:\Users\corba\Downloads\Compu\dp_offline.txt" 2>&1 | ForEach-Object { Write-Host "  $_" }
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "=== PASO 4: Intentando clean con disco offline ===" -ForegroundColor Cyan
@"
select disk 2
online disk noerr
attributes disk clear readonly noerr
clean
"@ | Out-File "C:\Users\corba\Downloads\Compu\dp_force_clean.txt" -Encoding ASCII
$cleanResult = diskpart /s "C:\Users\corba\Downloads\Compu\dp_force_clean.txt" 2>&1
$cleanResult | ForEach-Object { Write-Host "  $_" }

Start-Sleep -Seconds 2

# Check if clean worked
$disk = Get-Disk -Number 2
$parts = Get-Partition -DiskNumber 2 -ErrorAction SilentlyContinue
if (-not $parts) {
    Write-Host ""
    Write-Host "  DISCO LIMPIO!" -ForegroundColor Green
    
    # Initialize + Format
    Write-Host ""
    Write-Host "=== PASO 5: Inicializando y formateando ===" -ForegroundColor Cyan
    Initialize-Disk -Number 2 -PartitionStyle GPT
    $p = New-Partition -DiskNumber 2 -UseMaximumSize -AssignDriveLetter
    $L = $p.DriveLetter
    Start-Sleep -Seconds 2
    Format-Volume -DriveLetter $L -FileSystem NTFS -NewFileSystemLabel "NVMe_Ready" -Confirm:$false
    
    $v = Get-Volume -DriveLetter $L
    Write-Host "  Unidad: $($L):" -ForegroundColor Green
    Write-Host "  Tamano: $([math]::Round($v.Size/1GB, 2)) GB" -ForegroundColor Green
    Write-Host "  Libre: $([math]::Round($v.SizeRemaining/1GB, 2)) GB" -ForegroundColor Green
    
    # Test
    Write-Host ""
    Write-Host "=== PASO 6: Test de integridad ===" -ForegroundColor Cyan
    $testPath = "$($L):\test.bin"
    $buf = New-Object byte[] 10485760
    (New-Object Random).NextBytes($buf)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $h1 = [BitConverter]::ToString($sha.ComputeHash($buf))
    [IO.File]::WriteAllBytes($testPath, $buf)
    $h2 = [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($testPath)))
    if ($h1 -eq $h2) { Write-Host "  SHA256 OK - Integridad perfecta" -ForegroundColor Green }
    else { Write-Host "  SHA256 FALLO" -ForegroundColor Red }
    Remove-Item $testPath -Force -ErrorAction SilentlyContinue
} else {
    Write-Host ""
    Write-Host "  El disco AUN tiene $($parts.Count) particiones." -ForegroundColor Red
    Write-Host "  IsSystem: $($disk.IsSystem)" -ForegroundColor Red
    Write-Host ""
    Write-Host "  SOLUCION FINAL: Necesitas reiniciar y entrar a la BIOS." -ForegroundColor Yellow
    Write-Host "  En la BIOS, ve a Boot > Boot Option Priorities" -ForegroundColor Yellow
    Write-Host "  y asegurate de que el disco de arranque #1 sea el SA400 (SATA)" -ForegroundColor Yellow
    Write-Host "  y NO el Kingston NVMe. Guarda y reinicia." -ForegroundColor Yellow
    Write-Host "  Despues del reinicio, este script deberia funcionar." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Presiona Enter para cerrar"
