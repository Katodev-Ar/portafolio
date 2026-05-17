# ============================================================
# DIAGNOSTICO FORENSE COMPLETO - POST REINICIO
# Kingston SNV2S250G | 7 Mayo 2026
# ============================================================

$output = @()
$output += "================================================================"
$output += "DIAGNOSTICO FORENSE POST-REINICIO - $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
$output += "================================================================"

# ----------------------------
# 1. EVENTOS stornvme HOY
# ----------------------------
$output += ""
$output += "=== [1] EVENTOS stornvme (ID 129) NUEVOS HOY ==="
$hoy = (Get-Date).Date
try {
    $eventosTotal = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='stornvme'; Id=129} -ErrorAction Stop
    $eventosHoy   = $eventosTotal | Where-Object { $_.TimeCreated -ge $hoy }
    $output += "Total historico: $($eventosTotal.Count)"
    if ($eventosHoy.Count -gt 0) {
        $output += "ALERTA: Resets nuevos hoy: $($eventosHoy.Count)"
        foreach ($e in $eventosHoy) {
            $output += "  -> $($e.TimeCreated) | $($e.Message)"
        }
    } else {
        $output += "OK - Sin nuevos resets desde el reinicio de hoy"
        $output += "Ultimo reset registrado: $($eventosTotal[0].TimeCreated)"
    }
} catch {
    $output += "Sin eventos stornvme encontrados: $_"
}

# ----------------------------
# 2. TODOS LOS ERRORES RECIENTES DEL SISTEMA (ultimas 24h)
# ----------------------------
$output += ""
$output += "=== [2] ERRORES CRITICOS DEL SISTEMA (ultimas 24h) ==="
try {
    $desde = (Get-Date).AddHours(-24)
    $errores = Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; StartTime=$desde} -ErrorAction Stop
    if ($errores.Count -eq 0) {
        $output += "OK - Sin errores criticos en las ultimas 24 horas"
    } else {
        $output += "Total errores criticos: $($errores.Count)"
        foreach ($e in ($errores | Select-Object -First 20)) {
            $output += "  [$($e.LevelDisplayName)] $($e.TimeCreated) | $($e.ProviderName) | ID:$($e.Id) | $($e.Message -replace '\r?\n',' ')"
        }
    }
} catch {
    $output += "Error leyendo eventos: $_"
}

# ----------------------------
# 3. VERIFICACION DE ARRANQUE BCD
# ----------------------------
$output += ""
$output += "=== [3] VERIFICACION DE ARRANQUE (BCD) ==="
try {
    $bcdResult = bcdedit /enum all 2>&1
    # Buscar donde esta el bootmgr
    $enBootmgr = $false
    $bootmgrDevice = ""
    foreach ($line in $bcdResult) {
        if ($line -match "Administrador de arranque de Windows" -or $line -match "Windows Boot Manager") {
            $enBootmgr = $true
        }
        if ($enBootmgr -and $line -match "^device") {
            $bootmgrDevice = $line.Trim()
            break
        }
    }
    $output += "Dispositivo del bootmgr: $bootmgrDevice"
    if ($bootmgrDevice -match "HarddiskVolume6") {
        $output += "EXITO MIGRACION: El bootloader esta en HarddiskVolume6 (Disco 0 - Kingston SA400 960GB) - NO en el NVMe defectuoso"
    } elseif ($bootmgrDevice -match "HarddiskVolume") {
        $output += "ATTENCION: Verificar en que disco fisico esta este volumen"
    } else {
        $output += "ESTADO: $bootmgrDevice"
    }
} catch {
    $output += "Error leyendo BCD (requiere admin): $_"
}

