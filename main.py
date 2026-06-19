"""
LeeScreen Android — Transmisión de pantalla
Leecito Projects | Compatible con Windows LeeScreen
Requiere: Kivy, Pillow, numpy, opencv-python
"""

import os
import sys
import socket
import threading
import struct
import time
import io

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle, Ellipse, Line
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.utils import get_color_from_hex
from kivy.core.image import Image as CoreImage

import numpy as np

# ─── CONSTANTES ──────────────────────────────────────────────
APP_NAME     = "LeeScreen"
BRAND        = "Leecito Projects"
PORT_SEND    = 5555
PORT_RECEIVE = 5556
FPS_TARGET   = 20
QUALITY      = 50
CHUNK_SIZE   = 65536

# Colores
C_BG      = get_color_from_hex("#0A0A0F")
C_SURFACE = get_color_from_hex("#12121A")
C_CARD    = get_color_from_hex("#1A1A26")
C_ACCENT  = get_color_from_hex("#4FC3F7")
C_GREEN   = get_color_from_hex("#00E676")
C_TEXT    = get_color_from_hex("#FFFFFF")
C_TEXT2   = get_color_from_hex("#B0B8D0")
C_TEXT3   = get_color_from_hex("#6B7A99")
C_DANGER  = get_color_from_hex("#FF5252")

Window.clearcolor = C_BG


# ════════════════════════════════════════════════════════════════
# CAPTURA DE PANTALLA (Android)
# ════════════════════════════════════════════════════════════════
def capture_screen_android():
    """
    Intenta capturar pantalla en Android via screencap.
    Requiere permisos de MediaProjection en Android 5+.
    En entorno de desarrollo (Desktop), usa PIL.
    """
    try:
        # Android con plyer/screencap
        from android.permissions import request_permissions, Permission
        import subprocess
        result = subprocess.run(
            ["screencap", "-p", "/data/local/tmp/leescreen_frame.png"],
            capture_output=True, timeout=2
        )
        with open("/data/local/tmp/leescreen_frame.png", "rb") as f:
            return f.read()
    except Exception:
        pass

    # Desktop fallback (pruebas en PC)
    try:
        from PIL import ImageGrab, Image
        img = ImageGrab.grab()
        img = img.resize(
            (int(img.width * 0.5), int(img.height * 0.5)),
            Image.LANCZOS
        )
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=QUALITY)
        return buf.getvalue()
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# SENDER THREAD
# ════════════════════════════════════════════════════════════════
class ScreenSenderThread(threading.Thread):
    def __init__(self, target_ip, on_status, on_fps, on_error, on_connect, on_disconnect):
        super().__init__(daemon=True)
        self.target_ip     = target_ip
        self.on_status     = on_status
        self.on_fps        = on_fps
        self.on_error      = on_error
        self.on_connect    = on_connect
        self.on_disconnect = on_disconnect
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
            self._sock.connect((self.target_ip, PORT_RECEIVE))
            self._sock.settimeout(None)
            Clock.schedule_once(lambda dt: self.on_connect())
            Clock.schedule_once(lambda dt: self.on_status(f"Transmitiendo a {self.target_ip}"))

            frame_time  = 1.0 / FPS_TARGET
            fps_counter = 0
            fps_timer   = time.time()

            while self._running:
                t0   = time.time()
                data = capture_screen_android()
                if data is None:
                    time.sleep(0.1)
                    continue

                header = struct.pack(">I", len(data))
                try:
                    self._sock.sendall(header + data)
                except Exception as e:
                    if self._running:
                        Clock.schedule_once(lambda dt, e=e: self.on_error(str(e)))
                    break

                fps_counter += 1
                elapsed = time.time() - fps_timer
                if elapsed >= 1.0:
                    fps = fps_counter / elapsed
                    Clock.schedule_once(lambda dt, f=fps: self.on_fps(f))
                    fps_counter = 0
                    fps_timer   = time.time()

                dt = time.time() - t0
                if dt < frame_time:
                    time.sleep(frame_time - dt)

        except ConnectionRefusedError:
            Clock.schedule_once(lambda dt: self.on_error("Dispositivo no encontrado"))
        except Exception as e:
            if self._running:
                Clock.schedule_once(lambda dt, e=e: self.on_error(str(e)))
        finally:
            Clock.schedule_once(lambda dt: self.on_disconnect())


