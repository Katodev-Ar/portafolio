# -*- coding: utf-8 -*-
import gspread
import asyncio
from datetime import datetime

class ExcelStaffManager:
    def __init__(self, credentials_path, spreadsheet_key):
        self.gc = gspread.service_account(filename=credentials_path)
        self.sh = self.gc.open_by_key(spreadsheet_key)
        self.asig_sheet = self.sh.worksheet("Asignaciones")
        self.reg_sheet = self.sh.worksheet("Registro")

    async def get_assignments(self):
        return await asyncio.to_thread(self.asig_sheet.get_all_records)

    async def add_assignment(self, project, chapter, task, user_name, user_id):
        row = [project, chapter, task, user_name, "En Proceso", str(user_id)]
        await asyncio.to_thread(self.asig_sheet.append_row, row)

    async def mark_as_finished(self, project, chapter, task, user_id):
        data = await self.get_assignments()
        for i, row in enumerate(data, start=2):
            if (str(row['Proyecto']).strip().lower() == project.strip().lower() and
                str(row['Capítulo']) == str(chapter) and
                row['Tarea'] == task and
                str(row['ID_Usuario']) == str(user_id) and
                row['Estado'] != "Terminado"):
                
                # Actualizar estado en Asignaciones
                await asyncio.to_thread(self.asig_sheet.update_cell, i, 5, "Terminado")
                
                # Registrar en hoja de Registro
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                reg_row = [now, row['Usuario'], project, chapter, task, str(user_id)]
                await asyncio.to_thread(self.reg_sheet.append_row, reg_row)
                return True
        return False

    async def get_staff_status(self, user_id=None):
        data = await self.get_assignments()
        active = [r for r in data if r['Estado'] == "En Proceso"]
        if user_id:
            return [r for r in active if str(r['ID_Usuario']) == str(user_id)]
        return active
