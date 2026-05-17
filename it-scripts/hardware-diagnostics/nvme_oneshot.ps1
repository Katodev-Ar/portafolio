# ONE-SHOT: diskpart clean+format, then integrity test

Write-Host "=== DISKPART: CLEAN + FORMAT ===" -ForegroundColor Cyan
$dp = diskpart /s "C:\Users\corba\Downloads\Compu\dp_full.txt" 2>&1
$dp | ForEach-Object { Write-Host "  $_" }

Start-Sleep -Seconds 5

# Verify E: exists
Write-Host ""
if (Test-Path "E:\") {
    Write-Host "=== E:\ ACCESIBLE ===" -ForegroundColor Green
    $v = Get-Volume -DriveLetter E
    Write-Host "  Etiqueta: $($v.FileSystemLabel)"
    Write-Host "  Tamano: $([math]::Round($v.Size/1GB, 2)) GB"
    Write-Host "  Libre: $([math]::Round($v.SizeRemaining/1GB, 2)) GB"

    # Integrity test
    Write-Host ""
    Write-Host "=== TEST DE INTEGRIDAD ===" -ForegroundColor Cyan
    $path = "E:\test.bin"
    $data = New-Object byte[] 104857600
    (New-Object Random).NextBytes($data)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hash1 = [BitConverter]::ToString($sha.ComputeHash($data))

    $t1 = Get-Date
    [IO.File]::WriteAllBytes($path, $data)
    $wMs = (Get-Date).Subtract($t1).TotalMilliseconds
    $wMBs = [math]::Round(100 / ($wMs / 1000), 1)
    Write-Host "  Escritura 100MB: $wMBs MB/s ($([math]::Round($wMs)) ms)" -ForegroundColor Green

    $t2 = Get-Date
    $read = [IO.File]::ReadAllBytes($path)
    $rMs = (Get-Date).Subtract($t2).TotalMilliseconds
    $rMBs = [math]::Round(100 / ($rMs / 1000), 1)
    $hash2 = [BitConverter]::ToString($sha.ComputeHash($read))
    Write-Host "  Lectura 100MB: $rMBs MB/s ($([math]::Round($rMs)) ms)" -ForegroundColor Green

    if ($hash1 -eq $hash2) {
        Write-Host "  SHA256: INTEGRIDAD PERFECTA" -ForegroundColor Green
    } else {
        Write-Host "  SHA256: FALLO" -ForegroundColor Red
    }
    Remove-Item $path -Force -ErrorAction SilentlyContinue

    # SMART
    Write-Host ""
    Write-Host "=== SMART ===" -ForegroundColor Cyan
    & "C:\Program Files\smartmontools\bin\smartctl.exe" -a /dev/sdc 2>&1 | ForEach-Object {
        if ($_ -match "Health|Available Spare|Percentage Used|Media and Data|Temperature:|Unsafe|Power Cycles|Data Units") {
            Write-Host "  $_" -ForegroundColor White
        }
    }
} else {
    Write-Host "=== E:\ NO ACCESIBLE ===" -ForegroundColor Red
    Get-Partition -DiskNumber 2 -ErrorAction SilentlyContinue | Format-Table
}

Write-Host ""
Read-Host "Presiona Enter"
