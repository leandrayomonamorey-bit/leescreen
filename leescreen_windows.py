"""
LeeScreen Windows — Transmisión de pantalla estilo Samsung Smart View
Leecito Projects | Compatible con Android APK
Usa SOLO librerías compatibles con Python 3.14:
  tkinter (built-in), Pillow, numpy, opencv-python
"""

import sys, os, socket, threading, struct, time, io, tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageGrab, Image, ImageTk
import numpy as np
import cv2

# ─── CONSTANTES ──────────────────────────────────────────────
APP_NAME    = "LeeScreen"
BRAND       = "Leecito Projects"
PORT_RECV   = 5556
FPS_TARGET  = 20
QUALITY     = 52
SCALE       = 0.55
CHUNK       = 65536

# Colores Samsung-inspired
BG          = "#0A0A0F"
SURFACE     = "#12121A"
CARD        = "#1A1A26"
CARD2       = "#1E1E2E"
ACCENT      = "#4FC3F7"
ACCENT2     = "#00B0FF"
GREEN       = "#00E676"
TEXT        = "#FFFFFF"
TEXT2       = "#B0B8D0"
TEXT3       = "#6B7A99"
DANGER      = "#FF5252"
BORDER      = "#252538"


# ════════════════════════════════════════════════════════════════
# WORKERS
# ════════════════════════════════════════════════════════════════
class ScreenSender(threading.Thread):
    def __init__(self, ip, cb_status, cb_fps, cb_error, cb_connect, cb_disconnect):
        super().__init__(daemon=True)
        self.ip            = ip
        self.cb_status     = cb_status
        self.cb_fps        = cb_fps
        self.cb_error      = cb_error
        self.cb_connect    = cb_connect
        self.cb_disconnect = cb_disconnect
        self._running      = False
        self._sock         = None

    def stop(self):
        self._running = False
        if self._sock:
            try: self._sock.close()
            except: pass

    def run(self):
        self._running = True
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5)
            self._sock.connect((self.ip, PORT_RECV))
            self._sock.settimeout(None)
            self.cb_connect()
            self.cb_status(f"Transmitiendo a {self.ip}")

            frame_t = 1.0 / FPS_TARGET
            fps_c, fps_t = 0, time.time()

            while self._running:
                t0 = time.time()
                ss = ImageGrab.grab()
                w  = int(ss.width * SCALE)
                h  = int(ss.height * SCALE)
                ss = ss.resize((w, h), Image.LANCZOS)
                buf = io.BytesIO()
                ss.save(buf, "JPEG", quality=QUALITY)
                data = buf.getvalue()
                self._sock.sendall(struct.pack(">I", len(data)) + data)

                fps_c += 1
                el = time.time() - fps_t
                if el >= 1.0:
                    self.cb_fps(fps_c / el)
                    fps_c, fps_t = 0, time.time()

                dt = time.time() - t0
                if dt < frame_t:
                    time.sleep(frame_t - dt)

        except ConnectionRefusedError:
            self.cb_error("Dispositivo no encontrado o no está listo")
        except Exception as e:
            if self._running:
                self.cb_error(str(e))
        finally:
            self.cb_disconnect()


class ScreenReceiver(threading.Thread):
    def __init__(self, cb_frame, cb_status, cb_connect, cb_disconnect, cb_error):
        super().__init__(daemon=True)
        self.cb_frame      = cb_frame
        self.cb_status     = cb_status
        self.cb_connect    = cb_connect
        self.cb_disconnect = cb_disconnect
        self.cb_error      = cb_error
        self._running      = False
        self._server       = None

    def stop(self):
        self._running = False
        if self._server:
            try: self._server.close()
            except: pass

    def run(self):
        self._running = True
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind(("0.0.0.0", PORT_RECV))
            self._server.listen(1)
            self._server.settimeout(1)
            self.cb_status(f"Esperando conexión en puerto {PORT_RECV}...")

            while self._running:
                try:
                    conn, addr = self._server.accept()
                except socket.timeout:
                    continue
                self.cb_connect(addr[0])
                self._handle(conn)
                self.cb_disconnect()

        except Exception as e:
            if self._running:
                self.cb_error(str(e))

    def _handle(self, conn):
        buf = b""
        try:
            while self._running:
                while len(buf) < 4:
                    c = conn.recv(4096)
                    if not c: return
                    buf += c
                size = struct.unpack(">I", buf[:4])[0]
                buf  = buf[4:]
                while len(buf) < size:
                    c = conn.recv(min(size - len(buf), CHUNK))
                    if not c: return
                    buf += c
                data   = buf[:size]
                buf    = buf[size:]
                nparr  = np.frombuffer(data, np.uint8)
                img    = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None: continue
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(img_rgb)
                self.cb_frame(pil_img)
        except: pass
        finally:
            try: conn.close()
            except: pass


