$ErrorActionPreference = "Stop"

try {
    Write-Host "Limpiando disco 2..."
    Clear-Disk -Number 2 -RemoveData -RemoveOEM -Confirm:$false
    Start-Sleep -Seconds 2

    Write-Host "Inicializando disco 2 como GPT..."
    Initialize-Disk -Number 2 -PartitionStyle GPT

    Write-Host "Creando particion..."
    $part = New-Partition -DiskNumber 2 -UseMaximumSize -AssignDriveLetter
    $letra = $part.DriveLetter

    Write-Host "Formateando $letra : como NTFS..."
    Format-Volume -DriveLetter $letra -FileSystem NTFS -NewFileSystemLabel "NVMe_Ready" -Confirm:$false

    Write-Host "¡El disco NVMe esta limpio, formateado y listo para usarse! Letra asignada: $letra :" -ForegroundColor Green
} catch {
    Write-Host "Ocurrio un error: $($_.Exception.Message)" -ForegroundColor Red
}

Read-Host "Presiona Enter para salir"
