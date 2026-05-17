$targetDir = "C:\Users\corba\Downloads"
$outputFile = "C:\Users\corba\Downloads\Compu\project_scan_results.txt"

Write-Host "Iniciando escaneo de proyectos en $targetDir..."
# Buscamos carpetas que contengan archivos de codigo comunes y guardamos sus nombres y algunos archivos clave
$codeExtensions = @("*.py", "*.php", "*.js", "*.html", "*.cpp", "*.ino", "*.ps1")
$results = @()

$folders = Get-ChildItem -Path $targetDir -Directory -Recurse -Depth 4 -ErrorAction SilentlyContinue | Where-Object {
    # Evitar carpetas muy comunes o temporales
    $_.FullName -notmatch "\\node_modules" -and $_.FullName -notmatch "\\\.git" -and $_.FullName -notmatch "\\vendor"
}

foreach ($folder in $folders) {
    $files = Get-ChildItem -Path $folder.FullName -Include $codeExtensions -Recurse -Depth 1 -File -ErrorAction SilentlyContinue
    if ($files.Count -gt 0) {
        $extensions = ($files | Select-Object Extension -Unique).Extension -join ", "
        $fileNames = ($files | Select-Object Name -First 5).Name -join ", "
        $results += [PSCustomObject]@{
            Folder = $folder.Name
            Path = $folder.FullName
            FileTypes = $extensions
            SampleFiles = $fileNames
            TotalFiles = $files.Count
        }
    }
}

$results | Sort-Object TotalFiles -Descending | Select-Object -First 30 | Format-Table -AutoSize | Out-File -FilePath $outputFile -Encoding utf8
Write-Host "Escaneo completado. Resultados guardados en $outputFile"
