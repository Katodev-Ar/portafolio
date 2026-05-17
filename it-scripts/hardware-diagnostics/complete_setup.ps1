# Step 1: Clean Disk 2 with diskpart (removes ALL partitions including System)
Write-Host "=== PASO 1: Limpiando TODAS las particiones del Disco 2 ===" -ForegroundColor Cyan

$dpScript = "C:\Users\corba\Downloads\Compu\dp_clean.txt"
$dpOut = diskpart /s $dpScript 2>&1
$dpOut | ForEach-Object { Write-Host "  $_" }

Start-Sleep -Seconds 3

# Step 2: Verify it's clean
Write-Host ""
Write-Host "=== PASO 2: Verificando disco limpio ===" -ForegroundColor Cyan
$disk = Get-Disk -Number 2
Write-Host "  PartitionStyle: $($disk.PartitionStyle)"
Write-Host "  IsSystem: $($disk.IsSystem)"
Write-Host "  HealthStatus: $($disk.HealthStatus)"

$parts = Get-Partition -DiskNumber 2 -ErrorAction SilentlyContinue
if ($parts) {
    Write-Host "  ADVERTENCIA: Aun tiene particiones:" -ForegroundColor Yellow
    $parts | Format-Table PartitionNumber, Size, Type
} else {
    Write-Host "  OK: Disco completamente limpio (sin particiones)" -ForegroundColor Green
}

# Step 3: Initialize as GPT (NO EFI partition this time)
Write-Host ""
Write-Host "=== PASO 3: Inicializando como GPT ===" -ForegroundColor Cyan
if ($disk.PartitionStyle -eq "RAW") {
    Initialize-Disk -Number 2 -PartitionStyle GPT
    Write-Host "  Disco inicializado como GPT" -ForegroundColor Green
}

# Step 4: Create a single data partition (NO system/EFI partition)
Write-Host ""
Write-Host "=== PASO 4: Creando particion de datos ===" -ForegroundColor Cyan
$part = New-Partition -DiskNumber 2 -UseMaximumSize -AssignDriveLetter
$letra = $part.DriveLetter
Write-Host "  Particion creada con letra: $letra" -ForegroundColor Green

Start-Sleep -Seconds 2

# Step 5: Format as NTFS (quick format)
Write-Host ""
Write-Host "=== PASO 5: Formateando como NTFS ===" -ForegroundColor Cyan
Format-Volume -DriveLetter $letra -FileSystem NTFS -NewFileSystemLabel "NVMe_Ready" -Confirm:$false
Write-Host "  Formateado completado" -ForegroundColor Green

# Step 6: Verify
Write-Host ""
Write-Host "=== PASO 6: Verificacion final ===" -ForegroundColor Cyan
$vol = Get-Volume -DriveLetter $letra
Write-Host "  Unidad: $($letra):" -ForegroundColor Green
Write-Host "  Etiqueta: $($vol.FileSystemLabel)" -ForegroundColor Green
Write-Host "  Sistema de archivos: $($vol.FileSystem)" -ForegroundColor Green
Write-Host "  Tamano total: $([math]::Round($vol.Size/1GB, 2)) GB" -ForegroundColor Green
Write-Host "  Espacio libre: $([math]::Round($vol.SizeRemaining/1GB, 2)) GB" -ForegroundColor Green

# Step 7: Quick write/read test
Write-Host ""
Write-Host "=== PASO 7: Test rapido de escritura/lectura ===" -ForegroundColor Cyan
$testFile = "$($letra):\test_integrity.bin"
$data = [byte[]]::new(10485760) # 10MB
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($data)
$hashBefore = [BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($data))

[IO.File]::WriteAllBytes($testFile, $data)
$readBack = [IO.File]::ReadAllBytes($testFile)
$hashAfter = [BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($readBack))

if ($hashBefore -eq $hashAfter) {
    Write-Host "  INTEGRIDAD OK: SHA256 coincide" -ForegroundColor Green
} else {
    Write-Host "  ERROR DE INTEGRIDAD: SHA256 NO coincide" -ForegroundColor Red
}
Remove-Item $testFile -Force -ErrorAction SilentlyContinue

# Step 8: SMART final
Write-Host ""
Write-Host "=== PASO 8: SMART final ===" -ForegroundColor Cyan
$smartctl = "C:\Program Files\smartmontools\bin\smartctl.exe"
if (Test-Path $smartctl) {
    $smart = & $smartctl -a /dev/sdc 2>&1
    $smart | ForEach-Object {
        if ($_ -match "Health|Available Spare|Percentage Used|Media and Data|Temperature:|Unsafe|Power Cycles|Data Units") {
            Write-Host "  $_" -ForegroundColor White
        }
    }
    $smart | Out-File "C:\Users\corba\Downloads\Compu\smart_final.txt" -Encoding UTF8
}

# Save results
$results = @(
    "=== RESULTADO FINAL ==="
    "Disco: KINGSTON SNV2S250G"
    "Letra: $($letra):"
    "Tamano: $([math]::Round($vol.Size/1GB, 2)) GB"
    "Libre: $([math]::Round($vol.SizeRemaining/1GB, 2)) GB"
    "FS: $($vol.FileSystem)"
    "Integridad: $(if ($hashBefore -eq $hashAfter) {'OK'} else {'FALLO'})"
)
$results | Out-File "C:\Users\corba\Downloads\Compu\nvme_final_result.txt" -Encoding UTF8

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  DISCO NVMe LISTO PARA USAR: $($letra):\" -ForegroundColor Green  
Write-Host "================================================================" -ForegroundColor Green
Read-Host "Presiona Enter para cerrar"