# ════════════════════════════════════════════════════════════════
# RECEIVER THREAD
# ════════════════════════════════════════════════════════════════
class ScreenReceiverThread(threading.Thread):
    def __init__(self, on_frame, on_status, on_connect, on_disconnect, on_error):
        super().__init__(daemon=True)
        self.on_frame      = on_frame
        self.on_status     = on_status
        self.on_connect    = on_connect
        self.on_disconnect = on_disconnect
        self.on_error      = on_error
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
            self._server.bind(("0.0.0.0", PORT_RECEIVE))
            self._server.listen(1)
            self._server.settimeout(1)
            Clock.schedule_once(lambda dt: self.on_status(f"Esperando en puerto {PORT_RECEIVE}..."))

            while self._running:
                try:
                    conn, addr = self._server.accept()
                except socket.timeout:
                    continue

                ip = addr[0]
                Clock.schedule_once(lambda dt, ip=ip: self.on_connect(ip))
                self._handle_client(conn)
                Clock.schedule_once(lambda dt: self.on_disconnect())

        except Exception as e:
            if self._running:
                Clock.schedule_once(lambda dt, e=e: self.on_error(str(e)))

    def _handle_client(self, conn):
        buf = b""
        try:
            while self._running:
                while len(buf) < 4:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk

                size = struct.unpack(">I", buf[:4])[0]
                buf  = buf[4:]

                while len(buf) < size:
                    needed = size - len(buf)
                    chunk  = conn.recv(min(needed, CHUNK_SIZE))
                    if not chunk:
                        return
                    buf += chunk

                frame_data = buf[:size]
                buf        = buf[size:]

                # Convertir a textura Kivy
                try:
                    core_img = CoreImage(
                        io.BytesIO(frame_data),
                        ext="jpg",
                        nocache=True
                    )
                    Clock.schedule_once(lambda dt, tex=core_img.texture: self.on_frame(tex))
                except Exception:
                    pass

        except Exception:
            pass
        finally:
            try: conn.close()
            except: pass


# ════════════════════════════════════════════════════════════════
# UI HELPERS
# ════════════════════════════════════════════════════════════════
def hex_color(h):
    return get_color_from_hex(h)


class RoundedButton(Button):
    def __init__(self, bg_color="#4FC3F7", text_color="#000000",
                 radius=12, **kwargs):
        super().__init__(**kwargs)
        self.bg_hex    = bg_color
        self.text_color_hex = text_color
        self.radius    = dp(radius)
        self.color     = hex_color(text_color)
        self.background_color = (0, 0, 0, 0)
        self.background_normal = ""
        self.bold      = True
        self.font_size = sp(14)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*hex_color(self.bg_hex))
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[self.radius])


class CardWidget(BoxLayout):
    def __init__(self, bg="#1A1A26", radius=16, **kwargs):
        super().__init__(**kwargs)
        self.bg_hex = bg
        self.radius = dp(radius)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*hex_color(self.bg_hex))
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[self.radius])


class StatusBar(CardWidget):
    def __init__(self, **kwargs):
        super().__init__(
            bg="#1A1A26",
            radius=14,
            orientation="horizontal",
            padding=[dp(16), dp(8)],
            spacing=dp(8),
            size_hint_y=None,
            height=dp(48),
            **kwargs
        )
        self._dot = Label(text="●", font_size=sp(10), size_hint_x=None, width=dp(16))
        self._dot.color = hex_color("#6B7A99")
        self._status = Label(text="Inactivo", font_size=sp(12), halign="left",
                             color=hex_color("#B0B8D0"))
        self._status.bind(size=self._status.setter("text_size"))
        self._right = Label(text="", font_size=sp(12), halign="right",
                            color=hex_color("#4FC3F7"))
        self._right.bind(size=self._right.setter("text_size"))

        self.add_widget(self._dot)
        self.add_widget(self._status)
        self.add_widget(self._right)

    def update(self, text, active=False, right=""):
        self._status.text  = text
        self._right.text   = right
        dot_color  = "#00E676" if active else "#6B7A99"
        text_color = "#FFFFFF" if active else "#B0B8D0"
        self._dot.color    = hex_color(dot_color)
        self._status.color = hex_color(text_color)


