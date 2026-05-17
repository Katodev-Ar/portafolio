# 🖼️ BloomStitch

**Pipeline de procesamiento masivo de imágenes manga**

## ¿Qué hace?
BloomStitch es un sistema automatizado que toma cientos de imágenes fuente (páginas de manga en formato PSD o imagen), las une verticalmente en tiras continuas, las corta en segmentos exactos de 10,000px de alto y las convierte a formato WebP lossless para distribución web optimizada.

## Problema que resuelve
Procesar manualmente las imágenes de un solo capítulo de manga tomaba **entre 30 y 60 minutos**. Con BloomStitch, el mismo trabajo se completa en **menos de 2 minutos**, logrando una **reducción del 95% en tiempo de procesamiento**.

## Métricas
- 📦 **+15 versiones** de desarrollo (v55 → v907)
- 🖼️ **+1,000 imágenes/mes** procesadas de forma estable
- ⚡ **95% de reducción** en tiempo de procesamiento manual en comparación con el flujo anterior

## Tecnologías
- Python 3
- Pillow (PIL) para manipulación de imágenes
- Procesamiento por lotes y manejo de memoria optimizado
- Formato de salida: WebP lossless con altura fija de 10,000px

## Estructura
```
BloomStitch/
├── main.py              # Punto de entrada principal
├── stitch.py            # Lógica de pegado vertical
├── slicer.py            # Corte en segmentos de 10K px
├── converter.py         # Conversión a WebP
└── config.py            # Configuración de rutas y parámetros
```
