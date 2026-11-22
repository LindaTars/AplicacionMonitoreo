"""Diagnóstico: revisa qué le falta a ESTA PC para pantalla, llamadas, páginas y ping.

Uso (desde la carpeta del proyecto, dentro de Hyprland):
    sudo -v
    .venv/bin/python cliente/diagnostico.py

Pega todo lo que imprima en el chat. Hay que correrlo en las DOS PCs.
"""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

AYUDANTE = Path(__file__).with_name("privilegiado.py")
PING = Path("/proc/sys/net/ipv4/icmp_echo_ignore_all")


def titulo(texto):
    print(f"\n=== {texto} ===")


def ok(texto):
    print(f"  OK     {texto}")


def falla(texto, ayuda=""):
    print(f"  FALLA  {texto}")
    if ayuda:
        print(f"         -> {ayuda}")


def como_admin(*args):
    return subprocess.run(["sudo", "-n", sys.executable, str(AYUDANTE), *args], capture_output=True, text=True)


def revisar_pantalla():
    titulo("1. VER PANTALLA")
    print(
        f"  Sesión: WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY')} "
        f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE')} DISPLAY={os.environ.get('DISPLAY')}"
    )
    if (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland") and not shutil.which("grim"):
        falla("grim no está instalado", "sudo pacman -S grim")
        return
    try:
        from comun.pantalla import capturar_jpeg

        datos = capturar_jpeg()
        ok(f"captura correcta ({len(datos) // 1024} KB)")
    except Exception as e:
        falla(f"no se pudo capturar la pantalla: {e}", "Corre esto dentro de Hyprland (no por SSH ni con sudo).")


def revisar_audio():
    titulo("2. LLAMADAS - AUDIO")
    try:
        import sounddevice as sd
    except Exception as e:
        falla(f"no se pudo cargar sounddevice: {e}", "sudo pacman -S portaudio   y luego   pip install -r requirements.txt")
        return
    try:
        dispositivos = sd.query_devices()
    except Exception as e:
        falla(f"no se pudo listar el audio: {e}", "sudo pacman -S pipewire-alsa")
        return
    entradas = [d["name"] for d in dispositivos if d["max_input_channels"] > 0]
    salidas = [d["name"] for d in dispositivos if d["max_output_channels"] > 0]
    if entradas:
        ok(f"micrófonos encontrados: {len(entradas)} (primero: {entradas[0]})")
    else:
        falla("no se ve ningún micrófono", "sudo pacman -S pipewire-alsa   y luego   systemctl --user restart pipewire pipewire-pulse wireplumber")
    if salidas:
        ok(f"bocinas encontradas: {len(salidas)} (primera: {salidas[0]})")
    else:
        falla("no se ven bocinas", "sudo pacman -S pipewire-alsa")
    try:
        with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", blocksize=512) as entrada:
            entrada.read(512)
        ok("el micrófono se puede abrir")
    except Exception as e:
        falla(f"no se pudo abrir el micrófono: {e}")
    try:
        with sd.RawOutputStream(samplerate=16000, channels=1, dtype="int16", blocksize=512) as salida:
            salida.write(bytes(1024))
        ok("las bocinas se pueden abrir")
    except Exception as e:
        falla(f"no se pudo abrir las bocinas: {e}")


def revisar_camara():
    titulo("3. VIDEOLLAMADA - CÁMARA")
    try:
        import cv2
    except Exception as e:
        falla(f"no se pudo cargar opencv: {e}", "pip install -r requirements.txt")
        return
    videos = sorted(str(p) for p in Path("/dev").glob("video*"))
    print(f"  Dispositivos de video: {videos or 'ninguno'}")
    camara = cv2.VideoCapture(0)
    if camara.isOpened():
        bien, cuadro = camara.read()
        if bien:
            ok(f"la cámara funciona ({cuadro.shape[1]}x{cuadro.shape[0]})")
        else:
            falla("la cámara abre pero no da imagen", "Revisa que otro programa no la esté usando.")
    else:
        falla("no se pudo abrir la cámara 0", "Revisa que otro programa no la use y que tu usuario esté en el grupo 'video' (comando: groups).")
    camara.release()


def revisar_admin():
    titulo("4. PERMISOS DE ADMINISTRADOR (páginas, ping, bloqueo)")
    try:
        autorizado = subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0
    except FileNotFoundError:
        falla("no está instalado sudo", "sudo pacman -S sudo")
        return False
    if not autorizado:
        falla("sudo está pidiendo contraseña", "Corre 'sudo -v' en ESTA terminal y vuelve a ejecutar el diagnóstico.")
        return False
    ok("sudo ya está autorizado")
    r = como_admin("permitir-webs")
    if r.returncode == 0:
        ok("el ayudante de administrador funciona")
    else:
        falla(f"el ayudante falló: {(r.stderr or r.stdout).strip()}")
        return False
    return True


def revisar_paginas():
    titulo("5. BLOQUEO DE PÁGINAS")
    sitio = "prueba-bloqueo-app.test"
    r = como_admin("bloquear-webs", sitio)
    if r.returncode != 0:
        falla(f"no se pudo escribir en /etc/hosts: {(r.stderr or r.stdout).strip()}")
        return
    ok("se escribió el bloqueo en /etc/hosts")
    try:
        ip = socket.gethostbyname(sitio)
        if ip == "127.0.0.1":
            ok("el sistema SÍ respeta el bloqueo (el sitio apunta a 127.0.0.1)")
            print("         Si el navegador aún abre las páginas: apaga 'Usar DNS seguro' en Brave")
            print("         (Configuración > Privacidad y seguridad > Seguridad) y reinicia el navegador.")
        else:
            falla(f"el sistema resolvió {ip} en vez de 127.0.0.1", "Revisa la línea 'hosts:' en /etc/nsswitch.conf (debe incluir 'files').")
    except OSError as e:
        falla(f"el sistema no pudo resolver el sitio de prueba: {e}")
    como_admin("permitir-webs")  # limpiar la prueba


def revisar_ping():
    titulo("6. BLOQUEO DE PING")
    r = como_admin("ping", "negar")
    if r.returncode != 0:
        falla(f"no se pudo cambiar el ping: {(r.stderr or r.stdout).strip()}")
        return
    valor = PING.read_text().strip() if PING.exists() else "?"
    if valor == "1":
        ok("ping NEGADO (valor 1). Prueba desde la OTRA PC: ping IP_DE_ESTA_PC  -> no debe responder")
    else:
        falla(f"el valor quedó en {valor}, debería ser 1")
    como_admin("ping", "permitir")
    valor = PING.read_text().strip() if PING.exists() else "?"
    if valor == "0":
        ok("ping permitido otra vez (valor 0)")
    else:
        falla(f"no se pudo volver a permitir el ping (valor {valor})")


def main():
    print("Diagnóstico de la aplicación de monitoreo")
    revisar_pantalla()
    revisar_audio()
    revisar_camara()
    if revisar_admin():
        revisar_paginas()
        revisar_ping()
    print("\nListo. Copia TODO este resultado y pégalo en el chat.")


if __name__ == "__main__":
    main()
