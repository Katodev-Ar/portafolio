# 📝 CorrectorTraducciones

**Corrector automatizado de textos traducidos e inyector de nodos XML OpenXML para archivos Word.**

## 📋 Descripción
Suite de corrección y formateo de textos traducidos para novelas web. Incluye un corrector masivo compilable como ejecutable standalone y un inyector especializado de nodos XML OpenXML que supera las limitaciones nativas de `python-docx` para formatear bloques de estadísticas OCR complejos.

## 🚀 Características
- **Corrector masivo** de textos traducidos con reglas de estilo y ortografía
- **Compilable como .exe** standalone via script batch (`compilar_corrector.bat`)
- **Inyector XML OpenXML (`pulir_solo_leveling_completo.py`):**
  - Crea nodos XML de párrafo (`OxmlElement('w:p')`) e los inyecta en el árbol DOM del documento Word usando `paragraph._p.addnext()` de lxml
  - Permite insertar párrafos exactamente después de una ubicación específica, algo imposible con la API de alto nivel de `python-docx`
  - Reformatea bloques de estadísticas y perfiles de personajes que estaban colapsados en líneas únicas por errores de OCR

## 💻 Tecnologías
- Python 3, python-docx, lxml
- Batch scripting (compilación)
