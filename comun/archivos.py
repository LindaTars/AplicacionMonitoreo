"""Ayudas para archivos: selector del sistema y abrir carpetas."""
import shutil
import subprocess
from pathlib import Path

LIMITE_MB = 150  # el protocolo acepta hasta 200 MB por mensaje


def elegir_archivo(titulo="Elegir archivo"):
    """Abre el selector de archivos del sistema (zenity o kdialog).
    Si no hay ninguno instalado, usa el de Tk. Devuelve la ruta o None."""
    inicio = str(Path.home())
    opciones = [
        ["zenity", "--file-selection", "--title", titulo, "--filename", inicio + "/"],
        ["kdialog", "--title", titulo, "--getopenfilename", inicio],
    ]
    for comando in opciones:
        if shutil.which(comando[0]):
            r = subprocess.run(comando, capture_output=True, text=True)
            return r.stdout.strip() or None
    from tkinter import filedialog

    return filedialog.askopenfilename(title=titulo, initialdir=inicio) or None


def abrir_carpeta(ruta):
    ruta = Path(ruta)
    ruta.mkdir(exist_ok=True)
    subprocess.Popen(["xdg-open", str(ruta)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def demasiado_grande(ruta):
    return Path(ruta).stat().st_size > LIMITE_MB * 1024 * 1024
