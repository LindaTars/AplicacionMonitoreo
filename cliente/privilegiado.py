"""Ayudante con permisos de administrador. Lo llama el agente con `sudo -n`.

Así el agente y su ventana corren con TU usuario (para que funcionen la pantalla,
el micrófono y la cámara) y solo estas pocas tareas corren como administrador.

Acciones:
  bloquear-webs sitio1,sitio2   |  permitir-webs
  ping permitir|negar
  bloquear-entrada SEGUNDOS     (se queda corriendo hasta que el agente cierre su stdin)
"""
import fcntl
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

HOSTS = Path("/etc/hosts")
MARCA_INI = "# >>> BLOQUEO-APP"
MARCA_FIN = "# <<< BLOQUEO-APP"

EVIOCGRAB = 0x40044590  # orden del kernel: "este programa se queda con el dispositivo"
LIBRES = ("power button", "sleep button", "lid switch", "video bus")  # no se bloquean


def limpiar_cache_dns():
    """Para que el cambio se note de inmediato (si el sistema usa systemd-resolved)."""
    try:
        subprocess.run(["resolvectl", "flush-caches"], capture_output=True)
    except FileNotFoundError:
        pass


# ---------- páginas web (3.9) ----------
def permitir_webs():
    lineas = HOSTS.read_text().splitlines()
    limpias, dentro = [], False
    for linea in lineas:
        if linea.strip() == MARCA_INI:
            dentro = True
        elif linea.strip() == MARCA_FIN:
            dentro = False
        elif not dentro:
            limpias.append(linea)
    HOSTS.write_text("\n".join(limpias) + "\n")
    limpiar_cache_dns()


def bloquear_webs(sitios):
    permitir_webs()  # quita bloqueos anteriores
    nuevas = [MARCA_INI]
    for sitio in sitios:
        sitio = sitio.strip().lower().removeprefix("www.")
        if re.fullmatch(r"[a-z0-9.-]+", sitio):  # evita meter basura en /etc/hosts
            nuevas += [f"127.0.0.1 {sitio}", f"127.0.0.1 www.{sitio}",
                       f"::1 {sitio}", f"::1 www.{sitio}"]  # ::1 = lo mismo para IPv6
    nuevas.append(MARCA_FIN)
    with HOSTS.open("a") as f:
        f.write("\n".join(nuevas) + "\n")
    limpiar_cache_dns()


# ---------- ping (3.10) ----------
def cambiar_ping(permitir):
    valor = "0" if permitir else "1"
    r = subprocess.run(["sysctl", "-w", f"net.ipv4.icmp_echo_ignore_all={valor}"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "sysctl falló")


# ---------- teclado y mouse (3.6 y 3.7) ----------
def dispositivos():
    """Rutas /dev/input/eventN de teclados y mouse/touchpad."""
    rutas = []
    texto = Path("/proc/bus/input/devices").read_text()
    for bloque in texto.strip().split("\n\n"):
        nombre = re.search(r'Name="(.*)"', bloque)
        manejadores = re.search(r"Handlers=(.*)", bloque)
        if not nombre or not manejadores:
            continue
        if any(x in nombre.group(1).lower() for x in LIBRES):
            continue
        m = manejadores.group(1)
        evento = re.search(r"\bevent(\d+)", m)
        if evento and re.search(r"\b(kbd|mouse\d+)\b", m):
            rutas.append(f"/dev/input/event{evento.group(1)}")
    return rutas


def bloquear_entrada(segundos):
    """Toma control exclusivo de teclado y mouse. Funciona igual en X11 y Wayland.
    Se suelta solo cuando: pasa el tiempo, el agente cierra stdin o este programa muere."""
    fds = []
    for ruta in dispositivos():
        try:
            fd = os.open(ruta, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            fcntl.ioctl(fd, EVIOCGRAB, 1)
            fds.append(fd)
        except OSError:
            os.close(fd)
    if not fds:
        print("error: no se pudo bloquear ningún dispositivo", flush=True)
        return 1
    print(f"listo {len(fds)}", flush=True)
    fin = time.time() + segundos
    while time.time() < fin:
        listo, _, _ = select.select([0], [], [], 0.5)
        if listo and not os.read(0, 1024):  # el agente cerró la conexión: desbloquear
            break
    for fd in fds:
        os.close(fd)  # al cerrar el archivo, el kernel suelta el dispositivo
    return 0


def main():
    if os.geteuid() != 0:
        print("este ayudante debe correr con sudo", file=sys.stderr)
        return 1
    if len(sys.argv) < 2:
        print("falta la acción", file=sys.stderr)
        return 1
    accion = sys.argv[1]
    try:
        if accion == "bloquear-webs":
            bloquear_webs(sys.argv[2].split(",") if len(sys.argv) > 2 else [])
        elif accion == "permitir-webs":
            permitir_webs()
        elif accion == "ping":
            cambiar_ping(sys.argv[2] == "permitir")
        elif accion == "bloquear-entrada":
            return bloquear_entrada(int(sys.argv[2]))
        else:
            print(f"acción desconocida: {accion}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
