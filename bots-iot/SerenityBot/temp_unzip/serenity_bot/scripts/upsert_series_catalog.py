import re
import sys
import unicodedata
from datetime import datetime

import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build


SPREADSHEET_KEY = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERIES_HEADERS = [
    "Nombre",
    "Canal_ID",
    "Link_Drive",
    "Folder_ID",
    "Categoria",
    "Idioma",
    "Fecha_Agregada",
    "Admin_ID",
    "Admin_Nombre",
]
WORKSHEET_HEADERS = [
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
CARPETAS_DRIVE = {
    "RAW": ["1_raw"],
    "Clean": ["2_clrd", "2_clean"],
    "Traduccion": ["3_traduccion", "3_tl", "tl"],
    "Edicion": ["4_type", "4_ts", "ts"],
    "Recorte": ["5_recortes"],
}

ITSUKI_ID = "1154257480734490664"
ITSUKI_NAME = "Itsuki"
CELESTE_ID = "1203552106041180220"
CELESTE_NAME = "Celeste"

TARGET_SERIES = [
    {
        "Nombre": "dama-obsesionada",
        "Canal_ID": "1459717197629755494",
        "Link_Drive": "https://drive.google.com/drive/folders/1epz8UzgZvAvE5SIhcvvZyqC-UZpwe7IK?usp=sharing",
        "Categoria": "+15",
        "Idioma": "Coreano",
        "Admin_ID": ITSUKI_ID,
        "Admin_Nombre": ITSUKI_NAME,
    },
    {
        "Nombre": "complejo-de-amigos",
        "Canal_ID": "1459717370460246026",
        "Link_Drive": "https://drive.google.com/drive/folders/1gHWgT2c5fFgHUG0lYk2Ni5zperYFdF3M?usp=drive_link",
        "Categoria": "+19",
        "Idioma": "Ingles",
        "Admin_ID": ITSUKI_ID,
        "Admin_Nombre": ITSUKI_NAME,
    },
    {
        "Nombre": "lagrimas-entre-flores-marchitas",
        "Canal_ID": "1459717770617950311",
        "Link_Drive": "https://drive.google.com/drive/folders/1I7YaaCbH49iS1XbBpT1dxkRaszAL0RBV?usp=drive_link",
        "Categoria": "+19",
        "Idioma": "Ingles",
        "Admin_ID": ITSUKI_ID,
        "Admin_Nombre": ITSUKI_NAME,
    },
    {
        "Nombre": "🔞la-tumba-del-cisne",
        "Canal_ID": "1459717687205826691",
        "Link_Drive": "https://drive.google.com/drive/folders/1ix1uGN87jMfNvGhJjqSzlgaQbA24mLZR?usp=drive_link",
        "Categoria": "+19",
        "Idioma": "Ingles",
        "Admin_ID": ITSUKI_ID,
        "Admin_Nombre": ITSUKI_NAME,
    },
    {
        "Nombre": "niña-impecable",
        "Canal_ID": "1480024679673626744",
        "Link_Drive": "https://drive.google.com/drive/folders/1_3rCNX5yxVATm-RaA7sGvSlscgEgEe_F?usp=drive_link",
        "Categoria": "+15",
        "Idioma": "Ingles",
        "Admin_ID": ITSUKI_ID,
        "Admin_Nombre": ITSUKI_NAME,
    },
    {
        "Nombre": "deja-de-ser-complaciente",
        "Canal_ID": "1459718286060290079",
        "Link_Drive": "https://drive.google.com/drive/folders/1izkZ-cTjFBApi55A82vPqKLpKR65jjNJ?usp=drive_link",
        "Categoria": "+15",
        "Idioma": "Coreano",
        "Admin_ID": ITSUKI_ID,
        "Admin_Nombre": ITSUKI_NAME,
    },
    {
        "Nombre": "una-familia-de-villanos-esta-en-contra-de-mi-autonomia",
        "Canal_ID": "1459718218771075172",
        "Link_Drive": "https://drive.google.com/drive/folders/18eI4gNM7qL4GiiXD8FTuFYG3Cg5-igEZ?usp=drive_link",
        "Categoria": "+15",
        "Idioma": "Coreano",
        "Admin_ID": ITSUKI_ID,
        "Admin_Nombre": ITSUKI_NAME,
    },
]


def normalize_text(value):
    return str(value or "").strip()


def normalize_drive_name(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def normalize_cap(value):
    text = normalize_text(value)
    if not text:
        return ""

    text = re.sub(r"\.[a-zA-Z0-9]+$", "", text)
    text = text.lower().replace("_", " ")
    patterns = [
        r"(?:cap(?:itulo)?|chapter|ch|episodio|ep)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)",
        r"(?:traduccion|traducción|trad|clean|clrd|edicion|edición|type|recorte|raw)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)",
        r"(\d+(?:[.-]\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace(".", "-")

    return normalize_text(value)


def order_cap(cap):
    parts = normalize_cap(cap).split("-")
    try:
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except Exception:
        return (0, 0)


def extract_folder_id(link):
    patterns = [r"folders/([a-zA-Z0-9_-]+)", r"id=([a-zA-Z0-9_-]+)"]
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    return ""


def get_services():
    sheets = gspread.service_account("credentials.json")
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json",
        scopes=DRIVE_SCOPES,
    )
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


def ensure_series_sheet_headers(sheet):
    headers = sheet.row_values(1)
    if headers != SERIES_HEADERS:
        if len(headers) < len(SERIES_HEADERS):
            missing = len(SERIES_HEADERS) - len(headers)
            sheet.add_cols(missing)
        sheet.update(values=[SERIES_HEADERS], range_name="A1:I1")


def ensure_series_rows(sheet, existing_rows):
    target_names = {item["Nombre"] for item in TARGET_SERIES}
    updates = []
    appended = 0

    for index, row in enumerate(existing_rows, start=2):
        nombre = normalize_text(row.get("Nombre"))
        if not nombre:
            continue

        if nombre == "atrapada-en-una-novela-romantica" or nombre in target_names:
            admin_id = ITSUKI_ID
            admin_name = ITSUKI_NAME
        else:
            admin_id = CELESTE_ID
            admin_name = CELESTE_NAME

        current_admin_id = normalize_text(row.get("Admin_ID"))
        current_admin_name = normalize_text(row.get("Admin_Nombre"))
        if current_admin_id != admin_id or current_admin_name != admin_name:
            updates.append({"range": f"H{index}:I{index}", "values": [[admin_id, admin_name]]})

    existing_by_channel = {normalize_text(row.get("Canal_ID")): row for row in existing_rows}

    for item in TARGET_SERIES:
        folder_id = extract_folder_id(item["Link_Drive"])
        values = [
            item["Nombre"],
            item["Canal_ID"],
            item["Link_Drive"],
            folder_id,
            item["Categoria"],
            item["Idioma"],
            datetime.now().strftime("%Y-%m-%d"),
            item["Admin_ID"],
            item["Admin_Nombre"],
        ]

        row = existing_by_channel.get(item["Canal_ID"])
        if row:
            row_index = existing_rows.index(row) + 2
            current_values = [
                normalize_text(row.get("Nombre")),
                normalize_text(row.get("Canal_ID")),
                normalize_text(row.get("Link_Drive")),
                normalize_text(row.get("Folder_ID")),
                normalize_text(row.get("Categoria")),
                normalize_text(row.get("Idioma")),
                normalize_text(row.get("Fecha_Agregada")),
                normalize_text(row.get("Admin_ID")),
                normalize_text(row.get("Admin_Nombre")),
            ]
            target_values = [str(v) for v in values]
            if current_values != target_values:
                updates.append({"range": f"A{row_index}:I{row_index}", "values": [values]})
        else:
            sheet.append_row(values)
            appended += 1

    if updates:
        sheet.batch_update(updates)

    return appended, len(updates)


def list_drive_items(service, folder_id, folders_only):
    mime_filter = (
        "mimeType='application/vnd.google-apps.folder'"
        if folders_only
        else "mimeType != 'application/vnd.google-apps.folder'"
    )
    result = service.files().list(
        q=f"'{folder_id}' in parents and {mime_filter} and trashed=false",
        fields="files(id,name)",
        orderBy="name",
    ).execute()
    return result.get("files", [])


def get_caps_from_drive(service, folder_id):
    caps = {stage: set() for stage in CARPETAS_DRIVE}
    principal = list_drive_items(service, folder_id, folders_only=True)

    for stage, aliases in CARPETAS_DRIVE.items():
        folder = next(
            (item for item in principal if any(alias in normalize_drive_name(item["name"]) for alias in aliases)),
            None,
        )
        if not folder:
            continue

        items = list_drive_items(service, folder["id"], folders_only=(stage != "Traduccion"))
        caps[stage] = {normalize_cap(item["name"]) for item in items if normalize_cap(item["name"])}

    return caps


def ensure_series_worksheet(spreadsheet, series_name):
    try:
        ws = spreadsheet.worksheet(series_name)
    except Exception:
        ws = spreadsheet.add_worksheet(title=series_name, rows=500, cols=len(WORKSHEET_HEADERS))
        ws.append_row(WORKSHEET_HEADERS)

    headers = ws.row_values(1)
    if headers != WORKSHEET_HEADERS:
        if len(headers) < len(WORKSHEET_HEADERS):
            ws.add_cols(len(WORKSHEET_HEADERS) - len(headers))
        ws.update(values=[WORKSHEET_HEADERS], range_name="A1:L1")
    return ws


def sync_series_worksheet(ws, caps_by_stage):
    raw_caps = caps_by_stage.get("RAW", set())
    if not raw_caps:
        return 0, 0

    rows = ws.get_all_records()
    updates = []
    rows_to_append = []
    existing = {}

    for idx, row in enumerate(rows, start=2):
        cap_original = normalize_text(row.get("Cap"))
        cap = normalize_cap(cap_original)
        if not cap:
            continue
        if cap not in existing:
            existing[cap] = idx
        if cap_original != cap:
            updates.append({"range": f"A{idx}", "values": [[cap]]})

    new_rows = 0
    for cap in sorted(raw_caps, key=order_cap):
        values = [
            cap,
            "",
            "✅" if cap in caps_by_stage.get("RAW", set()) else "❌",
            "✅" if cap in caps_by_stage.get("Clean", set()) else "❌",
            "✅" if cap in caps_by_stage.get("Traduccion", set()) else "❌",
            "✅" if cap in caps_by_stage.get("Edicion", set()) else "❌",
            "✅" if cap in caps_by_stage.get("Recorte", set()) else "❌",
            "❌",
            datetime.now().strftime("%Y-%m-%d"),
        ]
        if cap in existing:
            row_index = existing[cap]
            current_row = rows[row_index - 2]
            current_values = [
                normalize_text(current_row.get("RAW")),
                normalize_text(current_row.get("Clean")),
                normalize_text(current_row.get("Traduccion")),
                normalize_text(current_row.get("Edicion")),
                normalize_text(current_row.get("Recorte")),
            ]
            merged_values = [
                "✅" if current_values[0] == "✅" or values[2] == "✅" else "❌",
                "✅" if current_values[1] == "✅" or values[3] == "✅" else "❌",
                "✅" if current_values[2] == "✅" or values[4] == "✅" else "❌",
                "✅" if current_values[3] == "✅" or values[5] == "✅" else "❌",
                "✅" if current_values[4] == "✅" or values[6] == "✅" else "❌",
            ]
            if current_values != merged_values:
                updates.append({"range": f"C{row_index}:G{row_index}", "values": [merged_values]})
        else:
            rows_to_append.append(values)
            new_rows += 1

    if updates:
        ws.batch_update(updates)
    if rows_to_append:
        ws.append_rows(rows_to_append)

    return new_rows, len(updates)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    sheets_client, drive_service = get_services()
    spreadsheet = sheets_client.open_by_key(SPREADSHEET_KEY)
    series_sheet = spreadsheet.worksheet("Series")
    ensure_series_sheet_headers(series_sheet)

    existing_rows = series_sheet.get_all_records()
    appended, updated = ensure_series_rows(series_sheet, existing_rows)

    refreshed_rows = spreadsheet.worksheet("Series").get_all_records()
    refreshed_map = {normalize_text(row.get("Nombre")): row for row in refreshed_rows}

    print(f"Series agregadas: {appended}")
    print(f"Filas Series actualizadas: {updated}")
    print("Modo legacy desactivado: este script ya no crea ni sincroniza hojas por serie.")
    print("Usa las hojas por responsable y reconstruye con scripts/build_admin_views.py")


if __name__ == "__main__":
    main()
