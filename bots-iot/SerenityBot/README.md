# 🤖 SerenityBot

**Bot de Discord para gestión automatizada de staff con sincronización en tiempo real**

## ¿Qué hace?
SerenityBot es un bot avanzado de Discord diseñado para coordinar equipos de trabajo (moderadores, editores, traductores) de forma completamente automática. Gestiona asignaciones de tareas, seguimiento de actividad y reportes de rendimiento, sincronizando todo en tiempo real con Google Sheets.

## Problema que resuelve
Coordinar manualmente a un equipo distribuido de colaboradores generaba caos organizativo, tareas perdidas y falta de seguimiento de la actividad. SerenityBot **automatizó por completo la gestión**, gestionando asignaciones, recordatorios y reportes centralizados.

## Versiones
- **SerenityBot Full** — Versión completa con todas las funcionalidades (discord.py)
- **SerenityStaff_Lite** — Versión ligera optimizada para migración a hardware embebido
- **ESP32_PC_Link** — Módulo de control de hardware físico (ver proyecto separado)

## Métricas
- 👥 **30 miembros de staff y 4 coordinadores** gestionados de forma completamente automatizada
- 📊 Sincronización en **tiempo real** con Google Sheets
- 🔄 Asignación automática de tareas y seguimiento de completación

## Tecnologías
- Python 3
- discord.py (API de Discord)
- Google Sheets API (gspread)
- SQLite para almacenamiento local
- Arquitectura modular con Cogs

## Estructura
```
SerenityBot/
├── main.py / full_main.py    # Punto de entrada
├── staff_cog.py              # Módulo de gestión de staff
├── database_staff.py         # Capa de base de datos
├── excel_staff.py            # Integración con Google Sheets
├── test_api.py               # Tests de la API
└── requirements.txt          # Dependencias
```

## Seguridad
> ⚠️ Este repositorio no incluye archivos de credenciales (.env, credentials.json, token.json). 
> Para ejecutarlo, necesitarás configurar tus propias API keys de Discord y Google Sheets.
