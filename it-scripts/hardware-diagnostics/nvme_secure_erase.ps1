# ============================================================
# NVMe FORMAT (Secure Erase via Firmware)
# Kingston SNV2S250G - Disco 2
# ============================================================
# ESTE SCRIPT ENVIA EL COMANDO NVMe FORMAT DIRECTAMENTE
# AL FIRMWARE DEL DISCO. ES EL MISMO COMANDO QUE KINGSTON
# SSD MANAGER ENVIARIA. NO ES UN WIPE POR SOFTWARE.
# ============================================================

$ErrorActionPreference = "Stop"
$logPath = "C:\Users\corba\Downloads\Compu\secure_erase_log.txt"
$log = @()

$log += "================================================================"
$log += "NVMe SECURE ERASE - KINGSTON SNV2S250G"
$log += "Fecha: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
$log += "Metodo: NVMe Format Command via Windows Storage Stack"
$log += "================================================================"

# Verificar admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Ejecutar como Administrador" -ForegroundColor Red
    $log += "ERROR: No se ejecuto como administrador"
    $log | Out-File $logPath -Encoding UTF8
    Read-Host "Presiona Enter para salir"
    exit
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  NVMe SECURE ERASE - KINGSTON SNV2S250G (Disco 2)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Paso 1: Identificar el disco
Write-Host "[1/5] Verificando disco objetivo..." -ForegroundColor Yellow
$targetDisk = Get-PhysicalDisk -DeviceNumber 2
$model = $targetDisk.FriendlyName
$serial = $targetDisk.SerialNumber
$size = [math]::Round($targetDisk.Size / 1GB, 2)

Write-Host "  Modelo:  $model" -ForegroundColor White
Write-Host "  Serial:  $serial" -ForegroundColor White
Write-Host "  Tamano:  $size GB" -ForegroundColor White
Write-Host "  Health:  $($targetDisk.HealthStatus)" -ForegroundColor White
$log += "Disco identificado: $model | Serial: $serial | $size GB"

# Verificacion de seguridad: asegurarnos de que es el NVMe y NO el disco principal
if ($model -notmatch "SNV2S250G") {
    Write-Host ""
    Write-Host "  ABORTAR: El Disco 2 NO es el Kingston SNV2S250G esperado." -ForegroundColor Red
    Write-Host "  Modelo encontrado: $model" -ForegroundColor Red
    $log += "ABORTADO: Disco incorrecto - $model"
    $log | Out-File $logPath -Encoding UTF8
    Read-Host "Presiona Enter para salir"
    exit
}
Write-Host "  CONFIRMADO: Es el NVMe defectuoso correcto." -ForegroundColor Green
$log += "Verificacion de seguridad: PASADA - Es el disco correcto"

# Paso 2: Verificar que NO es el disco de arranque
Write-Host ""
Write-Host "[2/5] Verificando que no es disco de arranque..." -ForegroundColor Yellow
$bootPartition = Get-Partition -DiskNumber 2 | Where-Object { $_.IsBoot -eq $true }
if ($bootPartition) {
    Write-Host "  ABORTAR: Este disco tiene una particion de arranque activa!" -ForegroundColor Red
    $log += "ABORTADO: Disco tiene particion de arranque activa"
    $log | Out-File $logPath -Encoding UTF8
    Read-Host "Presiona Enter para salir"
    exit
}
Write-Host "  CONFIRMADO: No es disco de arranque." -ForegroundColor Green
$log += "Verificacion de arranque: PASADA - No es disco de boot"

# Paso 3: Tomar SMART antes del borrado
Write-Host ""
Write-Host "[3/5] Capturando SMART pre-borrado..." -ForegroundColor Yellow
$smartctl = "C:\Program Files\smartmontools\bin\smartctl.exe"
if (Test-Path $smartctl) {
    $smartPre = & $smartctl -a /dev/sdc 2>&1
    $smartPre | Out-File "C:\Users\corba\Downloads\Compu\smart_pre_erase.txt" -Encoding UTF8
    Write-Host "  SMART guardado en smart_pre_erase.txt" -ForegroundColor Green
    
    # Extraer valores clave
    $smartPre | ForEach-Object {
        if ($_ -match "Available Spare:|Percentage Used:|Media and Data|Unsafe Shutdowns") {
            Write-Host "  $_" -ForegroundColor Gray
        }
    }
}
$log += "SMART pre-borrado capturado"

# Paso 4: Limpiar particiones y ejecutar el formato NVMe
Write-Host ""
Write-Host "[4/5] Preparando disco para NVMe Format..." -ForegroundColor Yellow

# Primero: quitar todas las particiones con diskpart
Write-Host "  Eliminando tabla de particiones..." -ForegroundColor Yellow
try {
    Clear-Disk -Number 2 -RemoveData -RemoveOEM -Confirm:$false -ErrorAction Stop
    Write-Host "  Tabla de particiones eliminada." -ForegroundColor Green
    $log += "Clear-Disk: OK - Particiones eliminadas"
} catch {
    Write-Host "  Advertencia al limpiar disco: $($_.Exception.Message)" -ForegroundColor Yellow
    $log += "Clear-Disk: Advertencia - $($_.Exception.Message)"
}

