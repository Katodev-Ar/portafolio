// Photoshop Script to Export JPG for Printing
var imagePath = "C:/Users/corba/Downloads/ChatGPT Image 7 may 2026, 12_22_57 a.m..png";
var outputPath = "C:/Users/corba/Downloads/Compu/impresion_sublimacion.jpg";
var fileRef = new File(imagePath);

if (fileRef.exists) {
    var doc = app.open(fileRef);
    app.preferences.rulerUnits = Units.CM;
    
    doc.resizeImage(UnitValue(16, "cm"), undefined, 300, ResampleMethod.BICUBICSMOOTHER);
    doc.flipCanvas(Direction.HORIZONTAL);
    doc.resizeCanvas(UnitValue(21, "cm"), UnitValue(29.7, "cm"), AnchorPosition.TOPCENTER);
    doc.flatten();

    var jpgSaveOptions = new JPEGSaveOptions();
    jpgSaveOptions.embedColorProfile = true;
    jpgSaveOptions.formatOptions = FormatOptions.STANDARDBASELINE;
    jpgSaveOptions.matte = MatteType.NONE;
    jpgSaveOptions.quality = 12;

    doc.saveAs(new File(outputPath), jpgSaveOptions, true, Extension.LOWERCASE);
    doc.close(SaveOptions.DONOTSAVECHANGES);
}