class DeviceScanner(threading.Thread):
    def __init__(self, cb_found, cb_done):
        super().__init__(daemon=True)
        self.cb_found = cb_found
        self.cb_done  = cb_done
        self._running = True

    def stop(self): self._running = False

    def run(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local = s.getsockname()[0]
            s.close()
        except:
            self.cb_done(); return

        subnet = ".".join(local.split(".")[:3])
        workers = []

        def probe(ip):
            if not self._running: return
            try:
                sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sk.settimeout(0.35)
                if sk.connect_ex((ip, PORT_RECV)) == 0:
                    try: name = socket.gethostbyaddr(ip)[0].split(".")[0]
                    except: name = ip
                    self.cb_found(ip, name)
                sk.close()
            except: pass

        for i in range(1, 255):
            if not self._running: break
            ip = f"{subnet}.{i}"
            if ip == local: continue
            t = threading.Thread(target=probe, args=(ip,), daemon=True)
            t.start()
            workers.append(t)
        for t in workers: t.join(timeout=0.5)
        self.cb_done()


# ════════════════════════════════════════════════════════════════
# UI HELPERS
# ════════════════════════════════════════════════════════════════
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close()
        return ip
    except: return "127.0.0.1"


class Sidebar(tk.Frame):
    def __init__(self, parent, nav_callback):
        super().__init__(parent, bg=SURFACE, width=220)
        self.pack_propagate(False)
        self.nav_callback = nav_callback
        self._btns = {}
        self._build()

    def _build(self):
        # Logo
        logo_f = tk.Frame(self, bg=SURFACE)
        logo_f.pack(fill="x", padx=20, pady=(24, 8))
        tk.Label(logo_f, text="LeeScreen", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(logo_f, text=BRAND, bg=SURFACE, fg=ACCENT,
                 font=("Segoe UI", 9)).pack(anchor="w")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Nav
        nav_frame = tk.Frame(self, bg=SURFACE)
        nav_frame.pack(fill="x", pady=8)

        items = [("🏠  Inicio", "home"), ("📤  Enviar", "send"), ("📥  Recibir", "receive")]
        for label, key in items:
            btn = tk.Label(nav_frame, text=label, bg=SURFACE, fg=TEXT2,
                           font=("Segoe UI", 13), cursor="hand2",
                           anchor="w", padx=22, pady=10)
            btn.pack(fill="x")
            btn.bind("<Button-1>", lambda e, k=key: self.nav_callback(k))
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=CARD))
            btn.bind("<Leave>", lambda e, b=btn, k=key: b.config(
                bg=CARD if self._btns.get("active") == k else SURFACE))
            self._btns[key] = btn

        # IP local
        ip_f = tk.Frame(self, bg=CARD)
        ip_f.pack(fill="x", side="bottom")
        tk.Frame(ip_f, bg=BORDER, height=1).pack(fill="x")
        inner = tk.Frame(ip_f, bg=CARD)
        inner.pack(fill="x", padx=20, pady=12)
        tk.Label(inner, text="Tu IP en esta red", bg=CARD, fg=TEXT3,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self._ip_lbl = tk.Label(inner, text=get_local_ip(), bg=CARD, fg=ACCENT,
                                font=("Segoe UI", 12, "bold"))
        self._ip_lbl.pack(anchor="w")

    def set_active(self, key):
        for k, btn in self._btns.items():
            if isinstance(btn, tk.Label):
                if k == key:
                    btn.config(bg=CARD, fg=ACCENT, font=("Segoe UI", 13, "bold"))
                else:
                    btn.config(bg=SURFACE, fg=TEXT2, font=("Segoe UI", 13))
        self._btns["active"] = key


class StatusBar(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=CARD, height=50)
        self.pack_propagate(False)
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=0)
        self._dot = tk.Label(inner, text="●", bg=CARD, fg=TEXT3, font=("Segoe UI", 9))
        self._dot.pack(side="left")
        self._status = tk.Label(inner, text="Inactivo", bg=CARD, fg=TEXT2,
                                font=("Segoe UI", 11), anchor="w")
        self._status.pack(side="left", padx=(8, 0))
        self._right = tk.Label(inner, text="", bg=CARD, fg=ACCENT,
                               font=("Segoe UI", 11, "bold"))
        self._right.pack(side="right")

    def update(self, text, active=False, right=""):
        color = GREEN if active else TEXT3
        fg    = TEXT if active else TEXT2
        self._dot.config(fg=color)
        self._status.config(text=text, fg=fg)
        self._right.config(text=right)


