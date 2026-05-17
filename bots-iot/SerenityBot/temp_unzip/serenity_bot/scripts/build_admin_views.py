from collections import defaultdict

import gspread


SPREADSHEET_KEY = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk"
SERIES_HEADERS = [
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
BLOCK_WIDTH = 11
KNOWN_OWNERS = [
    ("1154257480734490664", "Itsuki"),
    ("643559580990701596", "Kato"),
    ("1203552106041180220", "Celeste"),
    ("1123475061664387093", "El pirateador"),
]
OWNER_NAME_BY_ID = {owner_id: owner_name for owner_id, owner_name in KNOWN_OWNERS}


def norm(value):
    return str(value or "").strip()


def get_client():
    return gspread.service_account("credentials.json")


def ensure_worksheet(book, worksheets_by_title, title, rows, cols):
    try:
        sheet = worksheets_by_title[norm(title).lower()]
        sheet.clear()
        current_rows = sheet.row_count
        current_cols = sheet.col_count
        if current_rows < rows or current_cols < cols:
            sheet.resize(rows=max(current_rows, rows), cols=max(current_cols, cols))
        if sheet.title != title:
            old_title = sheet.title
            sheet.update_title(title)
            worksheets_by_title.pop(norm(old_title).lower(), None)
            worksheets_by_title[norm(title).lower()] = sheet
        return sheet, False
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=title, rows=rows, cols=cols)
        worksheets_by_title[norm(title).lower()] = sheet
        return sheet, True
    except KeyError:
        sheet = book.add_worksheet(title=title, rows=rows, cols=cols)
        worksheets_by_title[norm(title).lower()] = sheet
        return sheet, True


def get_series_rows(series_sheet):
    rows = series_sheet.get_all_records()
    valid = []
    for row in rows:
        if norm(row.get("Nombre")):
            valid.append(row)
    return valid


