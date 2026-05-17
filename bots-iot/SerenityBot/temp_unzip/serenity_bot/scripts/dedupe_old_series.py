import re
import sys
from collections import defaultdict

import gspread


SPREADSHEET_KEY = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk"
HEADERS = ["Cap", "Idioma", "RAW", "Clean", "Traduccion", "Edicion", "Recorte", "Subido_Web", "Fecha_RAW"]
CHECK_FIELDS = ["RAW", "Clean", "Traduccion", "Edicion", "Recorte", "Subido_Web"]
NEW_SERIES = {
    "dama-obsesionada",
    "complejo-de-amigos",
    "lagrimas-entre-flores-marchitas",
    "🔞la-tumba-del-cisne",
    "niña-impecable",
    "deja-de-ser-complaciente",
    "una-familia-de-villanos-esta-en-contra-de-mi-autonomia",
}


def normalize_text(value):
    return str(value or "").strip()


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
        return (999999, 999999)


def merge_rows(rows):
    merged = {}
    for row in rows:
        cap = normalize_cap(row.get("Cap"))
        if not cap:
            continue

        if cap not in merged:
            merged[cap] = {
                "Cap": cap,
                "Idioma": normalize_text(row.get("Idioma")),
                "RAW": "❌",
                "Clean": "❌",
                "Traduccion": "❌",
                "Edicion": "❌",
                "Recorte": "❌",
                "Subido_Web": "❌",
                "Fecha_RAW": normalize_text(row.get("Fecha_RAW")),
            }

        current = merged[cap]
        if not current["Idioma"] and normalize_text(row.get("Idioma")):
            current["Idioma"] = normalize_text(row.get("Idioma"))

        for field in CHECK_FIELDS:
            if normalize_text(row.get(field)) == "✅":
                current[field] = "✅"

        fecha = normalize_text(row.get("Fecha_RAW"))
        if fecha and (not current["Fecha_RAW"] or fecha < current["Fecha_RAW"]):
            current["Fecha_RAW"] = fecha

    return [merged[cap] for cap in sorted(merged.keys(), key=order_cap)]


def has_duplicates(rows):
    counts = defaultdict(int)
    for row in rows:
        cap = normalize_cap(row.get("Cap"))
        if cap:
            counts[cap] += 1
    return any(count > 1 for count in counts.values())


def worksheet_is_series(headers):
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
        if ws.title in NEW_SERIES:
            continue

        headers = ws.row_values(1)
        if not worksheet_is_series(headers):
            continue

        rows = ws.get_all_records()
        if not has_duplicates(rows):
            continue

        merged_rows = merge_rows(rows)
        values = [HEADERS] + [
            [
                row["Cap"],
                row["Idioma"],
                row["RAW"],
                row["Clean"],
                row["Traduccion"],
                row["Edicion"],
                row["Recorte"],
                row["Subido_Web"],
                row["Fecha_RAW"],
            ]
            for row in merged_rows
        ]

        total_rows = max(len(rows) + 1, len(values))
        ws.batch_clear([f"A1:I{total_rows}"])
        ws.update(values=values, range_name=f"A1:I{len(values)}")
        touched += 1
        print(f"Deduplicada: {ws.title} -> {len(rows)} filas a {len(merged_rows)}")

    print(f"Hojas deduplicadas: {touched}")


if __name__ == "__main__":
    main()
