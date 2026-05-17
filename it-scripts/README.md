# 🔧 Scripts de Diagnóstico IT

**Suite de herramientas forenses en PowerShell para diagnóstico de hardware y optimización de sistemas**

## ¿Qué hacen?
Colección de scripts avanzados de PowerShell diseñados para realizar diagnósticos a bajo nivel de componentes de hardware (discos NVMe/SATA), reparación de bootloaders UEFI, y optimización de rendimiento del sistema operativo.

## Scripts incluidos
- **Diagnóstico NVMe/SATA**: Lectura de atributos SMART, detección de sectores dañados, análisis de errores CRC.
- **Reparación UEFI**: Migración de bootloaders EFI entre discos, limpieza de entradas BCD huérfanas.
- **Secure Erase**: Ejecución de borrado seguro a nivel firmware en unidades NVMe.
- **Optimización de Sistema**: Análisis de procesos, gestión de memoria RAM, limitación de WSL/Docker.
- **Scripts de Photoshop (JSX)**: Automatización de exportación y procesamiento de imágenes.

## Tecnologías
- PowerShell 5.1+
- Windows Management Instrumentation (WMI/CIM)
- DiskPart y StorageReliabilityCounter
- Adobe ExtendScript (JSX)
