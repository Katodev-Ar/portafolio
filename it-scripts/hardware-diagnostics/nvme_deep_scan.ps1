# ============================================================
# ESCANEO PROFUNDO SECTOR A SECTOR - Kingston SNV2S250G
# Usa WMI/PowerShell para leer bloques directamente
# ============================================================

$logPath = "C:\Users\corba\Downloads\Compu\nvme_sector_scan.txt"
$results = @()
$results += "================================================================"
$results += "ESCANEO PROFUNDO SECTOR A SECTOR - KINGSTON SNV2S250G"
$results += "Fecha: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
$results += "================================================================"

Write-Host "=== TEST 1: LECTURA DIRECTA DE SECTORES via DeviceIoControl ===" -ForegroundColor Cyan

# Obtener handle al disco fisico
$diskNumber = 2
$diskPath = "\\.\PhysicalDrive$diskNumber"

Write-Host "Abriendo disco: $diskPath"

# Test de lectura por bloques usando .NET
Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public class DiskReader {
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern SafeFileHandle CreateFile(
        string lpFileName, uint dwDesiredAccess, uint dwShareMode,
        IntPtr lpSecurityAttributes, uint dwCreationDisposition,
        uint dwFlagsAndAttributes, IntPtr hTemplateFile);
    
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool ReadFile(SafeFileHandle hFile, byte[] lpBuffer,
        uint nNumberOfBytesToRead, out uint lpNumberOfBytesRead, IntPtr lpOverlapped);
    
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetFilePointerEx(SafeFileHandle hFile,
        long liDistanceToMove, out long lpNewFilePointer, uint dwMoveMethod);
    
    public const uint GENERIC_READ = 0x80000000;
    public const uint FILE_SHARE_READ = 0x00000001;
    public const uint FILE_SHARE_WRITE = 0x00000002;
    public const uint OPEN_EXISTING = 3;
    public const uint FILE_FLAG_NO_BUFFERING = 0x20000000;
    
    public static SafeFileHandle OpenDisk(string path) {
        return CreateFile(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            IntPtr.Zero, OPEN_EXISTING, FILE_FLAG_NO_BUFFERING, IntPtr.Zero);
    }
    
    public static bool ReadSector(SafeFileHandle handle, long lba, byte[] buffer, out uint bytesRead) {
        long newPos;
        SetFilePointerEx(handle, lba * 512, out newPos, 0);
        return ReadFile(handle, buffer, (uint)buffer.Length, out bytesRead, IntPtr.Zero);
    }
}
"@ -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== TEST 2: LECTURA POR ZONAS DEL DISCO ===" -ForegroundColor Cyan
Write-Host "Escaneando zonas del Kingston SNV2S250G (Disco 2)..."

try {
    $handle = [DiskReader]::OpenDisk($diskPath)
    
    if ($handle.IsInvalid) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        Write-Host "No se puede abrir el disco directamente (Error $err). Usando metodo alternativo..." -ForegroundColor Yellow
        $handle = $null
    } else {
        Write-Host "Disco abierto exitosamente para lectura directa" -ForegroundColor Green
        
        $sectorSize = 512
        $buffer = New-Object byte[] (4096)  # 8 sectores a la vez
        
        # Zonas a testear: inicio, 25%, 50%, 75%, fin
        $diskSizeBytes = 250059350016
        $totalSectors = $diskSizeBytes / $sectorSize
        
        $zones = @(
            @{Name="Zona EFI (inicio)";   LBA=0},
            @{Name="Zona 12.5%";          LBA=[long]($totalSectors * 0.125)},
            @{Name="Zona 25%";            LBA=[long]($totalSectors * 0.25)},
            @{Name="Zona 37.5%";          LBA=[long]($totalSectors * 0.375)},
            @{Name="Zona 50% (centro)";   LBA=[long]($totalSectors * 0.50)},
            @{Name="Zona 62.5%";          LBA=[long]($totalSectors * 0.625)},
            @{Name="Zona 75%";            LBA=[long]($totalSectors * 0.75)},
            @{Name="Zona 87.5%";          LBA=[long]($totalSectors * 0.875)},
            @{Name="Zona 95% (final)";    LBA=[long]($totalSectors * 0.95)}
        )
        
        $zoneResults = @()
        
        foreach ($zone in $zones) {
            $lba = $zone.LBA
            $name = $zone.Name
            
            # Leer 100 sectores contiguos en cada zona para medir estabilidad
            $errores = 0
            $ok = 0
            $tiempos = @()
            
            for ($i = 0; $i -lt 50; $i++) {
                $bytesRead = 0
                $startTime = [DateTime]::Now
                $result = [DiskReader]::ReadSector($handle, $lba + ($i * 8), $buffer, [ref]$bytesRead)
                $elapsed = ([DateTime]::Now - $startTime).TotalMilliseconds
                
                if ($result -and $bytesRead -gt 0) {
                    $ok++
                    $tiempos += $elapsed
                } else {
                    $errores++
                }
            }
            
            $avgTime = if ($tiempos.Count -gt 0) { [math]::Round(($tiempos | Measure-Object -Average).Average, 2) } else { 0 }
            $maxTime = if ($tiempos.Count -gt 0) { [math]::Round(($tiempos | Measure-Object -Maximum).Maximum, 2) } else { 0 }
            
            $estado = if ($errores -eq 0) { "OK" } elseif ($errores -lt 5) { "DEGRADADO" } else { "CRITICO" }
            
            $zoneResults += [PSCustomObject]@{
                Zona    = $name
                LBA     = $lba
                OK      = $ok
                Errores = $errores
                AvgMs   = $avgTime
                MaxMs   = $maxTime
                Estado  = $estado
            }
            
            $color = if ($estado -eq "OK") { "Green" } elseif ($estado -eq "DEGRADADO") { "Yellow" } else { "Red" }
            Write-Host "  [$estado] $name (LBA: $lba) - OK:$ok Err:$errores Avg:${avgTime}ms Max:${maxMs}ms" -ForegroundColor $color
        }
        
        $handle.Close()
        
        Write-Host ""
        Write-Host "=== RESUMEN DE ZONAS ===" -ForegroundColor Cyan
        $zoneResults | Format-Table -AutoSize
        
        $results += ""
        $results += "=== SCAN POR ZONAS ==="
        $zoneResults | ForEach-Object {
            $results += "[$($_.Estado)] $($_.Zona) LBA:$($_.LBA) OK:$($_.OK) Err:$($_.Errores) Avg:$($_.AvgMs)ms Max:$($_.MaxMs)ms"
        }
    }
} catch {
    Write-Host "Error durante el scan: $($_.Exception.Message)" -ForegroundColor Red
    $results += "Error durante scan: $($_.Exception.Message)"
}