def styled_btn(parent, text, bg=ACCENT, fg="#000000", cmd=None, w=None, h=36):
    btn = tk.Button(parent, text=text, bg=bg, fg=fg, activebackground=ACCENT2,
                    activeforeground=fg, relief="flat", cursor="hand2",
                    font=("Segoe UI", 11, "bold"),
                    command=cmd, bd=0, padx=14)
    if w: btn.config(width=w)
    return btn


def card(parent, **kwargs):
    f = tk.Frame(parent, bg=CARD, **kwargs)
    return f


# ════════════════════════════════════════════════════════════════
# PÁGINAS
# ════════════════════════════════════════════════════════════════
class HomePage(tk.Frame):
    def __init__(self, parent, navigate):
        super().__init__(parent, bg=BG)
        self._nav = navigate
        self._build()

    def _build(self):
        pad = tk.Frame(self, bg=BG)
        pad.pack(fill="both", expand=True, padx=48, pady=40)

        tk.Label(pad, text="LeeScreen", bg=BG, fg=TEXT,
                 font=("Segoe UI", 28, "bold")).pack(anchor="w")
        tk.Label(pad, text="Transmisión de pantalla entre Windows y Android",
                 bg=BG, fg=TEXT3, font=("Segoe UI", 12)).pack(anchor="w", pady=(2, 24))

        # Tarjetas de modo
        cards_row = tk.Frame(pad, bg=BG)
        cards_row.pack(fill="x")

        self._mode_card(cards_row,
            "📤", "Enviar Pantalla",
            "Transmite tu pantalla a otro\ndispositivo en la misma red.",
            ACCENT, lambda: self._nav("send")
        ).pack(side="left", fill="both", expand=True, padx=(0, 10))

        self._mode_card(cards_row,
            "📥", "Recibir Pantalla",
            "Visualiza en vivo la pantalla\nde otro dispositivo.",
            "#7C4DFF", lambda: self._nav("receive")
        ).pack(side="left", fill="both", expand=True, padx=(10, 0))

        # Info
        tk.Frame(pad, bg=BG, height=20).pack()
        info = card(pad)
        info.pack(fill="x")
        tk.Frame(info, bg=BG, height=1).pack()
        inner = tk.Frame(info, bg=CARD)
        inner.pack(fill="x", padx=20, pady=16)
        tk.Label(inner, text="ℹ️  Cómo usar LeeScreen", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        for step in [
            "1. Ambos dispositivos deben estar en la misma red Wi-Fi.",
            "2. El que envía elige 'Enviar' e ingresa la IP del receptor.",
            "3. El que recibe elige 'Recibir' y pulsa Iniciar.",
            "4. La transmisión comienza automáticamente.",
        ]:
            tk.Label(inner, text=step, bg=CARD, fg=TEXT2,
                     font=("Segoe UI", 11)).pack(anchor="w")

    def _mode_card(self, parent, icon, title, desc, color, cmd):
        f = tk.Frame(parent, bg=CARD, cursor="hand2")
        inner = tk.Frame(f, bg=CARD)
        inner.pack(fill="both", expand=True, padx=24, pady=22)
        tk.Label(inner, text=icon, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 30)).pack(anchor="w")
        tk.Label(inner, text=title, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(8, 4))
        tk.Label(inner, text=desc, bg=CARD, fg=TEXT3,
                 font=("Segoe UI", 10), justify="left").pack(anchor="w")
        tk.Frame(inner, bg=CARD, height=14).pack()
        btn = tk.Button(inner, text="Seleccionar →", bg=color,
                        fg="#000000" if color == ACCENT else TEXT,
                        font=("Segoe UI", 10, "bold"), relief="flat",
                        cursor="hand2", command=cmd, padx=14, pady=6)
        btn.pack(anchor="w")
        f.bind("<Button-1>", lambda e: cmd())
        return f


