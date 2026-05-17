with open('register_commands.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

lines[55] = '            {"name":"anio","type":4,"description":"Año (ej. 2026)","required":False}\n'
lines[257] = '            "description": "Año a finalizar (ej. 2026)",\n'

with open('register_commands.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
