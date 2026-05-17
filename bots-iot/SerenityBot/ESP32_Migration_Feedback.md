# Revisión de la Migración a ESP32 (SerenityStaff Lite)

Este documento contiene las correcciones críticas que se deben aplicar al código generado para el ESP32 y el Google Apps Script (GAS), además de notas importantes sobre integraciones pasadas.

## 1. Problemas Críticos a Corregir

Por favor, indica al hilo donde estás construyendo el código que realice las siguientes correcciones:

### 🔴 Problema A: Validación de Firma de Discord en Apps Script
**Contexto:** Discord **exige** que cualquier URL configurada en el portal de desarrolladores como "Interactions Endpoint URL" valide las firmas criptográficas Ed25519 de cada petición.
**El Error:** Google Apps Script no soporta la validación de firmas Ed25519 de forma nativa sin librerías de terceros (y es difícil de implementar allí). Por lo tanto, Discord rechazará la URL del GAS.
**La Solución requerida:** Tienen que implementar un pequeño proxy intermediario (la mejor opción gratuita es **Cloudflare Workers**) que reciba el Webhook de Discord, valide la firma Ed25519 y luego envíe la petición al Google Apps Script. 

### 🔴 Problema B: Doble Callback en `main.py`
**Contexto:** En `Code.gs` (Apps Script), cuando llega un comando de Discord, se devuelve inmediatamente un JSON con `{ type: 5 }` (que significa "Deferred" o "Pensando..."). Esto le indica a Discord que el bot recibió el comando.
**El Error:** En `main.py`, la función `send_response` intenta llamar a `respond_interaction` (que envía un `{ type: 4 }`). Discord no permite dos respuestas a la misma interacción y lanzará un error `400 Bad Request: Interaction has already been acknowledged`.
**La Solución requerida:** En `main.py`, se debe usar `send_followup` en lugar de `respond_interaction` si el comando ya fue diferido por el Apps Script.

### 🔴 Problema C: Error al buscar IDs en Sheets (`_rowNum` vs `_rowId`)
**Contexto:** En el GAS, al leer las filas, se inyecta la propiedad `_rowNum`.
**El Error:** En `comandos.py` de Python (líneas 143, 329, 350), se está intentando buscar la fila usando `row_id = asignacion.get('_rowId') or asignacion.get('id')`. Esto devuelve `None`, rompiendo los comandos `/terminado`, `/abandonar` y `/cancelar_asignacion`.
**La Solución requerida:** Reemplazar esa línea en todo `comandos.py` por `row_id = asignacion.get('_rowNum')`.

---

## 2. Sobre el "Traductor en Drive / Sheets"

Me preguntaste si el sistema del traductor que hicimos antes estaba integrado:

**Respuesta:** En el código actual de `SerenityStaff_Lite` que acabo de revisar, **NO está integrado** el sistema de traducción automática o generación de documentos (Google Docs) traducidos. 

Como me indicaste que no quieres que tenga la función de traducción de capítulos, el código está perfecto en ese sentido. Esa función ha sido descartada para mantener la arquitectura lo más ligera y limpia posible, ideal para el ESP32.
