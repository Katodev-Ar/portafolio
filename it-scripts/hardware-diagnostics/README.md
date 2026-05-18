# 🔧 Scripts de Diagnóstico IT & Hardware Forensics

**Suite de scripts forenses y de diagnóstico para discos NVMe/SATA, reparación de bootloaders UEFI y optimización de sistemas Windows.**

## 📋 Descripción
Colección de 25 scripts PowerShell especializados en diagnóstico forense de hardware, recuperación de sistemas de arranque y optimización avanzada de rendimiento en Windows. Incluye herramientas que operan a nivel de firmware y sectores de disco mediante inyecciones de C# inline con Win32 P-Invoke.

## 🚀 Herramientas Destacadas

### 🔬 nvme_deep_scan.ps1
Scanner forense de bloques de disco que compila clases C# inline con `Add-Type` para invocar las funciones nativas de Win32 `CreateFile` y `ReadFile`. Lee sectores crudos LBA directamente desde `\\.\PhysicalDriveN` con el flag `FILE_FLAG_NO_BUFFERING` para evitar los cachés del sistema operativo y obtener lecturas directas de NAND.

### 💥 nvme_secure_erase.ps1
Ejecutor de borrado seguro a nivel de firmware que verifica modelos y particiones EFI activas antes de enviar señales de formato directo (`Reset-PhysicalDisk`) al controlador NVMe para regenerar celdas NAND degradadas.

### 🛠️ full_forensics_v2.ps1
Suite completa de diagnóstico que incluye análisis SMART, verificación de particiones GPT/MBR, escaneo de sectores defectuosos y reportes detallados.

### 🔄 verify_boot.ps1 / fix_boot.ps1
Herramientas de diagnóstico y reparación de bootloaders UEFI para resolver problemas de arranque dual y restaurar la cadena de arranque BCD.

## 💻 Tecnologías
- PowerShell 5.1+
- C# Inline (Add-Type) con Win32 P-Invoke
- Windows Management Instrumentation (WMI/CIM)
- DiskPart, BCDEdit, Windows Storage API
