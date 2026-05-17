# Post-Secure Erase: Inicializar, particionar y formatear el NVMe
$logPath = "C:\Users\corba\Downloads\Compu\post_erase_test.txt"
$log = @()
$log += "================================================================"
$log += "POST SECURE ERASE - TEST DE FUNCIONALIDAD"
$log += "Fecha: $(Get-Date)"
$log += "================================================================"

# 1. Estado actual del disco
Write-Host "[1/4] Estado actual del disco..." -ForegroundColor Yellow
$disk = Get-Disk -Number 2
Write-Host "  Modelo: $($disk.FriendlyName)" -ForegroundColor White
Write-Host "  Estado: $($disk.HealthStatus) / $($disk.OperationalStatus)" -ForegroundColor White
Write-Host "  Estilo: $($disk.PartitionStyle)" -ForegroundColor White
Write-Host "  Tamano: $([math]::Round($disk.Size/1GB, 2)) GB" -ForegroundColor White
$log += "Estado: $($disk.HealthStatus) / $($disk.OperationalStatus) / PartStyle: $($disk.PartitionStyle)"

# 2. Inicializar como GPT
Write-Host ""
Write-Host "[2/4] Inicializando disco como GPT..." -ForegroundColor Yellow
try {
    if ($disk.PartitionStyle -eq "RAW") {
        Initialize-Disk -Number 2 -PartitionStyle GPT -ErrorAction Stop
        Write-Host "  Disco inicializado como GPT." -ForegroundColor Green
        $log += "Initialize-Disk: OK"
    } else {
        # Limpiar e inicializar
        Clear-Disk -Number 2 -RemoveData -RemoveOEM -Confirm:$false -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Initialize-Disk -Number 2 -PartitionStyle GPT -ErrorAction Stop
        Write-Host "  Disco limpiado y reinicializado como GPT." -ForegroundColor Green
        $log += "Clear + Initialize-Disk: OK"
    }
} catch {
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    $log += "Initialize-Disk: ERROR - $($_.Exception.Message)"
}

Start-Sleep -Seconds 2

# 3. Crear particion y formatear
Write-Host ""
Write-Host "[3/4] Creando particion y formateando como NTFS..." -ForegroundColor Yellow
try {
    $part = New-Partition -DiskNumber 2 -UseMaximumSize -AssignDriveLetter -ErrorAction Stop
    $letra = $part.DriveLetter
    Write-Host "  Particion creada: $($letra):" -ForegroundColor Green
    $log += "New-Partition: OK - Letra $letra"

    Start-Sleep -Seconds 2

    # Formateo completo (verifica cada sector al escribir)
    Write-Host "  Formateando con verificacion completa (esto tardara unos minutos)..." -ForegroundColor Yellow
    $startFormat = Get-Date
    Format-Volume -DriveLetter $letra -FileSystem NTFS -NewFileSystemLabel "NVMe_Test" -Full -Force -ErrorAction Stop
    $formatTime = (Get-Date) - $startFormat
    Write-Host "  Formateado completado en $([math]::Round($formatTime.TotalMinutes, 1)) minutos!" -ForegroundColor Green
    $log += "Format-Volume (Full): OK en $([math]::Round($formatTime.TotalMinutes, 1)) min"

    # Verificar volumen
    $vol = Get-Volume -DriveLetter $letra
    Write-Host "  Volumen: $($vol.FileSystemLabel) | FS: $($vol.FileSystem) | Tamano: $([math]::Round($vol.Size/1GB, 2)) GB | Libre: $([math]::Round($vol.SizeRemaining/1GB, 2)) GB" -ForegroundColor Green
    $log += "Volumen OK: $($vol.FileSystem) $([math]::Round($vol.Size/1GB, 2)) GB"

} catch {
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    $log += "Particion/Formato: ERROR - $($_.Exception.Message)"
}

# 4. Test de escritura/lectura
Write-Host ""
Write-Host "[4/4] Test de escritura y lectura..." -ForegroundColor Yellow
try {
    $testDir = "$($letra):\nvme_test"
    New-Item -ItemType Directory -Path $testDir -Force | Out-Null

    # Escribir archivo de 100MB
    Write-Host "  Escribiendo archivo de prueba de 100MB..." -ForegroundColor Yellow
    $testFile = "$testDir\test_100mb.bin"
    $buffer = New-Object byte[] (104857600) # 100MB
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $hash1 = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($buffer))

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    [System.IO.File]::WriteAllBytes($testFile, $buffer)
    $sw.Stop()
    $writeMBps = [math]::Round(100 / ($sw.ElapsedMilliseconds / 1000), 2)
    Write-Host "  Escritura: $writeMBps MB/s ($($sw.ElapsedMilliseconds) ms)" -ForegroundColor Green
    $log += "Write test: $writeMBps MB/s"

    # Leer y verificar integridad
    Write-Host "  Leyendo y verificando integridad..." -ForegroundColor Yellow
    $sw.Restart()
    $readBuffer = [System.IO.File]::ReadAllBytes($testFile)
    $sw.Stop()
    $readMBps = [math]::Round(100 / ($sw.ElapsedMilliseconds / 1000), 2)
    $hash2 = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($readBuffer))

    if ($hash1 -eq $hash2) {
        Write-Host "  Lectura: $readMBps MB/s ($($sw.ElapsedMilliseconds) ms)" -ForegroundColor Green
        Write-Host "  INTEGRIDAD: SHA256 COINCIDE - Datos escritos y leidos correctamente!" -ForegroundColor Green
        $log += "Read test: $readMBps MB/s | Integridad: OK"
    } else {
        Write-Host "  INTEGRIDAD: SHA256 NO COINCIDE - ERROR DE DATOS!" -ForegroundColor Red
        $log += "Read test: $readMBps MB/s | Integridad: FALLO!"
    }

    # Limpiar
    Remove-Item $testDir -Recurse -Force -ErrorAction SilentlyContinue

} catch {
    Write-Host "  Error en test: $($_.Exception.Message)" -ForegroundColor Red
    $log += "Test R/W: ERROR - $($_.Exception.Message)"
}

# SMART post-test
Write-Host ""
Write-Host "=== SMART POST-TEST ===" -ForegroundColor Cyan
$smartctl = "C:\Program Files\smartmontools\bin\smartctl.exe"
if (Test-Path $smartctl) {
    $smart = & $smartctl -a /dev/sdc 2>&1
    $smart | ForEach-Object {
        if ($_ -match "Health|Available Spare|Percentage Used|Media and Data|Temperature:|Unsafe|Power Cycles|Data Units") {
            Write-Host "  $_" -ForegroundColor White
        }
    }
    $smart | Out-File "C:\Users\corba\Downloads\Compu\smart_post_test.txt" -Encoding UTF8
}

$log += "================================================================"
$log | Out-File $logPath -Encoding UTF8

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  TEST POST-ERASE COMPLETADO" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Read-Host "Presiona Enter para cerrar"