# ----------------------------
# 4. ESTADO ACTUAL DE PARTICIONES
# ----------------------------
$output += ""
$output += "=== [4] ESTADO ACTUAL DE TODOS LOS DISCOS ==="
$discos = Get-Disk
foreach ($disco in $discos) {
    $output += ""
    $output += "  DISCO $($disco.Number): $($disco.FriendlyName) | $([math]::Round($disco.Size/1GB,1)) GB | $($disco.HealthStatus) | $($disco.OperationalStatus)"
    $particiones = Get-Partition -DiskNumber $disco.Number -ErrorAction SilentlyContinue
    foreach ($p in $particiones) {
        $vol = $p | Get-Volume -ErrorAction SilentlyContinue
        $letra = if ($p.DriveLetter -ne [char]0) { $p.DriveLetter } else { "(sin letra)" }
        $fs = if ($vol) { $vol.FileSystem } else { "N/A" }
        $fsLabel = if ($vol) { $vol.FileSystemLabel } else { "" }
        $tamano = [math]::Round($p.Size/1MB, 0)
        $output += "    Particion $($p.PartitionNumber): Letra=$letra | Tipo=$($p.Type) | Tamano=${tamano}MB | FS=$fs | Label=$fsLabel | IsSystem=$($p.IsSystem) | IsBoot=$($p.IsBoot)"
    }
}

# ----------------------------
# 5. SMART NVMe ACTUALIZADO
# ----------------------------
$output += ""
$output += "=== [5] SMART NVMe KINGSTON SNV2S250G (ACTUALIZADO) ==="
$smartctl = "C:\Program Files\smartmontools\bin\smartctl.exe"
if (Test-Path $smartctl) {
    $smart = & $smartctl -a /dev/sdc 2>&1
    foreach ($line in $smart) {
        if ($line -match "Critical Warning|Temperature:|Available Spare|Percentage Used|Data Units|Unsafe Shutdown|Media and Data|Error Information Log|Power Cycles|Power On Hours|Controller Busy|Health self") {
            $output += "  $line"
        }
    }
} else {
    $output += "smartctl no encontrado"
}

# ----------------------------
# 6. SMART SA400 960GB (DISCO PRINCIPAL)
# ----------------------------
$output += ""
$output += "=== [6] SMART KINGSTON SA400S37960G (Disco Principal - 960GB) ==="
if (Test-Path $smartctl) {
    $smart2 = & $smartctl -a /dev/sda 2>&1
    foreach ($line in $smart2) {
        if ($line -match "overall-health|Reallocated_Sector|Pending_Sector|Uncorrectable|Power_On_Hours|Temperature|Unsafe_Shutdown|Percentage|SATA_Phy") {
            $output += "  $line"
        }
    }
}

# ----------------------------
# 7. PCIe POWER MANAGEMENT
# ----------------------------
$output += ""
$output += "=== [7] CONFIGURACION DE ENERGIA PCIe ==="
try {
    $planActivo = powercfg /getactivescheme
    $output += "Plan activo: $planActivo"
    $pcieCfg = powercfg /query SCHEME_CURRENT SUB_PCIEXPRESS 2>&1
    foreach ($line in $pcieCfg) {
        if ($line -match "GUID|Alias|Indice|Current|Maximum") {
            $output += "  $line"
        }
    }
} catch {
    $output += "Error leyendo powercfg: $_"
}

# ----------------------------
# 8. CONFIABILIDAD WINDOWS (WER)
# ----------------------------
$output += ""
$output += "=== [8] REGISTRO DE CONFIABILIDAD DEL SISTEMA (ultimas 72h) ==="
try {
    $wer = Get-WinEvent -LogName 'Application' -FilterXPath "*[System[(Level=1 or Level=2) and TimeCreated[timediff(@SystemTime) <= 259200000]]]" -ErrorAction Stop | Select-Object -First 10
    if ($wer.Count -eq 0) {
        $output += "OK - Sin fallas de aplicacion criticas en 72h"
    } else {
        foreach ($e in $wer) {
            $output += "  $($e.TimeCreated) | $($e.ProviderName) | $($e.Message -replace '\r?\n',' ' | Select-Object -First 1)"
        }
    }
} catch {
    $output += "Sin errores criticos de aplicacion en 72h (OK)"
}

# ----------------------------
# 9. VEREDICTO FINAL
# ----------------------------
$output += ""
$output += "================================================================"
$output += "VEREDICTO POST-REINICIO"
$output += "================================================================"
$output += "Fecha: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
$output += ""

# Guardar resultado
$outputPath = "C:\Users\corba\Downloads\Compu\forensics_post_reboot.txt"
$output | Out-File -FilePath $outputPath -Encoding UTF8
Write-Host "DIAGNOSTICO COMPLETADO. Resultado en: $outputPath"
$output | ForEach-Object { Write-Host $_ }
