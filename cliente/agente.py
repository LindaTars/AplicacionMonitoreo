"""Agente (cliente): corre en cada PC que será controlada.

Uso:  sudo -E venv/bin/python cliente/agente.py IP_DEL_SERVIDOR [nombre]

Necesita sudo porque editar /etc/hosts y el ping requieren permisos de administrador.
"""
import io
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun.protocolo import Conexion, PUERTO, TOKEN  # noqa: E402

CARPETA_RECIBIDOS = Path("recibidos_agente")
HOSTS = Path("/etc/hosts")
MARCA_INI = "# >>> BLOQUEO-APP"
MARCA_FIN = "# <<< BLOQUEO-APP"
SEGUNDOS_BLOQUEO_MAX = 120  # seguridad: el teclado se desbloquea solo


# ---------- utilidades ----------
def correr(comando):
    r = subprocess.run(comando, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"falló {comando[0]}")
    return r.stdout


def exigir_root():
    if os.geteuid() != 0:
        raise PermissionError("el agente debe ejecutarse con sudo")


def capturar_jpeg(calidad=50):
    import mss
    from PIL import Image

    with mss.mss() as sct:
        foto = sct.grab(sct.monitors[1])
        imagen = Image.frombytes("RGB", foto.size, foto.bgra, "raw", "BGRX")
    imagen.thumbnail((1280, 720))
    buffer = io.BytesIO()
    imagen.save(buffer, "JPEG", quality=calidad)
    return buffer.getvalue()


def dispositivos_entrada():
    """IDs de teclados y mouse reales (X11)."""
    salida = correr(["xinput", "list"])
    ids = []
    for linea in salida.splitlines():
        m = re.search(r"id=(\d+)\s+\[slave\s+(pointer|keyboard)", linea)
        if m and "XTEST" not in linea and "Virtual" not in linea:
            ids.append(m.group(1))
    return ids


# ---------- puntos 3.9 y 3.10 ----------
def permitir_webs():
    exigir_root()
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


def bloquear_webs(sitios):
    exigir_root()
    permitir_webs()  # quita bloqueos anteriores
    nuevas = [MARCA_INI]
    for sitio in sitios:
        sitio = sitio.strip().lower().removeprefix("www.")
        if re.fullmatch(r"[a-z0-9.-]+", sitio):  # evita meter basura en /etc/hosts
            nuevas += [f"127.0.0.1 {sitio}", f"127.0.0.1 www.{sitio}"]
    nuevas.append(MARCA_FIN)
    with HOSTS.open("a") as f:
        f.write("\n".join(nuevas) + "\n")


def cambiar_ping(permitir):
    exigir_root()
    valor = "0" if permitir else "1"
    correr(["sysctl", "-w", f"net.ipv4.icmp_echo_ignore_all={valor}"])


# ---------- el agente ----------
class Agente:
    def __init__(self, ip, nombre):
        self.ip = ip
        self.nombre = nombre
        self.con = None
        self.viendo = threading.Event()
        self.bloqueados = []
        self.temporizador = None

    def conectar(self):
        sock = socket.create_connection((self.ip, PUERTO), timeout=10)
        sock.settimeout(None)
        self.con = Conexion(sock)
        self.con.enviar("hola", {"token": TOKEN, "nombre": self.nombre})
        print(f"Conectado a {self.ip}:{PUERTO} como '{self.nombre}'")

    # 3.1 / 3.4: mandar la pantalla
    def hilo_pantalla(self):
        while True:
            self.viendo.wait()
            try:
                self.con.enviar("imagen", binario=capturar_jpeg())
            except Exception as e:
                print("Error enviando pantalla:", e)
                self.viendo.clear()
            time.sleep(0.5)

    # 3.2 / 3.3: chat y archivos desde este lado
    def hilo_teclado(self):
        print("Escribe para chatear. Para mandar un archivo: /enviar ruta")
        for linea in sys.stdin:
            linea = linea.strip()
            if not linea:
                continue
            try:
                if linea.startswith("/enviar "):
                    ruta = Path(linea[8:].strip()).expanduser()
                    self.con.enviar("archivo", {"nombre": ruta.name}, ruta.read_bytes())
                    print("Archivo enviado.")
                else:
                    self.con.enviar("chat", {"texto": linea})
            except Exception as e:
                print("Error:", e)

    # 3.6 / 3.7: bloquear y desbloquear teclado y mouse
    def bloquear(self):
        if self.bloqueados:
            return "Ya estaba bloqueado"
        for id_ in dispositivos_entrada():
            correr(["xinput", "disable", id_])
            self.bloqueados.append(id_)
        self.temporizador = threading.Timer(SEGUNDOS_BLOQUEO_MAX, self.desbloquear)
        self.temporizador.start()
        return f"Bloqueado (se desbloquea solo en {SEGUNDOS_BLOQUEO_MAX} s)"

    def desbloquear(self):
        if self.temporizador:
            self.temporizador.cancel()
            self.temporizador = None
        for id_ in self.bloqueados:
            subprocess.run(["xinput", "enable", id_], capture_output=True)
        self.bloqueados = []
        return "Desbloqueado"

    def ejecutar(self, tipo, datos, binario):
        if tipo == "chat":
            print(f"\n[Servidor] {datos.get('texto', '')}")
            return
        if tipo == "ver_pantalla":
            if datos.get("activo"):
                self.viendo.set()
            else:
                self.viendo.clear()
            return
        try:
            if tipo == "archivo":
                CARPETA_RECIBIDOS.mkdir(exist_ok=True)
                destino = CARPETA_RECIBIDOS / Path(datos.get("nombre", "archivo")).name
                destino.write_bytes(binario)
                mensaje = f"Archivo guardado en {destino}"
            elif tipo == "bloquear":
                mensaje = self.bloquear()
            elif tipo == "desbloquear":
                mensaje = self.desbloquear()
            elif tipo == "bloquear_webs":
                bloquear_webs(datos.get("sitios", []))
                mensaje = "Páginas bloqueadas"
            elif tipo == "permitir_webs":
                permitir_webs()
                mensaje = "Páginas permitidas"
            elif tipo == "ping":
                cambiar_ping(datos.get("permitir", True))
                mensaje = "Ping permitido" if datos.get("permitir") else "Ping negado"
            elif tipo == "apagar":
                self.con.enviar("estado", {"ok": True, "mensaje": "Apagando..."})
                correr(["systemctl", "poweroff"])
                return
            else:
                raise ValueError(f"orden desconocida: {tipo}")
            self.con.enviar("estado", {"ok": True, "mensaje": mensaje})
        except Exception as e:
            self.con.enviar("estado", {"ok": False, "mensaje": f"{tipo}: {e}"})


def main():
    if len(sys.argv) < 2:
        print("Uso: sudo -E venv/bin/python cliente/agente.py IP_DEL_SERVIDOR [nombre]")
        sys.exit(1)
    nombre = sys.argv[2] if len(sys.argv) > 2 else socket.gethostname()
    agente = Agente(sys.argv[1], nombre)
    agente.conectar()
    threading.Thread(target=agente.hilo_pantalla, daemon=True).start()
    threading.Thread(target=agente.hilo_teclado, daemon=True).start()
    try:
        while True:
            msg = agente.con.recibir()
            if msg is None:
                print("Se perdió la conexión con el servidor.")
                break
            agente.ejecutar(*msg)
    except KeyboardInterrupt:
        pass
    finally:
        agente.desbloquear()  # nunca dejar el teclado bloqueado al salir


if __name__ == "__main__":
    main()