[app]
# ─── Info básica ───────────────────────────────────────────────
title = LeeScreen
package.name = leescreen
package.domain = com.leecitoprojects
version = 1.0
author = Leecito Projects
description = Transmisión de pantalla entre Android y Windows

# ─── Fuente ────────────────────────────────────────────────────
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

# ─── Requisitos ────────────────────────────────────────────────
requirements = python3,kivy==2.3.0,pillow,numpy,opencv-python

# ─── Orientación ───────────────────────────────────────────────
orientation = portrait

# ─── Android ───────────────────────────────────────────────────
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

# Permisos necesarios
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE, FOREGROUND_SERVICE

# ─── Íconos (opcional, puedes reemplazarlos) ───────────────────
# android.icon.filename = %(source.dir)s/icon.png
# android.presplash.filename = %(source.dir)s/splash.png

# ─── Buildozer ─────────────────────────────────────────────────
[buildozer]
log_level = 2
warn_on_root = 1
