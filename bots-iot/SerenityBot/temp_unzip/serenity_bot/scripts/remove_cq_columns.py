import sys

import gspread


SPREADSHEET_KEY = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk"
TARGET_HEADERS = [
    "Cap",
    "Idioma",
    "RAW",
    "Clean",
    "Traduccion",
    "Edicion",
    "Recorte",
    "Subido_Web",
    "Fecha_RAW",
]
CQ_HEADERS = {"CQ_Clean", "CQ_Traduc", "CQ_Edicion"}


def is_series_sheet(headers):
    return headers[:3] == ["Cap", "Idioma", "RAW"]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    client = gspread.service_account("credentials.json")
    spreadsheet = client.open_by_key(SPREADSHEET_KEY)

    touched = 0
    for ws in spreadsheet.worksheets():
        headers = ws.row_values(1)
        if not headers or not is_series_sheet(headers):
            continue

        if not any(header in CQ_HEADERS for header in headers):
            continue

        while True:
            headers = ws.row_values(1)
            cq_indexes = [idx for idx, header in enumerate(headers, start=1) if header in CQ_HEADERS]
            if not cq_indexes:
                break
            ws.delete_columns(min(cq_indexes), max(cq_indexes))

        ws.update(values=[TARGET_HEADERS], range_name="A1:I1")
        touched += 1
        print(f"Limpieza CQ aplicada: {ws.title}")

    print(f"Hojas limpiadas: {touched}")


if __name__ == "__main__":
    main()
