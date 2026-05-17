# ⚡ ESP32_PC_Link

**Control remoto de PC desde un microcontrolador ESP32-S3 con MicroPython**

## ¿Qué hace?
ESP32_PC_Link permite encender, apagar y controlar una computadora de forma remota utilizando un microcontrolador ESP32-S3 programado en MicroPython. El dispositivo se comunica mediante HTTPS con APIs externas y puede activar relés físicos para controlar el encendido del equipo (Wake-on-LAN + relé de power).

## Problema que resuelve
Mantener un servidor o PC encendido 24/7 solo para ejecutar un bot de Discord era costoso e innecesario. Este proyecto **eliminó el 100% del costo de servidor** al mover la lógica de red a un microcontrolador de bajo consumo (~0.5W vs ~150W del PC).

## Tecnologías
- MicroPython (ESP32-S3)
- HTTPS asíncrono (urequests)
- Control de relés GPIO
- WiFi Manager para configuración de red
- Wake-on-LAN

## Estructura
```
ESP32_PC_Link/
├── main.py           # Lógica principal del microcontrolador
├── boot.py           # Secuencia de arranque
├── config.py         # Configuración WiFi y endpoints
└── wifi_manager.py   # Gestión de conexión WiFi
```
