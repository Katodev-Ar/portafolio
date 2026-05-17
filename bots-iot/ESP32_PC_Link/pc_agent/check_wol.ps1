$ErrorActionPreference = "SilentlyContinue"

Write-Output "=== ADAPTADORES DE RED ==="
$adapters = Get-NetAdapter
foreach ($a in $adapters) {
    Write-Output ("Name: " + $a.Name + " | MAC: " + $a.MacAddress + " | Status: " + $a.Status)
}

Write-Output ""
Write-Output "=== CONFIGURACION WAKE-ON-LAN POR ADAPTADOR ==="
foreach ($a in $adapters) {
    $pm = Get-NetAdapterPowerManagement -Name $a.Name -ErrorAction SilentlyContinue
    if ($pm) {
        Write-Output ("--- " + $a.Name + " ---")
        Write-Output ("  WakeOnMagicPacket: " + $pm.WakeOnMagicPacket)
        Write-Output ("  WakeOnPattern:     " + $pm.WakeOnPattern)
        Write-Output ("  ArpOffload:        " + $pm.ArpOffload)
    }
}

Write-Output ""
Write-Output "=== PROPIEDADES AVANZADAS DE REALTEK (LAN) ==="
Get-NetAdapterAdvancedProperty -Name "Ethernet" | Select-Object DisplayName, DisplayValue | Format-Table -AutoSize

Write-Output ""
Write-Output "=== PROPIEDADES AVANZADAS DE WIFI (Intel) ==="
Get-NetAdapterAdvancedProperty -Name "Wi-Fi" | Select-Object DisplayName, DisplayValue | Format-Table -AutoSize

Write-Output ""
Write-Output "=== ESTADO FAST STARTUP ==="
$key = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" -Name HiberbootEnabled -ErrorAction SilentlyContinue
if ($key) {
    Write-Output ("Fast Startup (HiberbootEnabled): " + $key.HiberbootEnabled + " (1=activo, 0=desactivado)")
} else {
    Write-Output "No se encontro la clave de Fast Startup."
}