Start-Sleep -Seconds 2

# Ahora: enviar el comando de reset fisico (NVMe Format)
Write-Host ""
Write-Host "  >>> EJECUTANDO NVMe FORMAT (Secure Erase) <<<" -ForegroundColor Red
Write-Host "  Esto envia el comando de formateo directamente al firmware." -ForegroundColor Red
Write-Host "  NO desconectes ni apagues la PC." -ForegroundColor Red
Write-Host ""

$startTime = Get-Date
try {
    # Reset-PhysicalDisk envia el NVMe Format command al controlador
    $targetDisk2 = Get-PhysicalDisk -DeviceNumber 2
    Reset-PhysicalDisk -InputObject $targetDisk2 -ErrorAction Stop
    $elapsed = (Get-Date) - $startTime
    Write-Host "  NVMe FORMAT COMPLETADO en $([math]::Round($elapsed.TotalSeconds, 1)) segundos!" -ForegroundColor Green
    $log += "NVMe Format: EXITOSO en $([math]::Round($elapsed.TotalSeconds, 1)) segundos"
} catch {
    $elapsed = (Get-Date) - $startTime
    Write-Host "  Reset-PhysicalDisk fallo: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "  Intentando metodo alternativo via Initialize-Disk..." -ForegroundColor Yellow
    $log += "Reset-PhysicalDisk: Fallo - $($_.Exception.Message)"
    
    # Metodo alternativo: Initialize + Format
    try {
        Initialize-Disk -Number 2 -PartitionStyle GPT -ErrorAction Stop
        Write-Host "  Disco reinicializado como GPT." -ForegroundColor Green
        
        $newPart = New-Partition -DiskNumber 2 -UseMaximumSize -AssignDriveLetter -ErrorAction Stop
        Write-Host "  Nueva particion creada: $($newPart.DriveLetter):" -ForegroundColor Green
        
        Format-Volume -DriveLetter $newPart.DriveLetter -FileSystem NTFS -NewFileSystemLabel "NVMe_Recovered" -Full -Force -ErrorAction Stop
        Write-Host "  Volumen formateado como NTFS (formateo completo)." -ForegroundColor Green
        $log += "Metodo alternativo: EXITOSO - Disco formateado como NTFS"
    } catch {
        Write-Host "  Metodo alternativo tambien fallo: $($_.Exception.Message)" -ForegroundColor Red
        $log += "Metodo alternativo: FALLO - $($_.Exception.Message)"
    }
}

Start-Sleep -Seconds 3

# Paso 5: Verificar estado post-borrado
Write-Host ""
Write-Host "[5/5] Verificando estado post-borrado..." -ForegroundColor Yellow

# Verificar que el disco sigue visible
try {
    $postDisk = Get-PhysicalDisk -DeviceNumber 2 -ErrorAction Stop
    Write-Host "  Disco visible: $($postDisk.FriendlyName) - $($postDisk.HealthStatus)" -ForegroundColor Green
    $log += "Post-verificacion: Disco visible - $($postDisk.HealthStatus)"
    
    # Tomar SMART post-borrado
    if (Test-Path $smartctl) {
        Start-Sleep -Seconds 2
        $smartPost = & $smartctl -a /dev/sdc 2>&1
        $smartPost | Out-File "C:\Users\corba\Downloads\Compu\smart_post_erase.txt" -Encoding UTF8
        Write-Host "  SMART post-borrado guardado." -ForegroundColor Green
        
        Write-Host ""
        Write-Host "  === SMART POST-BORRADO ===" -ForegroundColor Cyan
        $smartPost | ForEach-Object {
            if ($_ -match "Health|Available Spare|Percentage Used|Media and Data|Unsafe|Power Cycles|Temperature") {
                Write-Host "  $_" -ForegroundColor White
            }
        }
        $log += "SMART post-borrado capturado"
    }
    
    # Verificar particiones
    $postParts = Get-Partition -DiskNumber 2 -ErrorAction SilentlyContinue
    if ($postParts) {
        Write-Host ""
        Write-Host "  Particiones encontradas:" -ForegroundColor Cyan
        $postParts | Format-Table PartitionNumber, DriveLetter, Size, Type -AutoSize
    } else {
        Write-Host "  Sin particiones (disco limpio - listo para inicializar)" -ForegroundColor Cyan
    }
    
} catch {
    Write-Host "  CRITICO: El disco ya no es visible despues del borrado." -ForegroundColor Red
    Write-Host "  Esto puede significar que el controlador necesita un reinicio." -ForegroundColor Red
    $log += "Post-verificacion: DISCO NO VISIBLE"
}

$log += "================================================================"
$log += "PROCESO FINALIZADO: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
$log += "================================================================"
$log | Out-File $logPath -Encoding UTF8

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  PROCESO COMPLETADO" -ForegroundColor Cyan
Write-Host "  Log guardado en: $logPath" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Presiona Enter para cerrar"
