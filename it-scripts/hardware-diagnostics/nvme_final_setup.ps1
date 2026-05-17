# COMPLETE NVMe CLEANUP AND SETUP
# Runs diskpart to delete all partitions, then formats and tests

$logFile = "C:\Users\corba\Downloads\Compu\nvme_final_setup_log.txt"

# Step 1: Delete all partitions via diskpart with override
Write-Host "=== PASO 1: Eliminando particiones con override ===" -ForegroundColor Cyan
$result = diskpart /s "C:\Users\corba\Downloads\Compu\dp_delete_all.txt" 2>&1
$result | ForEach-Object { Write-Host "  $_" }
$result | Out-File $logFile -Encoding UTF8

Start-Sleep -Seconds 3

# Step 2: Check remaining partitions
Write-Host ""
Write-Host "=== PASO 2: Estado del disco ===" -ForegroundColor Cyan
$disk = Get-Disk -Number 2
Write-Host "  IsSystem: $($disk.IsSystem) | PartStyle: $($disk.PartitionStyle)"
$remainingParts = Get-Partition -DiskNumber 2 -ErrorAction SilentlyContinue
if ($remainingParts) {
    Write-Host "  Quedan $($remainingParts.Count) particiones" -ForegroundColor Yellow
    # Try clean now that EFI is gone
    Write-Host "  Intentando diskpart clean..." -ForegroundColor Yellow
    "select disk 2`r`nclean" | Out-File "C:\Users\corba\Downloads\Compu\dp_clean2.txt" -Encoding ASCII
    diskpart /s "C:\Users\corba\Downloads\Compu\dp_clean2.txt" 2>&1 | ForEach-Object { Write-Host "  $_" }
    Start-Sleep -Seconds 2
} else {
    Write-Host "  Disco limpio!" -ForegroundColor Green
}

# Step 3: Initialize
Write-Host ""
Write-Host "=== PASO 3: Inicializando ===" -ForegroundColor Cyan
$disk = Get-Disk -Number 2
if ($disk.PartitionStyle -eq "RAW") {
    Initialize-Disk -Number 2 -PartitionStyle GPT -ErrorAction SilentlyContinue
    Write-Host "  GPT inicializado" -ForegroundColor Green
} else {
    Write-Host "  Ya tiene PartitionStyle: $($disk.PartitionStyle)" -ForegroundColor Yellow
}

# Step 4: Create partition and format via diskpart (more reliable)
Write-Host ""
Write-Host "=== PASO 4: Creando particion y formateando ===" -ForegroundColor Cyan
@"
select disk 2
create partition primary
format fs=ntfs label="NVMe_Ready" quick
assign
"@ | Out-File "C:\Users\corba\Downloads\Compu\dp_format.txt" -Encoding ASCII
$fmtResult = diskpart /s "C:\Users\corba\Downloads\Compu\dp_format.txt" 2>&1
$fmtResult | ForEach-Object { Write-Host "  $_" }
$fmtResult | Out-File $logFile -Append -Encoding UTF8

Start-Sleep -Seconds 3

# Step 5: Find the new drive letter
Write-Host ""
Write-Host "=== PASO 5: Buscando nueva unidad ===" -ForegroundColor Cyan
$newPart = Get-Partition -DiskNumber 2 -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter -ne [char]0 -and $_.DriveLetter -ne '' }
if ($newPart) {
    $letra = $newPart.DriveLetter
    Write-Host "  Unidad encontrada: $($letra):" -ForegroundColor Green
    
    $vol = Get-Volume -DriveLetter $letra -ErrorAction SilentlyContinue
    if ($vol) {
        Write-Host "  Etiqueta: $($vol.FileSystemLabel)" -ForegroundColor Green
        Write-Host "  Tamano: $([math]::Round($vol.Size/1GB, 2)) GB" -ForegroundColor Green
        Write-Host "  Libre: $([math]::Round($vol.SizeRemaining/1GB, 2)) GB" -ForegroundColor Green
    }
    
    # Step 6: Write/Read test
    Write-Host ""
    Write-Host "=== PASO 6: Test de integridad ===" -ForegroundColor Cyan
    try {
        $testPath = "$($letra):\integrity_test.bin"
        $buf = New-Object byte[] 10485760
        (New-Object Random).NextBytes($buf)
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $h1 = [BitConverter]::ToString($sha.ComputeHash($buf))
        
        [System.IO.File]::WriteAllBytes($testPath, $buf)
        Write-Host "  Escritura 10MB: OK" -ForegroundColor Green
        
        $readBuf = [System.IO.File]::ReadAllBytes($testPath)
        $h2 = [BitConverter]::ToString($sha.ComputeHash($readBuf))
        
        if ($h1 -eq $h2) {
            Write-Host "  Lectura + SHA256: INTEGRIDAD OK" -ForegroundColor Green
            "Integridad: OK" | Out-File $logFile -Append -Encoding UTF8
        } else {
            Write-Host "  SHA256 NO COINCIDE - ERROR!" -ForegroundColor Red
            "Integridad: FALLO" | Out-File $logFile -Append -Encoding UTF8
        }
        Remove-Item $testPath -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "  Error en test: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "  No se encontro unidad con letra asignada" -ForegroundColor Red
    # List what we have
    Get-Partition -DiskNumber 2 -ErrorAction SilentlyContinue | Format-Table PartitionNumber, DriveLetter, Size, Type
}

# Step 7: SMART
Write-Host ""
Write-Host "=== PASO 7: SMART Final ===" -ForegroundColor Cyan
$smartctl = "C:\Program Files\smartmontools\bin\smartctl.exe"
if (Test-Path $smartctl) {
    & $smartctl -a /dev/sdc 2>&1 | ForEach-Object {
        if ($_ -match "Health|Available Spare|Percentage Used|Media and Data|Temperature:|Unsafe|Power Cycles|Data Units") {
            Write-Host "  $_" -ForegroundColor White
        }
    }
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  PROCESO COMPLETADO" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Read-Host "Presiona Enter para cerrar"