# TEST 3: Intentar leer la particion EFI del NVMe
Write-Host ""
Write-Host "=== TEST 3: CONTENIDO DE PARTICION EFI DEL NVMe ===" -ForegroundColor Cyan
$volGuid = "{df3b9b8c-8c26-480e-8b2a-7691b3ccc91e}"
$accessPath = "\\?\Volume$volGuid\"
Write-Host "Intentando acceder a: $accessPath"

try {
    $items = Get-ChildItem $accessPath -Recurse -ErrorAction Stop -Force
    Write-Host "Archivos en la particion EFI del NVMe:" -ForegroundColor Green
    $items | Format-Table FullName, Length, LastWriteTime -AutoSize
    $results += ""
    $results += "=== CONTENIDO EFI NVMe ==="
    $items | ForEach-Object { $results += "$($_.FullName) - $($_.Length) bytes" }
} catch {
    Write-Host "No se puede leer la EFI del NVMe directamente: $($_.Exception.Message)" -ForegroundColor Yellow
}

# TEST 4: Benchmark de lectura raw via WMI Storage
Write-Host ""
Write-Host "=== TEST 4: VELOCIDAD DE LECTURA SECUENCIAL (bloques grandes) ===" -ForegroundColor Cyan

try {
    $handle2 = [DiskReader]::OpenDisk($diskPath)
    if (-not $handle2.IsInvalid) {
        $bufferBig = New-Object byte[] (1048576)  # 1MB buffer
        $velocidades = @()
        
        for ($i = 0; $i -lt 10; $i++) {
            $lba = [long]($i * 2048)  # Primeros 10MB
            $bytesRead = 0
            $start = [DateTime]::Now
            [DiskReader]::ReadSector($handle2, $lba, $bufferBig, [ref]$bytesRead) | Out-Null
            $ms = ([DateTime]::Now - $start).TotalMilliseconds
            if ($ms -gt 0 -and $bytesRead -gt 0) {
                $mbps = [math]::Round(($bytesRead / 1048576) / ($ms / 1000), 2)
                $velocidades += $mbps
                Write-Host "  Bloque $i (LBA $lba): $mbps MB/s ($([math]::Round($ms,1)) ms)" -ForegroundColor $(if ($mbps -gt 100) {"Green"} elseif ($mbps -gt 10) {"Yellow"} else {"Red"})
            }
        }
        
        if ($velocidades.Count -gt 0) {
            $avgMbps = [math]::Round(($velocidades | Measure-Object -Average).Average, 2)
            $minMbps = [math]::Round(($velocidades | Measure-Object -Minimum).Minimum, 2)
            Write-Host ""
            Write-Host "  Velocidad promedio: $avgMbps MB/s" -ForegroundColor Cyan
            Write-Host "  Velocidad minima:   $minMbps MB/s" -ForegroundColor Cyan
            $results += ""
            $results += "=== VELOCIDAD DE LECTURA ==="
            $results += "Promedio: $avgMbps MB/s | Minimo: $minMbps MB/s"
            $results += "Nota: Un NVMe sano Kingston NV2 deberia leer a ~3000-3500 MB/s"
        }
        $handle2.Close()
    }
} catch {
    Write-Host "Error en benchmark: $($_.Exception.Message)" -ForegroundColor Red
}

# Guardar resultados
$results | Out-File -FilePath $logPath -Encoding UTF8
Write-Host ""
Write-Host "=== SCAN COMPLETADO ===" -ForegroundColor Green
Write-Host "Resultados guardados en: $logPath" -ForegroundColor Cyan
