# -*- coding: utf-8 -*-
path = r'c:\Users\corba\Downloads\_Organizado\Pendiente Revisar\Serenity bot\ESP32_PC_Link\Serenity_Web\index.html'

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines 108-110 (0-indexed 107-109) are Atajos, Pantalla, Procesos buttons
# Replace with: Minimizar, Silenciar, Pantalla, Procesos, Mas
new_buttons = [
    "    <button class=\"btn\" data-when=\"on\" onclick=\"doAction('minimize_all')\"><span class=\"ico\">&#128377;</span>Minimizar</button>\n",
    "    <button class=\"btn\" data-when=\"on\" onclick=\"doAction('volume_mute')\"><span class=\"ico\">&#128263;</span>Silenciar</button>\n",
    "    <button class=\"btn\" data-when=\"on\" onclick=\"showScreen()\"><span class=\"ico\">&#128250;</span>Pantalla</button>\n",
    "    <button class=\"btn\" data-when=\"on\" onclick=\"showProcs()\"><span class=\"ico\">&#128187;</span>Procesos</button>\n",
    "    <button class=\"btn btn-shortcuts\" data-when=\"on\" onclick=\"$('modal-shortcuts').style.display='flex'\"><span class=\"ico\">&#9881;</span>M\u00e1s</button>\n",
]

lines[107:110] = new_buttons

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Done! Replaced 3 lines with {len(new_buttons)} lines. Total: {len(lines)}")
