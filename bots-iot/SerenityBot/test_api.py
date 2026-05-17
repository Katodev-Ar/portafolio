import requests

URL = "https://script.google.com/macros/s/AKfycby36VIxUtlFdc3kQnU0GEI2Sg6K0O_QhT_P1mLGFFKvMB0lNdvjkvQGqSq1Uf9BeOJk/exec"

test_data = {
    "action": "asignar",
    "proyecto": "TEST_ESP32",
    "capitulo": "99",
    "tarea": "Editor",
    "usuario": "Robot_Antigravity",
    "userId": "007"
}

try:
    print("RUN: Intentando conectar con el Apps Script...")
    r = requests.post(URL, json=test_data, timeout=10)
    print(f"DONE: Respuesta: {r.text}")
except Exception as e:
    print(f"ERROR: {e}")