# ════════════════════════════════════════════════════════════════
# SCREENS
# ════════════════════════════════════════════════════════════════
class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="home", **kwargs)
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(20))

        with root.canvas.before:
            Color(*C_BG)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *a: setattr(self._bg, "pos", root.pos),
                  size=lambda *a: setattr(self._bg, "size", root.size))

        # Header
        header = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(80))
        title = Label(
            text="LeeScreen",
            font_size=sp(28), bold=True,
            color=C_TEXT, halign="left"
        )
        title.bind(size=title.setter("text_size"))
        sub = Label(
            text="Leecito Projects",
            font_size=sp(12),
            color=C_ACCENT, halign="left"
        )
        sub.bind(size=sub.setter("text_size"))
        header.add_widget(title)
        header.add_widget(sub)
        root.add_widget(header)

        # IP info
        ip_card = CardWidget(
            bg="#1A1A26", radius=14,
            orientation="horizontal",
            size_hint_y=None, height=dp(52),
            padding=[dp(16), 0]
        )
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "Desconocida"

        ip_lbl = Label(
            text=f"📡  Tu IP:  [b][color=4FC3F7]{local_ip}[/color][/b]",
            markup=True, font_size=sp(13),
            color=C_TEXT2, halign="left"
        )
        ip_lbl.bind(size=ip_lbl.setter("text_size"))
        ip_card.add_widget(ip_lbl)
        root.add_widget(ip_card)

        # Botones principales
        btn_send = RoundedButton(
            text="📤  Enviar Pantalla",
            bg_color="#4FC3F7",
            text_color="#000000",
            size_hint_y=None, height=dp(72)
        )
        btn_send.bind(on_press=lambda *a: setattr(
            self.manager, "current", "send"
        ))

        btn_recv = RoundedButton(
            text="📥  Recibir Pantalla",
            bg_color="#7C4DFF",
            text_color="#FFFFFF",
            size_hint_y=None, height=dp(72)
        )
        btn_recv.bind(on_press=lambda *a: setattr(
            self.manager, "current", "receive"
        ))

        root.add_widget(btn_send)
        root.add_widget(btn_recv)

        # Info card
        info = CardWidget(
            bg="#1A1A26", radius=16,
            orientation="vertical",
            padding=[dp(16), dp(14)],
            spacing=dp(6)
        )
        info_title = Label(
            text="ℹ️  Cómo usar",
            font_size=sp(13), bold=True,
            color=C_TEXT, halign="left"
        )
        info_title.bind(size=info_title.setter("text_size"))
        info.add_widget(info_title)

        for step in [
            "1. Ambos dispositivos deben estar en la misma Wi-Fi.",
            "2. Elige 'Enviar' aquí e ingresa la IP del PC/Android receptor.",
            "3. En el receptor, abre LeeScreen → Recibir → Iniciar.",
        ]:
            lbl = Label(text=step, font_size=sp(11), color=C_TEXT2, halign="left")
            lbl.bind(size=lbl.setter("text_size"))
            info.add_widget(lbl)

        root.add_widget(info)
        root.add_widget(Widget())  # spacer

        self.add_widget(root)


class SendScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="send", **kwargs)
        self._sender = None
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))

        with root.canvas.before:
            Color(*C_BG)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *a: setattr(self._bg, "pos", root.pos),
                  size=lambda *a: setattr(self._bg, "size", root.size))

        # Header
        header_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        back_btn = RoundedButton(
            text="← Volver", bg_color="#1A1A26", text_color="#4FC3F7",
            size_hint_x=None, width=dp(100)
        )
        back_btn.bind(on_press=lambda *a: (self._stop(), setattr(self.manager, "current", "home")))
        title = Label(
            text="📤  Enviar Pantalla", font_size=sp(18), bold=True,
            color=C_TEXT, halign="left"
        )
        title.bind(size=title.setter("text_size"))
        header_row.add_widget(back_btn)
        header_row.add_widget(title)
        root.add_widget(header_row)

        # Input IP
        ip_card = CardWidget(
            bg="#1A1A26", radius=14,
            orientation="vertical",
            padding=[dp(14), dp(10)],
            spacing=dp(10),
            size_hint_y=None, height=dp(120)
        )
        lbl_ip = Label(
            text="IP del receptor (Windows o Android):",
            font_size=sp(12), color=C_TEXT2, halign="left"
        )
        lbl_ip.bind(size=lbl_ip.setter("text_size"))

        self._ip_input = TextInput(
            hint_text="192.168.1.x",
            multiline=False,
            font_size=sp(16),
            background_color=hex_color("#12121A"),
            foreground_color=C_TEXT,
            cursor_color=C_ACCENT,
            size_hint_y=None, height=dp(44)
        )
        ip_card.add_widget(lbl_ip)
        ip_card.add_widget(self._ip_input)
        root.add_widget(ip_card)

        # Botones
        btn_row = BoxLayout(orientation="horizontal", spacing=dp(10),
                            size_hint_y=None, height=dp(50))

        self._connect_btn = RoundedButton(
            text="▶  Conectar", bg_color="#00E676", text_color="#000000"
        )
        self._connect_btn.bind(on_press=self._start)

        self._stop_btn = RoundedButton(
            text="■  Detener", bg_color="#FF525230", text_color="#FF5252"
        )
        self._stop_btn.disabled = True
        self._stop_btn.bind(on_press=lambda *a: self._stop())

        btn_row.add_widget(self._connect_btn)
        btn_row.add_widget(self._stop_btn)
        root.add_widget(btn_row)

        # Status bar
        self._status_bar = StatusBar()
        root.add_widget(self._status_bar)

        root.add_widget(Widget())
        self.add_widget(root)

    def _start(self, *args):
        ip = self._ip_input.text.strip()
        if not ip:
            self._status_bar.update("Ingresa una IP válida", False)
            return
        self._stop()
        self._sender = ScreenSenderThread(
            target_ip    = ip,
            on_status    = lambda s: self._status_bar.update(s, True),
            on_fps       = lambda f: self._status_bar.update(
                self._status_bar._status.text, True, f"{f:.1f} FPS"
            ),
            on_error     = lambda e: self._status_bar.update(f"Error: {e}", False),
            on_connect   = lambda: (
                self._stop_btn.__setattr__("disabled", False),
            ),
            on_disconnect = lambda: (
                self._status_bar.update("Desconectado", False),
                self._stop_btn.__setattr__("disabled", True),
            )
        )
        self._sender.start()
        self._status_bar.update(f"Conectando a {ip}...", False)

    def _stop(self):
        if self._sender:
            self._sender.stop()
            self._sender = None
        self._status_bar.update("Sin conexión", False, "")
        self._stop_btn.disabled = True


class ReceiveScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="receive", **kwargs)
        self._receiver = None
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))

        with root.canvas.before:
            Color(*C_BG)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *a: setattr(self._bg, "pos", root.pos),
                  size=lambda *a: setattr(self._bg, "size", root.size))

        # Header
        header_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        back_btn = RoundedButton(
            text="← Volver", bg_color="#1A1A26", text_color="#4FC3F7",
            size_hint_x=None, width=dp(100)
        )
        back_btn.bind(on_press=lambda *a: (self._stop(), setattr(self.manager, "current", "home")))
        title = Label(
            text="📥  Recibir Pantalla", font_size=sp(18), bold=True,
            color=C_TEXT, halign="left"
        )
        title.bind(size=title.setter("text_size"))
        header_row.add_widget(back_btn)
        header_row.add_widget(title)
        root.add_widget(header_row)

        # Botones
        btn_row = BoxLayout(orientation="horizontal", spacing=dp(10),
                            size_hint_y=None, height=dp(50))
        self._start_btn = RoundedButton(
            text="▶  Iniciar", bg_color="#00E676", text_color="#000000"
        )
        self._start_btn.bind(on_press=self._start)

        self._stop_btn = RoundedButton(
            text="■  Detener", bg_color="#FF525230", text_color="#FF5252"
        )
        self._stop_btn.disabled = True
        self._stop_btn.bind(on_press=lambda *a: self._stop())

        btn_row.add_widget(self._start_btn)
        btn_row.add_widget(self._stop_btn)
        root.add_widget(btn_row)

        # Vista de pantalla
        frame_card = CardWidget(
            bg="#1A1A26", radius=16,
            orientation="vertical"
        )
        self._screen_img = KivyImage(
            allow_stretch=True,
            keep_ratio=True
        )
        self._placeholder_lbl = Label(
            text="Esperando transmisión...",
            font_size=sp(14),
            color=hex_color("#6B7A99"),
            halign="center", valign="middle"
        )
        self._placeholder_lbl.bind(size=self._placeholder_lbl.setter("text_size"))
        frame_card.add_widget(self._placeholder_lbl)
        frame_card.add_widget(self._screen_img)
        root.add_widget(frame_card)

        # Status bar
        self._status_bar = StatusBar()
        root.add_widget(self._status_bar)

        self.add_widget(root)

    def _start(self, *args):
        self._stop()
        self._receiver = ScreenReceiverThread(
            on_frame       = self._on_frame,
            on_status      = lambda s: self._status_bar.update(s, False),
            on_connect     = lambda ip: self._status_bar.update(f"Recibiendo de {ip}", True, f"📱 {ip}"),
            on_disconnect  = lambda: (
                self._status_bar.update("Esperando nueva conexión...", False),
                setattr(self._screen_img, "texture", None)
            ),
            on_error       = lambda e: self._status_bar.update(f"Error: {e}", False)
        )
        self._receiver.start()
        self._start_btn.disabled = True
        self._stop_btn.disabled  = False
        self._status_bar.update("Escuchando conexiones...", False)

    def _on_frame(self, texture):
        self._screen_img.texture = texture
        self._placeholder_lbl.text = ""

    def _stop(self):
        if self._receiver:
            self._receiver.stop()
            self._receiver = None
        self._start_btn.disabled = False
        self._stop_btn.disabled  = True
        self._status_bar.update("Inactivo", False, "")
        self._placeholder_lbl.text = "Esperando transmisión..."
        self._screen_img.texture = None


# ════════════════════════════════════════════════════════════════
# APP
# ════════════════════════════════════════════════════════════════
class LeeScreenApp(App):
    def build(self):
        self.title = f"{APP_NAME} — {BRAND}"
        sm = ScreenManager(transition=FadeTransition(duration=0.2))
        sm.add_widget(HomeScreen())
        sm.add_widget(SendScreen())
        sm.add_widget(ReceiveScreen())
        return sm


if __name__ == "__main__":
    LeeScreenApp().run()
