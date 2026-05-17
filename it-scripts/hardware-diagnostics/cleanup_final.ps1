# Desactivar ASPM
powercfg /setacvalueindex SCHEME_CURRENT SUB_PCIEXPRESS ASPM 0
powercfg /setdcvalueindex SCHEME_CURRENT SUB_PCIEXPRESS ASPM 0
powercfg /setactive SCHEME_CURRENT

# Limpiar BCD huerfano
bcdedit /delete {e6808458-3d60-11ee-a042-fb1a90ed8d65} /cleanup
bcdedit /delete {e680845b-3d60-11ee-a042-fb1a90ed8d65} /cleanup

Write-Host "ASPM desactivado y BCD limpio."
Start-Sleep -Seconds 3
