# Busqueda ampliada: todos los eventos de error de disco en los ultimos 30 dias
$events = Get-WinEvent -FilterHashtable @{LogName='System'; Level=@(1,2,3); StartTime=(Get-Date).AddDays(-30)} -ErrorAction SilentlyContinue
$diskEvents = $events | Where-Object { $_.ProviderName -match 'disk|stor|nvme|ntfs|volmgr|volsnap|partition|WHEA|Kernel-PnP' }
$diskEvents | Select-Object -First 40 TimeCreated, Id, LevelDisplayName, ProviderName, Message | Out-File -FilePath "c:\Users\corba\Downloads\Compu\disk_errors.txt" -Encoding UTF8
Write-Output "Eventos de disco encontrados: $($diskEvents.Count)"

# Verificar estado del volumen E
Write-Output ""
Write-Output "--- ESTADO DEL VOLUMEN E ---"
Get-Volume -DriveLetter E -ErrorAction SilentlyContinue | Format-List *

# Verificar el estado del disco logico
Write-Output ""
Write-Output "--- ESTADO DETALLADO DEL DISCO 2 ---"
Get-Disk -Number 2 | Format-List *

# Verificar si es de solo lectura
Write-Output ""
Write-Output "--- ATRIBUTOS DE SOLO LECTURA ---"
$d = Get-Disk -Number 2
Write-Output "IsReadOnly: $($d.IsReadOnly)"
Write-Output "IsOffline: $($d.IsOffline)"
Write-Output "IsSystem: $($d.IsSystem)"
Write-Output "IsBoot: $($d.IsBoot)"
Write-Output "PartitionStyle: $($d.PartitionStyle)"
Write-Output "OperationalStatus: $($d.OperationalStatus)"
Write-Output "HealthStatus: $($d.HealthStatus)"
Write-Output "BusType: $($d.BusType)"
Write-Output "UniqueId: $($d.UniqueId)"
Write-Output "Path: $($d.Path)"
Write-Output "FirmwareVersion: $($d.FirmwareVersion)"
Write-Output "Location: $($d.Location)"
Write-Output "Number: $($d.Number)"
Write-Output "Size: $($d.Size)"
Write-Output "AllocatedSize: $($d.AllocatedSize)"
Write-Output "LargestFreeExtent: $($d.LargestFreeExtent)"
Write-Output "NumberOfPartitions: $($d.NumberOfPartitions)"