class SendPage(tk.Frame):
    def __init__(self, parent, navigate):
        super().__init__(parent, bg=BG)
        self._nav    = navigate
        self._sender = None
        self._scanner = None
        self._build()

    def _build(self):
        pad = tk.Frame(self, bg=BG)
        pad.pack(fill="both", expand=True, padx=48, pady=32)

        # Header
        h = tk.Frame(pad, bg=BG)
        h.pack(fill="x", pady=(0, 4))
        tk.Label(h, text="📤  Enviar Pantalla", bg=BG, fg=TEXT,
                 font=("Segoe UI", 20, "bold")).pack(side="left")

        tk.Label(pad, text="Ingresa la IP del receptor o escanea la red local.",
                 bg=BG, fg=TEXT3, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 18))

        # Input row
        ip_row = tk.Frame(pad, bg=BG)
        ip_row.pack(fill="x", pady=(0, 12))
        tk.Label(ip_row, text="IP del receptor:", bg=BG, fg=TEXT2,
                 font=("Segoe UI", 11)).pack(side="left", padx=(0, 10))
        self._ip_var = tk.StringVar()
        self._ip_entry = tk.Entry(ip_row, textvariable=self._ip_var, bg=CARD, fg=TEXT,
                                  insertbackground=ACCENT, relief="flat",
                                  font=("Segoe UI", 12), width=22)
        self._ip_entry.pack(side="left", ipady=7, padx=(0, 8))
        self._ip_entry.bind("<Return>", lambda e: self._connect())

        styled_btn(ip_row, "🔍  Buscar", bg=CARD, fg=TEXT2,
                   cmd=self._scan).pack(side="left", padx=(0, 8), ipady=4)
        styled_btn(ip_row, "Conectar", bg=ACCENT, fg="#000",
                   cmd=self._connect).pack(side="left", ipady=4)

        # Dispositivos encontrados
        tk.Label(pad, text="Dispositivos en la red:", bg=BG, fg=TEXT3,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 4))

        list_frame = card(pad)
        list_frame.pack(fill="x")
        self._dev_frame = tk.Frame(list_frame, bg=CARD)
        self._dev_frame.pack(fill="x", padx=2, pady=2)
        self._no_dev_lbl = tk.Label(self._dev_frame,
                                    text="  Pulsa 'Buscar' para escanear la red...",
                                    bg=CARD, fg=TEXT3, font=("Segoe UI", 11),
                                    pady=12)
        self._no_dev_lbl.pack(anchor="w")

        self._scan_lbl = tk.Label(pad, text="", bg=BG, fg=TEXT3,
                                  font=("Segoe UI", 10))
        self._scan_lbl.pack(anchor="w", pady=(4, 16))

        # Status + stop
        status_card = card(pad)
        status_card.pack(fill="x", side="bottom", pady=(12, 0))
        inner = tk.Frame(status_card, bg=CARD)
        inner.pack(fill="x", padx=14, pady=10)

        self._status_bar = StatusBar(inner)
        self._status_bar.pack(side="left", fill="x", expand=True)

        self._stop_btn = styled_btn(inner, "■  Detener", bg=CARD, fg=DANGER, cmd=self._stop)
        self._stop_btn.pack(side="right", ipady=4)
        self._stop_btn.config(state="disabled")

    def _scan(self):
        # Limpiar lista
        for w in self._dev_frame.winfo_children():
            w.destroy()
        self._no_dev_lbl = tk.Label(self._dev_frame,
                                    text="  🔍 Escaneando red local...",
                                    bg=CARD, fg=ACCENT, font=("Segoe UI", 11), pady=12)
        self._no_dev_lbl.pack(anchor="w")
        self._scan_lbl.config(text="")

        if self._scanner:
            self._scanner.stop()
        self._scanner = DeviceScanner(
            cb_found=lambda ip, name: self.after(0, self._add_device, ip, name),
            cb_done =lambda: self.after(0, lambda: self._scan_lbl.config(
                text="✔ Escaneo completo. Dispositivos no encontrados = ingresa IP manual."))
        )
        self._scanner.start()

    def _add_device(self, ip, name):
        # Quitar mensaje "escaneando"
        for w in self._dev_frame.winfo_children():
            if isinstance(w, tk.Label) and "Escaneando" in str(w.cget("text")):
                w.destroy()

        row = tk.Frame(self._dev_frame, bg=CARD2, cursor="hand2")
        row.pack(fill="x", padx=4, pady=2)
        tk.Label(row, text="●", bg=CARD2, fg=GREEN,
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 6), pady=8)
        tk.Label(row, text="📱", bg=CARD2, font=("Segoe UI", 16)).pack(side="left")
        info = tk.Frame(row, bg=CARD2)
        info.pack(side="left", padx=10)
        tk.Label(info, text=name, bg=CARD2, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(info, text=ip, bg=CARD2, fg=TEXT3,
                 font=("Segoe UI", 9)).pack(anchor="w")
        btn = tk.Button(row, text="Conectar", bg=ACCENT, fg="#000",
                        font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                        command=lambda i=ip: self._connect_to(i), padx=10, pady=4)
        btn.pack(side="right", padx=10, pady=8)

    def _connect(self):
        self._connect_to(self._ip_var.get().strip())

    def _connect_to(self, ip):
        if not ip:
            messagebox.showwarning("IP vacía", "Ingresa una IP válida.")
            return
        self._stop()
        self._sender = ScreenSender(
            ip, cb_status=lambda s: self.after(0, self._status_bar.update, s, True),
            cb_fps=lambda f: self.after(0, self._status_bar.update,
                                        self._status_bar._status.cget("text"), True, f"{f:.1f} FPS"),
            cb_error=lambda e: self.after(0, self._on_error, e),
            cb_connect=lambda: self.after(0, self._stop_btn.config, {"state": "normal"}),
            cb_disconnect=lambda: self.after(0, self._on_disconnect)
        )
        self._sender.start()
        self._status_bar.update(f"Conectando a {ip}...", False)

    def _stop(self):
        if self._sender:
            self._sender.stop()
            self._sender = None
        self._status_bar.update("Sin conexión", False, "")
        self._stop_btn.config(state="disabled")

    def _on_error(self, msg):
        self._stop()
        messagebox.showerror("Error de conexión", msg)

    def _on_disconnect(self):
        self._status_bar.update("Desconectado", False, "")
        self._stop_btn.config(state="disabled")

    def on_hide(self):
        self._stop()


class ReceivePage(tk.Frame):
    def __init__(self, parent, navigate):
        super().__init__(parent, bg=BG)
        self._nav      = navigate
        self._receiver = None
        self._current_img = None
        self._build()

    def _build(self):
        # Header
        h = tk.Frame(self, bg=BG)
        h.pack(fill="x", padx=48, pady=(28, 0))
        tk.Label(h, text="📥  Recibir Pantalla", bg=BG, fg=TEXT,
                 font=("Segoe UI", 20, "bold")).pack(side="left")
        self._stop_btn = styled_btn(h, "■  Detener", bg=CARD, fg=DANGER,
                                    cmd=self.stop_recv)
        self._stop_btn.pack(side="right", ipady=4, padx=(8, 0))
        self._start_btn = styled_btn(h, "▶  Iniciar", bg=GREEN, fg="#000",
                                     cmd=self.start_recv)
        self._start_btn.pack(side="right", ipady=4)
        self._stop_btn.config(state="disabled")

        tk.Label(self, text=f"Este PC escucha en el puerto {PORT_RECV}. IP: {get_local_ip()}",
                 bg=BG, fg=TEXT3, font=("Segoe UI", 10)).pack(anchor="w", padx=48)

        # Canvas para mostrar pantalla
        canvas_frame = tk.Frame(self, bg=CARD)
        canvas_frame.pack(fill="both", expand=True, padx=48, pady=16)
        self._canvas = tk.Canvas(canvas_frame, bg=CARD, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._placeholder()

        # Status bar
        status_card = card(self)
        status_card.pack(fill="x", padx=48, pady=(0, 28))
        inner = tk.Frame(status_card, bg=CARD)
        inner.pack(fill="x", padx=14, pady=10)
        self._status_bar = StatusBar(inner)
        self._status_bar.pack(side="left", fill="x", expand=True)
        self._client_lbl = tk.Label(inner, text="", bg=CARD, fg=ACCENT,
                                    font=("Segoe UI", 11, "bold"))
        self._client_lbl.pack(side="right")

        self._canvas.bind("<Configure>", lambda e: self._redraw())

    def _placeholder(self):
        self._canvas.delete("all")
        w = self._canvas.winfo_width() or 600
        h = self._canvas.winfo_height() or 400
        self._canvas.create_text(w//2, h//2, text="Esperando transmisión...",
                                  fill=TEXT3, font=("Segoe UI", 14))
        self._canvas.create_text(w//2, h//2 + 30,
                                  text="Conecta un dispositivo para ver su pantalla",
                                  fill=TEXT3, font=("Segoe UI", 10))

    def start_recv(self):
        self.stop_recv()
        self._receiver = ScreenReceiver(
            cb_frame=lambda img: self.after(0, self._show_frame, img),
            cb_status=lambda s: self.after(0, self._status_bar.update, s, False),
            cb_connect=lambda ip: self.after(0, self._on_connect, ip),
            cb_disconnect=lambda: self.after(0, self._on_disconnect),
            cb_error=lambda e: self.after(0, self._status_bar.update, f"Error: {e}", False)
        )
        self._receiver.start()
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._status_bar.update(f"Escuchando en {get_local_ip()}:{PORT_RECV}...", False)

    def stop_recv(self):
        if self._receiver:
            self._receiver.stop()
            self._receiver = None
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._status_bar.update("Inactivo — pulsa Iniciar para escuchar", False)
        self._client_lbl.config(text="")
        self._current_img = None
        self._placeholder()

    def _on_connect(self, ip):
        self._status_bar.update(f"Recibiendo de {ip}", True)
        self._client_lbl.config(text=f"📱 {ip}")

    def _on_disconnect(self):
        self._status_bar.update("Esperando nueva conexión...", False)
        self._client_lbl.config(text="")
        self._current_img = None
        self._placeholder()

    def _show_frame(self, pil_img):
        self._current_img = pil_img
        self._redraw()

    def _redraw(self):
        if self._current_img is None:
            return
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        img = self._current_img.copy()
        img.thumbnail((cw, ch), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, ch // 2, image=tk_img, anchor="center")
        self._canvas._tk_img = tk_img   # evitar garbage collection

    def on_hide(self):
        self.stop_recv()


# ════════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ════════════════════════════════════════════════════════════════
class LeeScreenApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — {BRAND}")
        self.geometry("1100x680")
        self.minsize(900, 580)
        self.configure(bg=BG)
        self._current_page = None
        self._pages        = {}
        self._build()
        self._navigate("home")

    def _build(self):
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True)

        self._sidebar = Sidebar(root, self._navigate)
        self._sidebar.pack(side="left", fill="y")

        tk.Frame(root, bg=BORDER, width=1).pack(side="left", fill="y")

        self._content = tk.Frame(root, bg=BG)
        self._content.pack(side="left", fill="both", expand=True)

        self._pages = {
            "home"   : HomePage(self._content, self._navigate),
            "send"   : SendPage(self._content, self._navigate),
            "receive": ReceivePage(self._content, self._navigate),
        }

    def _navigate(self, key):
        if self._current_page and hasattr(self._current_page, "on_hide"):
            self._current_page.on_hide()
        for p in self._pages.values():
            p.pack_forget()
        page = self._pages[key]
        page.pack(fill="both", expand=True)
        self._current_page = page
        self._sidebar.set_active(key)

    def on_close(self):
        if self._current_page and hasattr(self._current_page, "on_hide"):
            self._current_page.on_hide()
        self.destroy()


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = LeeScreenApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
