$ws = New-Object -ComObject WScript.Shell
$startupPath = [Environment]::GetFolderPath('Startup')
$shortcut = $ws.CreateShortcut("$startupPath\ESP32_PC_Agent.lnk")
$shortcut.TargetPath = "C:\Users\corba\Downloads\_Organizado\Pendiente Revisar\Serenity bot\ESP32_PC_Link\pc_agent\Start_PC_Agent.bat"
$shortcut.WorkingDirectory = "C:\Users\corba\Downloads\_Organizado\Pendiente Revisar\Serenity bot\ESP32_PC_Link\pc_agent"
$shortcut.WindowStyle = 7
$shortcut.Description = "ESP32 PC Link Agent"
$shortcut.Save()
Write-Host "Shortcut creado en: $startupPath\ESP32_PC_Agent.lnk"
