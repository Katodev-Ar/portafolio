Write-Output "=== PARTICIONES DEL DISCO 0 (1TB Principal) ==="
Get-Partition -DiskNumber 0 | Select-Object PartitionNumber, DriveLetter, Size, Type, GptType, IsSystem, IsBoot, IsHidden | Format-List

Write-Output "=== PARTICIONES DEL DISCO 1 (953 GB) ==="
Get-Partition -DiskNumber 1 | Select-Object PartitionNumber, DriveLetter, Size, Type, GptType, IsSystem, IsBoot, IsHidden | Format-List

Write-Output "=== ESPACIO LIBRE EN DISCO 0 ==="
$disk0 = Get-Disk -Number 0
$allocatedSize = 0
Get-Partition -DiskNumber 0 | ForEach-Object { $allocatedSize += $_.Size }
$freeSpace = $disk0.Size - $allocatedSize
Write-Output "Tamano total del disco: $([math]::Round($disk0.Size / 1GB, 2)) GB"
Write-Output "Tamano asignado a particiones: $([math]::Round($allocatedSize / 1GB, 2)) GB"
Write-Output "Espacio libre sin particionar: $([math]::Round($freeSpace / 1MB, 2)) MB"
