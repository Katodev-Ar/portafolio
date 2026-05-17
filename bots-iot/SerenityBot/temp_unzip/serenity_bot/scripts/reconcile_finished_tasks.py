import re
import sys
import unicodedata
from collections import defaultdict

import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build


SPREADSHEET_KEY = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CARPETAS_DRIVE = {
    "RAW": "1_RAW",
    "Clean": "2_CLRD",
    "Traduccion": "3_TRADUCCION",
    "Edicion": "4_TYPE",
    "Recorte": "5_RECORTES",
}
ROLE_TO_COLUMN = {
    "Cleaner": 4,
    "Traductor": 5,
    "Editor": 6,
}


def normalize_text(value):
    return str(value or "").strip()


def normalize_project(value):
    return normalize_text(value).lower()


def normalize_role(value):
    return normalize_text(value)


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


def normalize_drive_name(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def drive_folder_matches(stage, folder_name):
    folder_normalized = normalize_drive_name(folder_name)
    aliases = {
        "RAW": ["1_raw"],
        "Clean": ["2_clrd", "2_clean"],
        "Traduccion": ["3_traduccion", "3_tl", "tl"],
        "Edicion": ["4_type", "4_ts", "ts"],
        "Recorte": ["5_recortes"],
    }
    return any(alias in folder_normalized for alias in aliases.get(stage, []))


def get_client():
    return gspread.service_account("credentials.json")


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json",
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=creds)


def list_drive_items(service, folder_id, folders_only):
    mime_filter = (
        "mimeType='application/vnd.google-apps.folder'"
        if folders_only
        else "mimeType != 'application/vnd.google-apps.folder'"
    )
    result = service.files().list(
        q=f"'{folder_id}' in parents and {mime_filter} and trashed=false",
        fields="files(id, name)",
        orderBy="name",
    ).execute()
    return result.get("files", [])


def get_caps_from_drive(service, folder_id_principal):
    caps_por_etapa = {etapa: set() for etapa in CARPETAS_DRIVE}

    principal_folders = list_drive_items(service, folder_id_principal, folders_only=True)

    for etapa, folder_name in CARPETAS_DRIVE.items():
        target = next(
            (folder for folder in principal_folders if drive_folder_matches(etapa, folder["name"])),
            None,
        )
        if not target:
            continue

        items = list_drive_items(service, target["id"], folders_only=(etapa != "Traduccion"))
        caps_por_etapa[etapa] = {
            normalize_cap(item["name"])
            for item in items
            if normalize_cap(item["name"])
        }

    return caps_por_etapa


def collect_finished_records(spreadsheet):
    finished = set()

    registro = spreadsheet.worksheet("Registro")
    registro_rows = registro.get_all_records()
    for row in registro_rows:
        finished.add(
            (
                normalize_project(row.get("Proyecto")),
                normalize_cap(row.get("Capítulo")),
                normalize_role(row.get("Tarea")),
            )
        )

    asignaciones = spreadsheet.worksheet("Asignaciones")
    asig_rows = asignaciones.get_all_records()
    asig_updates = []

    for row_index, row in enumerate(asig_rows, start=2):
        cap_normalized = normalize_cap(row.get("Capítulo"))
        current_cap = normalize_text(row.get("Capítulo"))
        if cap_normalized and current_cap != cap_normalized:
            asig_updates.append({"range": f"B{row_index}", "values": [[cap_normalized]]})

        if normalize_text(row.get("Estado")) == "Terminado":
            finished.add(
                (
                    normalize_project(row.get("Proyecto")),
                    cap_normalized,
                    normalize_role(row.get("Tarea")),
                )
            )

    if asig_updates:
        asignaciones.batch_update(asig_updates)

    reg_updates = []
    for row_index, row in enumerate(registro_rows, start=2):
        cap_normalized = normalize_cap(row.get("Capítulo"))
        current_cap = normalize_text(row.get("Capítulo"))
        if cap_normalized and current_cap != cap_normalized:
            reg_updates.append({"range": f"D{row_index}", "values": [[cap_normalized]]})

    if reg_updates:
        registro.batch_update(reg_updates)

    return finished, len(reg_updates), len(asig_updates)


def reconcile_series(spreadsheet, finished):
    series_sheet = spreadsheet.worksheet("Series")
    series_rows = series_sheet.get_all_records()
    drive_service = get_drive_service()

    summary = defaultdict(lambda: {"caps_normalized": 0, "marked_done": 0})

    for row in series_rows:
        series_name = normalize_text(row.get("Nombre"))
        folder_id = normalize_text(row.get("Folder_ID"))
        if not series_name:
            continue

        try:
            sheet = spreadsheet.worksheet(series_name)
        except Exception:
            continue

        caps_drive = get_caps_from_drive(drive_service, folder_id) if folder_id else {}
        sheet_rows = sheet.get_all_records()
        updates = []

        for row_index, sheet_row in enumerate(sheet_rows, start=2):
            cap_raw = sheet_row.get("Cap")
            cap_normalized = normalize_cap(cap_raw)
            if not cap_normalized:
                continue

            current_cap = normalize_text(cap_raw)
            if current_cap != cap_normalized:
                updates.append({"range": f"A{row_index}", "values": [[cap_normalized]]})
                summary[series_name]["caps_normalized"] += 1

            for role_name, column in ROLE_TO_COLUMN.items():
                key = (normalize_project(series_name), cap_normalized, role_name)
                stage_name = {4: "Clean", 5: "Traduccion", 6: "Edicion"}[column]
                exists_in_drive = cap_normalized in caps_drive.get(stage_name, set())
                if (key in finished or exists_in_drive) and normalize_text(sheet_row.get(stage_name)) != "✅":
                    col_letter = chr(ord("A") + column - 1)
                    updates.append({"range": f"{col_letter}{row_index}", "values": [["✅"]]})
                    summary[series_name]["marked_done"] += 1

        if updates:
            sheet.batch_update(updates)

    return summary


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    client = get_client()
    spreadsheet = client.open_by_key(SPREADSHEET_KEY)

    finished, reg_updates, asig_updates = collect_finished_records(spreadsheet)
    summary = reconcile_series(spreadsheet, finished)

    print(f"Registros normalizados: {reg_updates}")
    print(f"Asignaciones normalizadas: {asig_updates}")
    print(f"Trabajos terminados detectados: {len(finished)}")

    touched_series = 0
    for series_name, data in summary.items():
        if data["caps_normalized"] or data["marked_done"]:
            touched_series += 1
            print(
                f"{series_name}: caps normalizados={data['caps_normalized']}, "
                f"marcados terminado={data['marked_done']}"
            )

    print(f"Hojas de serie actualizadas: {touched_series}")


if __name__ == "__main__":
    main()
