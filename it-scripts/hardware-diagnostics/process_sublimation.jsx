// Photoshop Script for Sublimation (16cm, Mirror, Top of A4)
var imagePath = "C:/Users/corba/Downloads/ChatGPT Image 7 may 2026, 09_12_23 p.m..png";
var outputPath = "C:/Users/corba/Downloads/Compu/sublimacion_ceja.pdf";
var fileRef = new File(imagePath);

if (fileRef.exists) {
    app.displayDialogs = DialogModes.NO;
    var doc = app.open(fileRef);

    // Set units to cm
    app.preferences.rulerUnits = Units.CM;
    app.preferences.typeUnits = TypeUnits.PIXELS;

    // Resize to 16cm height (proportional)
    var currentHeight = doc.height.value;
    var currentWidth = doc.width.value;
    var ratio = 16 / currentHeight;
    var newWidth = currentWidth * ratio;
    
    doc.resizeImage(UnitValue(newWidth, "cm"), UnitValue(16, "cm"), 300, ResampleMethod.BICUBICSHARPER);

    // Mirror image
    doc.flipCanvas(Direction.HORIZONTAL);

    // Expand canvas to A4 (21 x 29.7 cm) from the top
    // Anchor at TOP means it expands downwards
    doc.resizeCanvas(UnitValue(21, "cm"), UnitValue(29.7, "cm"), AnchorPosition.TOPCENTER);

    // Flatten image
    doc.flatten();

    // Save as PDF
    var pdfSaveOptions = new PDFSaveOptions();
    pdfSaveOptions.alphaChannels = false;
    pdfSaveOptions.layers = false;
    pdfSaveOptions.preserveEditing = false;
    pdfSaveOptions.embedColorProfile = true;
    
    doc.saveAs(new File(outputPath), pdfSaveOptions, true, Extension.LOWERCASE);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    
    app.displayDialogs = DialogModes.ALL;
} else {
    alert("No se encontró la imagen: " + imagePath);
}
