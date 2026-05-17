Write-Output "======================================"
Write-Output "  VERIFICACION PRE-REINICIO (DOBLE CHECK)"
Write-Output "======================================"

# CHECK 1: Verificar que la particion EFI nueva existe en Disco 0
Write-Output "`n[CHECK 1] Particiones actuales del Disco 0 (tu disco principal de 1TB):"
Get-Partition -DiskNumber 0 | Select-Object PartitionNumber, DriveLetter, Size, Type, IsSystem, IsBoot, IsHidden | Format-Table -AutoSize | Out-String | Write-Output

# CHECK 2: Verificar que la particion S: es accesible y tiene archivos EFI
Write-Output "[CHECK 2] Contenido de la particion EFI nueva (S:\EFI):"
if (Test-Path "S:\EFI") {
    Get-ChildItem -Path "S:\EFI" -Recurse -ErrorAction SilentlyContinue | Select-Object FullName, Length | Format-Table -AutoSize | Out-String | Write-Output
    Write-Output "   >> RESULTADO: Los archivos de arranque EXISTEN en la nueva particion."
} else {
    Write-Output "   >> ERROR CRITICO: No se encontro la carpeta S:\EFI. NO reiniciar."
}

# CHECK 3: Verificar el archivo bootmgfw.efi especificamente
Write-Output "`n[CHECK 3] Archivo critico de arranque (BOOTMGFW.EFI):"
$bootFile = "S:\EFI\Microsoft\Boot\bootmgfw.efi"
if (Test-Path $bootFile) {
    $file = Get-Item $bootFile
    Write-Output "   >> ENCONTRADO: $($file.FullName)"
    Write-Output "   >> Tamano: $([math]::Round($file.Length / 1KB, 2)) KB"
    Write-Output "   >> Fecha de creacion: $($file.CreationTime)"
    Write-Output "   >> RESULTADO: CORRECTO"
} else {
    Write-Output "   >> ERROR CRITICO: bootmgfw.efi NO encontrado. NO reiniciar."
}

# CHECK 4: Verificar que BCD apunta al volumen correcto
Write-Output "`n[CHECK 4] Verificando BCD Store (gestor de arranque):"
$bcdOutput = bcdedit /enum "{bootmgr}" 2>&1
Write-Output $bcdOutput

# CHECK 5: Verificar a que disco fisico pertenece el volumen S:
Write-Output "`n[CHECK 5] Identificando a que disco fisico pertenece S:"
$sPartition = Get-Partition -DriveLetter S -ErrorAction SilentlyContinue
if ($sPartition) {
    Write-Output "   >> Letra: S:"
    Write-Output "   >> Disco Fisico: Disco $($sPartition.DiskNumber)"
    Write-Output "   >> Particion #: $($sPartition.PartitionNumber)"
    Write-Output "   >> Tipo: $($sPartition.Type)"
    Write-Output "   >> IsSystem: $($sPartition.IsSystem)"
    if ($sPartition.DiskNumber -eq 0) {
        Write-Output "   >> RESULTADO: CORRECTO - La particion EFI esta en el Disco 0 (tu disco sano de 1TB)"
    } else {
        Write-Output "   >> ADVERTENCIA: La particion EFI esta en Disco $($sPartition.DiskNumber), NO en el Disco 0"
    }
} else {
    Write-Output "   >> No se encontro la particion S:"
}

# CHECK 6: Verificar que C:\Windows existe y esta intacto
Write-Output "`n[CHECK 6] Verificando integridad de C:\Windows:"
if (Test-Path "C:\Windows\System32\winload.efi") {
    Write-Output "   >> winload.efi: PRESENTE"
} else {
    Write-Output "   >> ERROR: winload.efi NO encontrado"
}
if (Test-Path "C:\Windows\System32\ntoskrnl.exe") {
    Write-Output "   >> ntoskrnl.exe (kernel): PRESENTE"
} else {
    Write-Output "   >> ERROR: ntoskrnl.exe NO encontrado"
}
Write-Output "   >> RESULTADO: Archivos criticos del sistema intactos."

# CHECK 7: Verificar la entrada BCD del sistema operativo actual
Write-Output "`n[CHECK 7] Entrada BCD del sistema operativo actual:"
$bcdCurrent = bcdedit /enum "{current}" 2>&1
Write-Output $bcdCurrent

# RESUMEN FINAL
Write-Output "`n======================================"
Write-Output "  RESUMEN FINAL DE VERIFICACION"
Write-Output "======================================"
$allGood = $true
if (-not (Test-Path "S:\EFI\Microsoft\Boot\bootmgfw.efi")) { $allGood = $false }
if (-not (Test-Path "C:\Windows\System32\winload.efi")) { $allGood = $false }
$sPart = Get-Partition -DriveLetter S -ErrorAction SilentlyContinue
if (-not $sPart -or $sPart.DiskNumber -ne 0) { $allGood = $false }

if ($allGood) {
    Write-Output ">> TODOS LOS CHECKS PASARON CORRECTAMENTE."
    Write-Output ">> ES SEGURO REINICIAR LA COMPUTADORA."
} else {
    Write-Output ">> ALGUN CHECK FALLO. NO REINICIAR."
}
