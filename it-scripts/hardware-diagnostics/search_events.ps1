$events = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddDays(-30)} -ErrorAction SilentlyContinue
$filtered = $events | Where-Object { $_.Message -match 'Harddisk2|PhysicalDrive2|Kingston|SNV2|NVMe|nvme|WHEA|disk 2' }
$filtered | Select-Object -First 30 TimeCreated, Id, LevelDisplayName, ProviderName, Message | Out-File -FilePath "c:\Users\corba\Downloads\Compu\nvme_events.txt" -Encoding UTF8
Write-Output "Eventos encontrados: $($filtered.Count)"