def normalize_cap(value):
    import re

    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\.[a-zA-Z0-9]+$", "", text).lower().replace("_", " ")
    patterns = [
        r"(?:cap(?:itulo)?|chapter|ch|episodio|ep)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)",
        r"(?:traduccion|traducción|trad|clean|clrd|edicion|edición|type|recorte|raw)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)",
        r"(\d+(?:[.-]\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace(".", "-")
    return str(value or "").strip()


def get_series_table(worksheets_by_title, series_row):
    sheet_name = norm(series_row.get("Nombre"))
    sheet = worksheets_by_title.get(norm(sheet_name).lower())
    if not sheet:
        owner_sheet = worksheets_by_title.get(norm(series_row.get("Admin_Nombre")).lower())
        if not owner_sheet:
            return []

        values = owner_sheet.get_all_values()
        titles = values[0] if values else []
        start_col = None
        for idx in range(0, len(titles), BLOCK_WIDTH):
            if norm(titles[idx]).lower() == norm(sheet_name).lower():
                start_col = idx
                break
        if start_col is None:
            return []

        data_rows = []
        for row in values[4:]:
            padded = row + [""] * (start_col + len(SERIES_HEADERS) - len(row))
            block_row = padded[start_col:start_col + len(SERIES_HEADERS)]
            if norm(block_row[0]):
                data_rows.append(block_row)
            else:
                break
        return data_rows

    rows = sheet.get_all_values()
    if not rows:
        return []

    data_rows = []
    for row in rows[1:]:
        padded = row + [""] * (len(SERIES_HEADERS) - len(row))
        if norm(padded[0]):
            data_rows.append(padded[: len(SERIES_HEADERS)])
    return data_rows


def build_block(series_row, table_rows):
    nombre = norm(series_row.get("Nombre"))
    categoria = norm(series_row.get("Categoria"))
    idioma = norm(series_row.get("Idioma"))
    canal_id = norm(series_row.get("Canal_ID"))
    folder_id = norm(series_row.get("Folder_ID"))

    block = [
        [nombre],
        [f"Categoria: {categoria} | Idioma: {idioma}"],
        [f"Canal: {canal_id} | Folder: {folder_id}"],
        SERIES_HEADERS,
    ]

    if table_rows:
        block.extend(table_rows)
    else:
        block.append(["Sin datos", "", "", "", "", "", "", "", ""])

    return block


def apply_in_progress(block, serie_name, asig_rows):
    headers = block[3]
    rows = block[4:]
    task_to_col = {
        "Clean": "Clean",
        "Traduccion": "Traduccion",
        "Edicion": "Edicion",
    }

    in_progress = [
        row for row in asig_rows
        if norm(row.get("Proyecto")).lower() == norm(serie_name).lower()
        and norm(row.get("Estado")) == "En Proceso"
    ]

    for row in rows:
        cap = normalize_cap(row[0])
        if not cap:
            continue
        for item in in_progress:
            if normalize_cap(item.get("Capítulo")) != cap:
                continue
            col_name = task_to_col.get(norm(item.get("Tarea")))
            if not col_name:
                continue
            idx = headers.index(col_name)
            if row[idx] != "✅":
                row[idx] = "⏳"
    return block


def write_block(sheet, start_col, block):
    end_col = start_col + len(SERIES_HEADERS) - 1
    max_width = len(SERIES_HEADERS)
    padded = []
    for row in block:
        padded.append(row + [""] * (max_width - len(row)))

    start_a1 = gspread.utils.rowcol_to_a1(1, start_col)
    end_a1 = gspread.utils.rowcol_to_a1(len(padded), end_col)
    sheet.update(
        values=padded,
        range_name=f"{start_a1}:{end_a1}",
    )


def main():
    client = get_client()
    book = client.open_by_key(SPREADSHEET_KEY)
    worksheets_by_title = {norm(ws.title).lower(): ws for ws in book.worksheets()}
    series_sheet = book.worksheet("Series")
    asig_sheet = book.worksheet("Asignaciones")
    series_rows = get_series_rows(series_sheet)
    asig_rows = asig_sheet.get_all_records()

    owners = {(owner_id, owner_name) for owner_id, owner_name in KNOWN_OWNERS}
    grouped = defaultdict(list)

    for row in series_rows:
        owner_id = norm(row.get("Admin_ID"))
        owner_name = OWNER_NAME_BY_ID.get(owner_id, norm(row.get("Admin_Nombre")) or "Sin responsable")
        owners.add((owner_id, owner_name))
        grouped[(owner_id, owner_name)].append(row)

    summary = []

    for owner_id, owner_name in sorted(owners, key=lambda item: item[1].lower()):
        title = owner_name or f"Responsable {owner_id}"
        owner_series = sorted(grouped.get((owner_id, owner_name), []), key=lambda row: norm(row.get("Nombre")).lower())
        total_series = len(owner_series)
        total_cols = max(BLOCK_WIDTH * max(total_series, 1), BLOCK_WIDTH)

        longest_table = 1
        blocks = []
        for row in owner_series:
            table = get_series_table(worksheets_by_title, row)
            block = build_block(row, table)
            block = apply_in_progress(block, norm(row.get("Nombre")), asig_rows)
            blocks.append(block)
            longest_table = max(longest_table, len(block))

        sheet, created = ensure_worksheet(book, worksheets_by_title, title, rows=max(longest_table + 2, 20), cols=total_cols)

        if not owner_series:
            sheet.update(values=[[title], ["Sin series asignadas actualmente."]], range_name="A1:A2")
            summary.append(f"{title}: 0 series")
            continue

        for idx, block in enumerate(blocks):
            start_col = 1 + (idx * BLOCK_WIDTH)
            write_block(sheet, start_col, block)

        summary.append(f"{title}: {total_series} series")

    print("admin_views_built")
    for line in summary:
        print(line)


if __name__ == "__main__":
    main()
