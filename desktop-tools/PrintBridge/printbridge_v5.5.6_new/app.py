import sys
import os
import threading
import socket
import logging
import webbrowser
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw

import pystray

from config import load_config, save_config
from device_manager import DeviceManager
from queue_manager import QueueManager
import printer
import server as srv

# ─── Logging ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "data" / "printbridge.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("PrintBridge")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def make_tray_icon(active: bool = True) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (0, 229, 160) if active else (120, 120, 144)
    d.rounded_rectangle([8, 20, 56, 44], radius=6, fill=color)
    d.rectangle([18, 36, 46, 56], fill=(30, 30, 35))
    d.rectangle([22, 40, 42, 54], fill=(240, 240, 245))
    d.rectangle([20, 8, 44, 24], fill=(240, 240, 245))
    d.ellipse([42, 28, 50, 36], fill=(30, 30, 35))
    return img


class PrintBridgeApp:
    def __init__(self):
        self.config = load_config()
        self.device_mgr = DeviceManager()
        self.queue_mgr = QueueManager(printer)
        self.server_running = False

        srv.set_queue_manager(self.queue_mgr)
        srv.device_mgr = self.device_mgr

        self._build_window()
        self._build_tray()

        if self.config.get("start_minimized"):
            self.window.withdraw()
        else:
            self.window.deiconify()

        self._start_server()
        self._refresh_loop()

    # ─────────────────── WINDOW ───────────────────────────────
    def _build_window(self):
        self.window = tk.Tk()
        self.window.title("PrintBridge")
        self.window.geometry("700x560")
        self.window.minsize(620, 480)
        self.window.configure(bg="#0f0f11")
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#0f0f11", foreground="#e8e8f0",
                        fieldbackground="#1a1a1f", font=("Segoe UI", 9))
        style.configure("TNotebook", background="#0f0f11", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a1f",
                        foreground="#7a7a90", padding=[14, 8])
        style.map("TNotebook.Tab",
                  background=[("selected", "#242429")],
                  foreground=[("selected", "#00e5a0")])
        style.configure("TFrame", background="#0f0f11")
        style.configure("TLabel", background="#0f0f11", foreground="#e8e8f0")
        style.configure("TButton", background="#1a1a1f", foreground="#e8e8f0",
                        borderwidth=0, relief="flat", padding=[10, 6])
        style.map("TButton", background=[("active", "#242429")])
        style.configure("Treeview", background="#1a1a1f", foreground="#e8e8f0",
                        fieldbackground="#1a1a1f", rowheight=28)
        style.configure("Treeview.Heading", background="#242429",
                        foreground="#7a7a90", relief="flat")
        style.map("Treeview", background=[("selected", "#2e2e3a")])

        self._build_header()

        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._build_tab_status()
        self._build_tab_queue()
        self._build_tab_devices()
        self._build_tab_config()
        self._build_tab_log()

    def _build_header(self):
        hdr = tk.Frame(self.window, bg="#1a1a1f", height=58)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="◈ PRINTBRIDGE", bg="#1a1a1f",
                 fg="#00e5a0", font=("Courier New", 13, "bold")).pack(side="left", padx=20)

        right = tk.Frame(hdr, bg="#1a1a1f")
        right.pack(side="right", padx=16)

        self.status_label = tk.Label(right, text="● Detenido",
                                     bg="#1a1a1f", fg="#7a7a90",
                                     font=("Segoe UI", 9))
        self.status_label.pack(side="left", padx=12)

        self.toggle_btn = tk.Button(
            right, text="Iniciar",
            bg="#00e5a0", fg="#000", font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2", padx=14, pady=5,
            command=self._toggle_server
        )
        self.toggle_btn.pack(side="left")

    # ─── Status Tab ───────────────────────────────────────────
    def _build_tab_status(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  Estado  ")

        inner = tk.Frame(f, bg="#0f0f11")
        inner.pack(fill="both", expand=True, padx=20, pady=16)

        # URL Card
        card = tk.Frame(inner, bg="#1a1a1f")
        card.pack(fill="x", pady=(0, 12))
        tk.Label(card, text="DIRECCIÓN WEB", bg="#1a1a1f", fg="#7a7a90",
                 font=("Courier New", 7)).pack(anchor="w", padx=16, pady=(12, 4))
        url_row = tk.Frame(card, bg="#1a1a1f")
        url_row.pack(fill="x", padx=16, pady=(0, 12))
        self.url_label = tk.Label(url_row, text="Servidor detenido",
                                  bg="#242429", fg="#00e5a0",
                                  font=("Courier New", 11), padx=14, pady=8)
        self.url_label.pack(side="left", fill="x", expand=True)
        tk.Button(url_row, text="📋", bg="#242429", fg="#e8e8f0",
                  relief="flat", cursor="hand2", padx=10, pady=8,
                  command=self._copy_url).pack(side="left", padx=(6, 0))
        tk.Button(url_row, text="🌐", bg="#242429", fg="#e8e8f0",
                  relief="flat", cursor="hand2", padx=10, pady=8,
                  command=self._open_browser).pack(side="left", padx=(4, 0))

        # Stats grid
        stats = tk.Frame(inner, bg="#0f0f11")
        stats.pack(fill="x")
        self.stat_queue   = self._stat_card(stats, "EN COLA", "0")
        self.stat_done    = self._stat_card(stats, "IMPRESOS HOY", "0")
        self.stat_devices = self._stat_card(stats, "DISPOSITIVOS", "0")
        self.stat_printer = self._stat_card(stats, "IMPRESORA", "—")
        for w in stats.winfo_children():
            w.pack(side="left", fill="x", expand=True, padx=4)

    def _stat_card(self, parent, label, value):
        card = tk.Frame(parent, bg="#1a1a1f")
        tk.Label(card, text=label, bg="#1a1a1f", fg="#7a7a90",
                 font=("Courier New", 7)).pack(pady=(12, 4))
        val = tk.Label(card, text=value, bg="#1a1a1f", fg="#00e5a0",
                       font=("Segoe UI", 20, "bold"))
        val.pack(pady=(0, 12))
        card._val = val
        return card

    # ─── Queue Tab ────────────────────────────────────────────
    def _build_tab_queue(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  Cola  ")

        bar = tk.Frame(f, bg="#0f0f11")
        bar.pack(fill="x", padx=16, pady=(12, 6))
        tk.Button(bar, text="⟳ Actualizar", bg="#1a1a1f", fg="#e8e8f0",
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._refresh_queue).pack(side="left")

        cols = ("archivo", "dispositivo", "copias", "estado", "hora")
        self.queue_tree = ttk.Treeview(f, columns=cols, show="headings", height=10)
        for col, w, lbl in zip(cols, [220, 140, 60, 110, 130],
                                ["Archivo", "Dispositivo", "Copias", "Estado", "Hora"]):
            self.queue_tree.heading(col, text=lbl)
            self.queue_tree.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 16))
        self.queue_tree.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        tk.Button(f, text="✕ Cancelar seleccionado", bg="#ff4d6d", fg="white",
                  relief="flat", cursor="hand2", padx=12, pady=6,
                  command=self._cancel_selected).pack(padx=16, anchor="w", pady=(0, 12))

    # ─── Devices Tab ──────────────────────────────────────────
    def _build_tab_devices(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  Dispositivos  ")

        bar = tk.Frame(f, bg="#0f0f11")
        bar.pack(fill="x", padx=16, pady=(12, 6))
        tk.Button(bar, text="⟳ Actualizar", bg="#1a1a1f", fg="#e8e8f0",
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._refresh_devices).pack(side="left")
        tk.Button(bar, text="🗑 Revocar todos", bg="#ff4d6d", fg="white",
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._revoke_all).pack(side="left", padx=8)

        cols = ("nombre", "ip", "agregado", "ultimo")
        self.devices_tree = ttk.Treeview(f, columns=cols, show="headings", height=10)
        for col, w, lbl in zip(cols, [180, 120, 150, 150],
                                ["Nombre", "IP", "Agregado", "Último acceso"]):
            self.devices_tree.heading(col, text=lbl)
            self.devices_tree.column(col, width=w, anchor="w")
        sb2 = ttk.Scrollbar(f, orient="vertical", command=self.devices_tree.yview)
        self.devices_tree.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y", padx=(0, 16))
        self.devices_tree.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        tk.Button(f, text="🗑 Revocar seleccionado", bg="#ff4d6d", fg="white",
                  relief="flat", cursor="hand2", padx=12, pady=6,
                  command=self._revoke_selected).pack(padx=16, anchor="w", pady=(0, 12))

    # ─── Config Tab ───────────────────────────────────────────
    def _build_tab_config(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  Configuración  ")

        canvas = tk.Canvas(f, bg="#0f0f11", highlightthickness=0)
        vsb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        scroll = tk.Frame(canvas, bg="#0f0f11")
        canvas.create_window((0, 0), window=scroll, anchor="nw")
        scroll.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def cfg_row(parent, label, desc, widget_factory):
            r = tk.Frame(parent, bg="#1a1a1f")
            r.pack(fill="x", pady=3, padx=4)
            lf = tk.Frame(r, bg="#1a1a1f")
            lf.pack(side="left", fill="y", padx=16, pady=12)
            tk.Label(lf, text=label, bg="#1a1a1f", fg="#e8e8f0",
                     font=("Segoe UI", 10)).pack(anchor="w")
            if desc:
                tk.Label(lf, text=desc, bg="#1a1a1f", fg="#7a7a90",
                         font=("Segoe UI", 8)).pack(anchor="w")
            rf = tk.Frame(r, bg="#1a1a1f")
            rf.pack(side="right", padx=16, pady=12)
            widget_factory(rf)

        def mk_entry(var, show=None):
            def factory(parent):
                e = tk.Entry(parent, width=22, bg="#242429", fg="#e8e8f0",
                             insertbackground="#00e5a0", relief="flat",
                             font=("Segoe UI", 10), show=show or "")
                e.insert(0, var)
                parent._widget = e
                e.pack()
            return factory

        # Printer
        def mk_printer(parent):
            cb = ttk.Combobox(parent, width=24, state="readonly")
            cb["values"] = printer.get_available_printers()
            cur = self.config.get("printer") or printer.get_default_printer()
            cb.set(cur)
            parent._widget = cb
            cb.pack()
        cfg_row(scroll, "Impresora", "Impresora USB conectada a este equipo", mk_printer)
        self._cfg_printer_frame = scroll.winfo_children()[-1].winfo_children()[-1]

        def mk_port(parent):
            e = tk.Entry(parent, width=10, bg="#242429", fg="#e8e8f0",
                         insertbackground="#00e5a0", relief="flat",
                         font=("Courier New", 10))
            e.insert(0, str(self.config.get("port", 7878)))
            parent._widget = e
            e.pack()
        cfg_row(scroll, "Puerto", "Puerto de red del servidor (reinicia para aplicar)", mk_port)
        self._cfg_port_frame = scroll.winfo_children()[-1].winfo_children()[-1]

        def mk_pin(parent):
            e = tk.Entry(parent, width=10, bg="#242429", fg="#e8e8f0",
                         insertbackground="#00e5a0", relief="flat",
                         font=("Courier New", 10), show="●")
            e.insert(0, self.config.get("pin", "1234"))
            parent._widget = e
            e.pack()
        cfg_row(scroll, "PIN de acceso", "PIN para autorizar nuevos dispositivos", mk_pin)
        self._cfg_pin_frame = scroll.winfo_children()[-1].winfo_children()[-1]

        def mk_name(parent):
            e = tk.Entry(parent, width=22, bg="#242429", fg="#e8e8f0",
                         insertbackground="#00e5a0", relief="flat",
                         font=("Segoe UI", 10))
            e.insert(0, self.config.get("server_name", "PrintBridge"))
            parent._widget = e
            e.pack()
        cfg_row(scroll, "Nombre del servidor", "Nombre visible en la web", mk_name)
        self._cfg_name_frame = scroll.winfo_children()[-1].winfo_children()[-1]

        self._cfg_minimized = tk.BooleanVar(value=self.config.get("start_minimized", False))
        def mk_check(parent):
            tk.Checkbutton(parent, variable=self._cfg_minimized,
                           bg="#1a1a1f", fg="#e8e8f0",
                           selectcolor="#242429",
                           activebackground="#1a1a1f").pack()
        cfg_row(scroll, "Iniciar minimizado", "Ocultar ventana al arrancar", mk_check)

        tk.Button(scroll, text="💾 Guardar configuración",
                  bg="#00e5a0", fg="#000", font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", padx=20, pady=8,
                  command=self._save_config).pack(pady=16, padx=20, anchor="w")

    # ─── Log Tab ──────────────────────────────────────────────
    def _build_tab_log(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="  Registro  ")
        self.log_text = tk.Text(f, bg="#0a0a0d", fg="#5a5a70",
                                font=("Courier New", 8), state="disabled",
                                relief="flat", padx=12, pady=8)
        sb = ttk.Scrollbar(f, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

    # ─── Tray ─────────────────────────────────────────────────
    def _build_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Abrir PrintBridge", self._show_window, default=True),
            pystray.MenuItem("Abrir en navegador", lambda i, i2: self._open_browser()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Detener/Iniciar servidor", self._toggle_server),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._quit),
        )
        self.tray = pystray.Icon("PrintBridge", make_tray_icon(False),
                                 "PrintBridge — Servidor detenido", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    # ─── Server ───────────────────────────────────────────────
    def _start_server(self):
        if self.server_running:
            return
        port = int(self.config.get("port", 7878))
        srv.start_server(port)
        self.server_running = True
        ip = get_local_ip()
        url = f"http://{ip}:{port}"
        self.url_label.config(text=url)
        self.status_label.config(text=f"● Activo · {url}", fg="#00e5a0")
        self.toggle_btn.config(text="Detener", bg="#ff4d6d", fg="white")
        self.tray.icon = make_tray_icon(True)
        self.tray.title = f"PrintBridge · {url}"
        self._log(f"Servidor iniciado → {url}")

    def _stop_server(self):
        if not self.server_running:
            return
        srv.stop_server()
        self.server_running = False
        self.url_label.config(text="Servidor detenido")
        self.status_label.config(text="● Detenido", fg="#7a7a90")
        self.toggle_btn.config(text="Iniciar", bg="#00e5a0", fg="#000")
        self.tray.icon = make_tray_icon(False)
        self.tray.title = "PrintBridge — Servidor detenido"
        self._log("Servidor detenido")

    def _toggle_server(self, *_):
        if self.server_running:
            self._stop_server()
        else:
            self._start_server()

    # ─── Actions ──────────────────────────────────────────────
    def _refresh_queue(self):
        for row in self.queue_tree.get_children():
            self.queue_tree.delete(row)
        for j in self.queue_mgr.get_queue():
            self.queue_tree.insert("", "end", iid=j["id"], values=(
                j["filename"], j["device_name"], j["copies"],
                j["status"], j["created_at"][:16].replace("T", " ")
            ))

    def _cancel_selected(self):
        sel = self.queue_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Selecciona un trabajo primero")
            return
        self.queue_mgr.cancel_job(sel[0])
        self._refresh_queue()

    def _refresh_devices(self):
        for row in self.devices_tree.get_children():
            self.devices_tree.delete(row)
        for d in self.device_mgr.get_all_devices():
            self.devices_tree.insert("", "end", iid=d["full_token"], values=(
                d["name"], d["ip"],
                d["added_at"][:16].replace("T", " "),
                d["last_seen"][:16].replace("T", " "),
            ))

    def _revoke_selected(self):
        sel = self.devices_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Selecciona un dispositivo primero")
            return
        if messagebox.askyesno("Confirmar", "¿Revocar acceso a este dispositivo?"):
            self.device_mgr.remove_device(sel[0])
            self._refresh_devices()

    def _revoke_all(self):
        if messagebox.askyesno("Confirmar", "¿Revocar TODOS los dispositivos?\nDeberán ingresar PIN nuevamente."):
            self.device_mgr.remove_all()
            self._refresh_devices()

    def _save_config(self):
        p = self._cfg_printer_frame._widget.get()
        port = self._cfg_port_frame._widget.get()
        pin = self._cfg_pin_frame._widget.get()
        name = self._cfg_name_frame._widget.get()

        self.config["printer"] = p
        self.config["port"] = int(port or 7878)
        self.config["pin"] = pin
        self.config["server_name"] = name
        self.config["start_minimized"] = self._cfg_minimized.get()
        save_config(self.config)
        self.device_mgr.reload()
        messagebox.showinfo("Guardado", "✅ Configuración guardada.\nReinicia el servidor para aplicar cambios de puerto.")

    def _copy_url(self):
        url = self.url_label.cget("text")
        if url not in ("Servidor detenido", "—"):
            self.window.clipboard_clear()
            self.window.clipboard_append(url)

    def _open_browser(self, *_):
        port = self.config.get("port", 7878)
        webbrowser.open(f"http://localhost:{port}")

    # ─── Refresh loop ─────────────────────────────────────────
    def _refresh_loop(self):
        try:
            self._refresh_queue()
            self._refresh_devices()
            self._update_stats()
        except Exception:
            pass
        self.window.after(4000, self._refresh_loop)

    def _update_stats(self):
        queue = self.queue_mgr.get_queue()
        waiting = sum(1 for j in queue if j["status"] in ("waiting", "printing"))
        history = self.queue_mgr.get_history()
        today = datetime.now().strftime("%Y-%m-%d")
        done_today = sum(1 for j in history
                         if j.get("status") == "done" and (j.get("finished_at") or "").startswith(today))
        devices = len(self.device_mgr.devices)
        pr = self.config.get("printer") or printer.get_default_printer() or "—"

        self.stat_queue._val.config(text=str(waiting))
        self.stat_done._val.config(text=str(done_today))
        self.stat_devices._val.config(text=str(devices))
        short = pr[:16] + "…" if len(pr) > 16 else pr
        self.stat_printer._val.config(
            text=short,
            font=("Segoe UI", 10 if len(pr) > 10 else 20, "bold")
        )

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ─── Window control ───────────────────────────────────────
    def _show_window(self, *_):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _on_close(self):
        self.window.withdraw()  # Minimize to tray

    def _quit(self, *_):
        self._stop_server()
        self.tray.stop()
        self.window.destroy()
        sys.exit(0)

    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    app = PrintBridgeApp()
    app.run()
