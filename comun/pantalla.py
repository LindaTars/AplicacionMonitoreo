"""Captura de pantalla (la usan tanto el servidor como el agente).

- En Wayland (Hyprland, Sway...) usa el programa `grim`  ->  sudo pacman -S grim
- En X11 usa la librería `mss`.
"""
import io
import os
import shutil
import subprocess


def _es_wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"


def _reducir(datos, calidad):
    from PIL import Image

    imagen = Image.open(io.BytesIO(datos)).convert("RGB")
    imagen.thumbnail((1280, 720))
    buffer = io.BytesIO()
    imagen.save(buffer, "JPEG", quality=calidad)
    return buffer.getvalue()


def _capturar_wayland(calidad):
    if not shutil.which("grim"):
        raise RuntimeError("falta instalar grim (sudo pacman -S grim)")
    r = subprocess.run(["grim", "-t", "ppm", "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace").strip() or "grim falló")
    return _reducir(r.stdout, calidad)


def _capturar_x11(calidad):
    import mss
    from PIL import Image

    clase = getattr(mss, "MSS", None) or mss.mss  # versiones nuevas: MSS
    with clase() as sct:
        foto = sct.grab(sct.monitors[1])
        imagen = Image.frombytes("RGB", foto.size, foto.bgra, "raw", "BGRX")
    imagen.thumbnail((1280, 720))
    buffer = io.BytesIO()
    imagen.save(buffer, "JPEG", quality=calidad)
    return buffer.getvalue()


def capturar_jpeg(calidad=50):
    if _es_wayland():
        return _capturar_wayland(calidad)
    return _capturar_x11(calidad)
