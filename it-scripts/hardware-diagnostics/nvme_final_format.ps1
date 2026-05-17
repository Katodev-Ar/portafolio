# FINAL: Format NVMe + Full integrity test + SMART report
Write-Host "=== PASO 1: Formateando disco con diskpart ===" -ForegroundColor Cyan
$r = diskpart /s "C:\Users\corba\Downloads\Compu\dp_format_final.txt" 2>&1
$r | ForEach-Object { Write-Host "  $_" }

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "=== PASO 2: Verificando unidad E: ===" -ForegroundColor Cyan
if (Test-Path "E:\") {
    $vol = Get-Volume -DriveLetter E -ErrorAction SilentlyContinue
    if ($vol) {
        Write-Host "  Etiqueta: $($vol.FileSystemLabel)" -ForegroundColor Green
        Write-Host "  FS: $($vol.FileSystem)" -ForegroundColor Green
        Write-Host "  Tamano: $([math]::Round($vol.Size/1GB, 2)) GB" -ForegroundColor Green
        Write-Host "  Libre: $([math]::Round($vol.SizeRemaining/1GB, 2)) GB" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "=== PASO 3: Test de integridad (10MB) ===" -ForegroundColor Cyan
    $testPath = "E:\test_integrity.bin"
    $buf = New-Object byte[] 10485760
    (New-Object Random).NextBytes($buf)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $h1 = [BitConverter]::ToString($sha.ComputeHash($buf))
    [IO.File]::WriteAllBytes($testPath, $buf)
    $readBack = [IO.File]::ReadAllBytes($testPath)
    $h2 = [BitConverter]::ToString($sha.ComputeHash($readBack))
    if ($h1 -eq $h2) {
        Write-Host "  10MB SHA256: INTEGRIDAD OK" -ForegroundColor Green
    } else {
        Write-Host "  10MB SHA256: FALLO" -ForegroundColor Red
    }
    Remove-Item $testPath -Force -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "=== PASO 4: Test grande (100MB) ===" -ForegroundColor Cyan
    $testPath2 = "E:\test_100mb.bin"
    $buf2 = New-Object byte[] 104857600
    (New-Object Random).NextBytes($buf2)
    $h3 = [BitConverter]::ToString($sha.ComputeHash($buf2))
    $sw = [Diagnostics.Stopwatch]::StartNew()
    [IO.File]::WriteAllBytes($testPath2, $buf2)
    $sw.Stop()
    $wSpeed = [math]::Round(100 / ($sw.ElapsedMilliseconds / 1000), 2)
    Write-Host "  Escritura 100MB: $wSpeed MB/s" -ForegroundColor Cyan

    $sw.Restart()
    $readBack2 = [IO.File]::ReadAllBytes($testPath2)
    $sw.Stop()
    $rSpeed = [math]::Round(100 / ($sw.ElapsedMilliseconds / 1000), 2)
    $h4 = [BitConverter]::ToString($sha.ComputeHash($readBack2))
    Write-Host "  Lectura 100MB: $rSpeed MB/s" -ForegroundColor Cyan

    if ($h3 -eq $h4) {
        Write-Host "  100MB SHA256: INTEGRIDAD OK" -ForegroundColor Green
    } else {
        Write-Host "  100MB SHA256: FALLO" -ForegroundColor Red
    }
    Remove-Item $testPath2 -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "  E:\ no accesible" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== PASO 5: SMART Final ===" -ForegroundColor Cyan
$smartctl = "C:\Program Files\smartmontools\bin\smartctl.exe"
if (Test-Path $smartctl) {
    $smart = & $smartctl -a /dev/sdc 2>&1
    $smart | ForEach-Object {
        if ($_ -match "Health|Available Spare|Percentage Used|Media and Data|Temperature:|Unsafe|Power Cycles|Data Units") {
            Write-Host "  $_" -ForegroundColor White
        }
    }
    $smart | Out-File "C:\Users\corba\Downloads\Compu\smart_final_report.txt" -Encoding UTF8
}

Write-Host ""
Write-Host "=== PASO 6: Disco 2 estado final ===" -ForegroundColor Cyan
Get-Disk -Number 2 | Format-List FriendlyName, IsSystem, IsBoot, HealthStatus, OperationalStatus, Size

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  DISCO NVMe COMPLETAMENTE LISTO" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Read-Host "Presiona Enter para cerrar"
