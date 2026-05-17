$logPath = "C:\Users\corba\Downloads\Compu\nvme_sector_scan_admin.txt"
$ErrorActionPreference = "Stop"

try {
    $output = @()
    $output += "================================================================"
    $output += "ESCANEO RAW DE SUPERFICIE - KINGSTON SNV2S250G"
    $output += "Fecha: $(Get-Date)"
    $output += "================================================================"

    # Verify Admin
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        $output += "ERROR: El script debe ejecutarse como Administrador para acceder al disco."
        $output | Out-File $logPath
        exit
    }
    $output += "Privilegios de Administrador: OK"

    $diskNumber = 2
    $diskPath = "\\.\PhysicalDrive$diskNumber"

    Add-Type -TypeDefinition @"
    using System;
    using System.Runtime.InteropServices;
    using Microsoft.Win32.SafeHandles;
    
    public class DiskAPI {
        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
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
    }
"@

    $output += "Abriendo disco: $diskPath"
    $handle = [DiskAPI]::CreateFile($diskPath, [DiskAPI]::GENERIC_READ, [DiskAPI]::FILE_SHARE_READ -bor [DiskAPI]::FILE_SHARE_WRITE, [IntPtr]::Zero, [DiskAPI]::OPEN_EXISTING, [DiskAPI]::FILE_FLAG_NO_BUFFERING, [IntPtr]::Zero)

    if ($handle.IsInvalid) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        $output += "ERROR FATAL: No se puede abrir el disco directamente. Codigo de error Win32: $err"
    } else {
        $output += "Disco abierto con exito (Acceso Directo)."
        
        $buffer = New-Object byte[] (1048576) # 1 MB buffer
        
        $zonas = @(0, 1000, 5000, 10000, 50000, 100000, 200000)
        
        foreach ($mbOffset in $zonas) {
            $lba = [long]$mbOffset * 1048576 / 512
            $newPos = 0
            [DiskAPI]::SetFilePointerEx($handle, $mbOffset * 1048576, [ref]$newPos, 0) | Out-Null
            
            $bytesRead = 0
            $start = [DateTime]::Now
            $res = [DiskAPI]::ReadFile($handle, $buffer, 1048576, [ref]$bytesRead, [IntPtr]::Zero)
            $ms = ([DateTime]::Now - $start).TotalMilliseconds
            
            if ($res -and $bytesRead -eq 1048576) {
                $output += "  [OK] Zona ${mbOffset} MB (LBA: $lba) leida en $([math]::Round($ms, 2)) ms"
            } else {
                $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
                $output += "  [ERROR] Zona ${mbOffset} MB (LBA: $lba) fallo. Win32 Error: $err"
            }
        }
        $handle.Close()
        $output += "Escaneo de prueba completado."
    }

    $output += "================================================================"
    $output | Out-File $logPath
} catch {
    "ERROR EXCEPCION: $($_.Exception.Message)" | Out-File $logPath -Append
}
