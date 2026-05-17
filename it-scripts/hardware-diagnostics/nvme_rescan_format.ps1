# Rescan + re-detect + initialize + format the NVMe

Write-Host "=== PASO 1: Rescaneando discos ===" -ForegroundColor Cyan
$r = diskpart /s "C:\Users\corba\Downloads\Compu\dp_rescan.txt" 2>&1
$r | ForEach-Object { Write-Host "  $_" }

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "=== PASO 2: Listando discos ===" -ForegroundColor Cyan
Get-Disk | Format-Table Number, FriendlyName, Size, PartitionStyle, HealthStatus -AutoSize

# Find the NVMe
$nvme = Get-Disk | Where-Object { $_.FriendlyName -match "SNV2S250G" }
if (-not $nvme) {
    Write-Host "  NVMe no encontrado! Intentando por numero..." -ForegroundColor Yellow
    $nvme = Get-Disk -Number 2 -ErrorAction SilentlyContinue
}

if ($nvme) {
    $diskNum = $nvme.Number
    Write-Host "  NVMe encontrado: Disco $diskNum - $($nvme.FriendlyName) - PartStyle: $($nvme.PartitionStyle)" -ForegroundColor Green

    # Initialize if RAW
    if ($nvme.PartitionStyle -eq "RAW") {
        Write-Host ""
        Write-Host "=== PASO 3: Inicializando como GPT ===" -ForegroundColor Cyan
        Initialize-Disk -Number $diskNum -PartitionStyle GPT
        Write-Host "  Inicializado como GPT" -ForegroundColor Green
    }

    Start-Sleep -Seconds 2

    # Create partition
    Write-Host ""
    Write-Host "=== PASO 4: Creando particion ===" -ForegroundColor Cyan
    $part = New-Partition -DiskNumber $diskNum -UseMaximumSize -AssignDriveLetter
    $L = $part.DriveLetter
    Write-Host "  Particion creada: $($L):" -ForegroundColor Green

    Start-Sleep -Seconds 3

    # Format
    Write-Host ""
    Write-Host "=== PASO 5: Formateando NTFS ===" -ForegroundColor Cyan
    Format-Volume -DriveLetter $L -FileSystem NTFS -NewFileSystemLabel "NVMe_Ready" -Confirm:$false
    Write-Host "  Formateado completado" -ForegroundColor Green

    Start-Sleep -Seconds 2

    # Volume info
    $vol = Get-Volume -DriveLetter $L
    Write-Host ""
    Write-Host "=== RESULTADO ===" -ForegroundColor Green
    Write-Host "  Unidad: $($L):\" -ForegroundColor Green
    Write-Host "  Etiqueta: $($vol.FileSystemLabel)" -ForegroundColor Green
    Write-Host "  Tamano: $([math]::Round($vol.Size/1GB, 2)) GB" -ForegroundColor Green
    Write-Host "  Libre: $([math]::Round($vol.SizeRemaining/1GB, 2)) GB" -ForegroundColor Green

    # Integrity test
    Write-Host ""
    Write-Host "=== TEST DE INTEGRIDAD ===" -ForegroundColor Cyan
    $testPath = "$($L):\test_integrity.bin"
    $buf = New-Object byte[] 104857600
    (New-Object Random).NextBytes($buf)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $h1 = [BitConverter]::ToString($sha.ComputeHash($buf))

    $sw = [Diagnostics.Stopwatch]::StartNew()
    [IO.File]::WriteAllBytes($testPath, $buf)
    $sw.Stop()
    $wMBs = [math]::Round(100 / ($sw.ElapsedMilliseconds / 1000), 2)
    Write-Host "  Escritura 100MB: $wMBs MB/s" -ForegroundColor Cyan

    $sw.Restart()
    $rb = [IO.File]::ReadAllBytes($testPath)
    $sw.Stop()
    $rMBs = [math]::Round(100 / ($sw.ElapsedMilliseconds / 1000), 2)
    $h2 = [BitConverter]::ToString($sha.ComputeHash($rb))
    Write-Host "  Lectura 100MB: $rMBs MB/s" -ForegroundColor Cyan

    if ($h1 -eq $h2) {
        Write-Host "  SHA256: INTEGRIDAD PERFECTA" -ForegroundColor Green
    } else {
        Write-Host "  SHA256: ERROR DE INTEGRIDAD" -ForegroundColor Red
    }
    Remove-Item $testPath -Force -ErrorAction SilentlyContinue

    # SMART
    Write-Host ""
    Write-Host "=== SMART FINAL ===" -ForegroundColor Cyan
    $smartctl = "C:\Program Files\smartmontools\bin\smartctl.exe"
    if (Test-Path $smartctl) {
        & $smartctl -a /dev/sdc 2>&1 | ForEach-Object {
            if ($_ -match "Health|Available Spare|Percentage Used|Media and Data|Temperature:|Unsafe|Power Cycles|Data Units") {
                Write-Host "  $_" -ForegroundColor White
            }
        }
    }
} else {
    Write-Host "  ERROR CRITICO: El disco NVMe no aparece en el sistema" -ForegroundColor Red
    Write-Host "  Puede que necesite desconectar y reconectar fisicamente" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  PROCESO COMPLETADO" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Read-Host "Presiona Enter para cerrar"
