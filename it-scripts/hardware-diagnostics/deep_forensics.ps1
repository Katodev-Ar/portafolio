# Contar todos los resets del NVMe
$allEvents = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddDays(-90)} -ErrorAction SilentlyContinue
$nvmeResets = $allEvents | Where-Object { $_.Id -eq 129 -and $_.ProviderName -eq 'stornvme' -and $_.Message -match 'RaidPort2' }
Write-Output "Total de NVMe Device Resets (RaidPort2) en 90 dias: $($nvmeResets.Count)"
if ($nvmeResets) {
    Write-Output "Primer reset registrado: $($nvmeResets[-1].TimeCreated)"
    Write-Output "Ultimo reset registrado: $($nvmeResets[0].TimeCreated)"
}

# Buscar WHEA errors (hardware errors)
Write-Output ""
$wheaEvents = $allEvents | Where-Object { $_.ProviderName -match 'WHEA' }
Write-Output "Total de errores WHEA (Hardware) en 90 dias: $($wheaEvents.Count)"
if ($wheaEvents) {
    $wheaEvents | Select-Object -First 5 TimeCreated, Id, LevelDisplayName, Message | Format-List | Out-String | Write-Output
}

# Buscar eventos especificamente del disco 2 / E:
Write-Output ""
$volE = $allEvents | Where-Object { $_.Message -match 'volumen E:|volume E:' }
Write-Output "Eventos que mencionan volumen E: $($volE.Count)"
if ($volE) {
    $volE | Select-Object -First 5 TimeCreated, Id, ProviderName, LevelDisplayName, Message | Format-List | Out-String | Write-Output
}

# Buscar BugCheck / BlueScreens
Write-Output ""
$bsod = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'; StartTime=(Get-Date).AddDays(-90)} -ErrorAction SilentlyContinue
Write-Output "Pantallazos azules (BSOD) registrados en 90 dias: $($bsod.Count)"
if ($bsod) {
    $bsod | Select-Object -First 5 TimeCreated, Id, Message | Format-List | Out-String | Write-Output
}

# Estado de la particion EFI en el disco 2
Write-Output ""
Write-Output "--- DETALLE DE PARTICIONES DEL DISCO 2 ---"
Get-Partition -DiskNumber 2 | Select-Object PartitionNumber, DriveLetter, @{Name="SizeMB";Expression={[math]::Round($_.Size / 1MB, 2)}}, Type, GptType, IsSystem, IsBoot, IsHidden, IsActive, MbrType | Format-List | Out-String | Write-Output

# Obtener informacion del Namespace NVMe
Write-Output ""
Write-Output "--- INFORMACION DE NAMESPACE NVMe ---"
$nsInfo = & 'C:\Program Files\smartmontools\bin\smartctl.exe' -n standby /dev/sdc 2>&1
Write-Output $nsInfo
