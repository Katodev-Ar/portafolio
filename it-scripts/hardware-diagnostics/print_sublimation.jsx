// Photoshop Script to Save as PDF for Sublimation
var imagePath = "C:/Users/corba/Downloads/ChatGPT Image 7 may 2026, 12_22_57 a.m..png";
var outputPath = "C:/Users/corba/Downloads/Compu/impresion_sublimacion.pdf";
var fileRef = new File(imagePath);

if (fileRef.exists) {
    var doc = app.open(fileRef);

    // Set units
    app.preferences.rulerUnits = Units.CM;

    // 1. Resize to 16cm height
    var newHeight = 16;
    var ratio = newHeight / doc.height.value;
    var newWidth = doc.width.value * ratio;
    doc.resizeImage(UnitValue(newWidth, "cm"), UnitValue(newHeight, "cm"), 300, ResampleMethod.BICUBICSMOOTHER);

    // 2. Mirror
    doc.flipCanvas(Direction.HORIZONTAL);

    // 3. Canvas to A4 - Anchor TOP
    doc.resizeCanvas(UnitValue(21, "cm"), UnitValue(29.7, "cm"), AnchorPosition.TOPCENTER);

    // 4. Flatten
    doc.flatten();

    // 5. Save as PDF
    var pdfSaveOptions = new PDFSaveOptions();
    pdfSaveOptions.alphaChannels = false;
    pdfSaveOptions.embedColorProfile = true;
    pdfSaveOptions.optimizeForWeb = false;
    pdfSaveOptions.preserveEditing = false;
    
    doc.saveAs(new File(outputPath), pdfSaveOptions, true, Extension.LOWERCASE);
    doc.close(SaveOptions.DONOTSAVECHANGES);

    alert("PDF CREADO CON ÉXITO:\n" + outputPath + "\n\nAhora lo mandaré a imprimir automáticamente.");
} else {
    alert("No se encontró la imagen.");
}
