import gspread


SPREADSHEET_KEY = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk"


def norm(value):
    return str(value or "").strip()


def main():
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    client = gspread.service_account("credentials.json")
    book = client.open_by_key(SPREADSHEET_KEY)
    series_sheet = book.worksheet("Series")
    series_rows = series_sheet.get_all_records()
    series_names = {norm(row.get("Nombre")).lower() for row in series_rows if norm(row.get("Nombre"))}

    deleted = []
    for ws in book.worksheets():
        title = norm(ws.title).lower()
        if title in series_names:
            book.del_worksheet(ws)
            deleted.append(ws.title)

    print("deleted_series_tabs", len(deleted))
    for title in deleted:
        print(title)


if __name__ == "__main__":
    main()
