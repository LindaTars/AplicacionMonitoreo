"""Agente (cliente) con ventana: corre en cada PC que será controlada.

Antes (una sola vez por sesión, SIN sudo):   xhost +SI:localuser:root
Uso:  sudo -E .venv/bin/python cliente/agente.py IP_DEL_SERVIDOR [nombre]

Necesita sudo porque editar /etc/hosts y el ping requieren permisos de administrador.
"""
import io
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun.pantalla import capturar_jpeg  # noqa: E402
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


def carpeta_inicio():
    """Carpeta del usuario real (aunque el agente corra con sudo)."""
    usuario = os.environ.get("SUDO_USER")
    return Path(f"~{usuario}").expanduser() if usuario else Path.home()


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
        self.viendo = threading.Event()   # ¿el servidor está viendo mi pantalla?
        self.bloqueados = []
        self.temporizador = None
        self.cola = queue.Queue()         # lo que pasa en los hilos de red
        self.foto = None
        self.viendo_servidor = False
        self._armar_ventana()

    # ---------- ventana ----------
    def _armar_ventana(self):
        self.raiz = tk.Tk()
        self.raiz.title(f"Agente {self.nombre}")

        self.vacio = tk.PhotoImage(width=640, height=360)
        self.vacio.put("black", to=(0, 0, 640, 360))
        self.pantalla = tk.Label(self.raiz, image=self.vacio)
        self.pantalla.pack(padx=6, pady=6)

        barra = tk.Frame(self.raiz)
        barra.pack(fill="x", padx=6)
        self.boton_ver = tk.Button(barra, text="Ver pantalla del servidor", command=self.alternar_servidor)
        self.boton_ver.pack(side="left")
        tk.Button(barra, text="Enviar archivo", command=self.enviar_archivo).pack(side="left", padx=4)
        self.estado = tk.Label(barra, text="Conectando...", fg="orange")
        self.estado.pack(side="right")

        self.chat = tk.Text(self.raiz, height=10, state="disabled")
        self.chat.pack(fill="both", expand=True, padx=6, pady=6)
        escribir = tk.Frame(self.raiz)
        escribir.pack(fill="x", padx=6, pady=(0, 6))
        self.entrada = tk.Entry(escribir)
        self.entrada.pack(side="left", fill="x", expand=True)
        self.entrada.bind("<Return>", lambda e: self.enviar_chat())
        tk.Button(escribir, text="Enviar", command=self.enviar_chat).pack(side="left")

        self.raiz.protocol("WM_DELETE_WINDOW", self.cerrar)

    def _escribir(self, texto):
        self.chat.config(state="normal")
        self.chat.insert("end", texto + "\n")
        self.chat.see("end")
        self.chat.config(state="disabled")

    def _enviar(self, tipo, datos=None, binario=b""):
        try:
            self.con.enviar(tipo, datos, binario)
            return True
        except Exception as e:
            self._escribir(f"[sistema] no se pudo enviar: {e}")
            return False

    # ---------- botones ----------
    def enviar_chat(self):
        texto = self.entrada.get().strip()
        if texto and self._enviar("chat", {"texto": texto}):
            self._escribir(f"Tú: {texto}")
            self.entrada.delete(0, "end")

    def enviar_archivo(self):
        ruta = filedialog.askopenfilename(initialdir=carpeta_inicio())
        if ruta:
            ruta = Path(ruta)
            if self._enviar("archivo", {"nombre": ruta.name}, ruta.read_bytes()):
                self._escribir(f"[sistema] archivo '{ruta.name}' enviado al servidor")

    def alternar_servidor(self):
        self.viendo_servidor = not self.viendo_servidor
        self._enviar("ver_servidor", {"activo": self.viendo_servidor})
        if self.viendo_servidor:
            self.boton_ver.config(text="Dejar de ver el servidor")
        else:
            self.boton_ver.config(text="Ver pantalla del servidor")
            self.pantalla.config(image=self.vacio)

    # ---------- red ----------
    def iniciar(self):
        try:
            sock = socket.create_connection((self.ip, PUERTO), timeout=10)
            sock.settimeout(None)
            self.con = Conexion(sock)
            self.con.enviar("hola", {"token": TOKEN, "nombre": self.nombre})
        except OSError as e:
            messagebox.showerror("No se pudo conectar", f"{self.ip}:{PUERTO}\n{e}")
            self.raiz.destroy()
            return
        self.estado.config(text=f"Conectado a {self.ip}", fg="green")
        threading.Thread(target=self._hilo_red, daemon=True).start()
        threading.Thread(target=self._hilo_pantalla, daemon=True).start()
        self.raiz.after(100, self._procesar_cola)
        try:
            self.raiz.mainloop()
        finally:
            self.desbloquear()  # nunca dejar el teclado bloqueado al salir

    def _hilo_red(self):
        while True:
            msg = self.con.recibir()
            if msg is None:
                self.cola.put(("desconectado", None))
                return
            self.ejecutar(*msg)

    # 3.1 / 3.4: mandar mi pantalla cuando el servidor la pide
    def _hilo_pantalla(self):
        while True:
            self.viendo.wait()
            try:
                self.con.enviar("imagen", binario=capturar_jpeg())
            except Exception as e:
                self.cola.put(("log", f"Error enviando pantalla: {e}"))
                self.viendo.clear()
            time.sleep(0.5)

    def _procesar_cola(self):
        try:
            while True:
                evento, dato = self.cola.get_nowait()
                if evento == "chat":
                    self._escribir(f"Servidor: {dato}")
                elif evento == "log":
                    self._escribir(f"[sistema] {dato}")
                elif evento == "imagen":
                    imagen = Image.open(io.BytesIO(dato))
                    imagen.thumbnail((640, 360))
                    self.foto = ImageTk.PhotoImage(imagen)
                    if self.viendo_servidor:
                        self.pantalla.config(image=self.foto)
                elif evento == "desconectado":
                    self.estado.config(text="Desconectado", fg="red")
                    self._escribir("[sistema] se perdió la conexión con el servidor")
        except queue.Empty:
            pass
        self.raiz.after(100, self._procesar_cola)

    # ---------- 3.6 / 3.7: bloquear y desbloquear teclado y mouse ----------
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

    # ---------- órdenes del servidor (corren en el hilo de red) ----------
    def ejecutar(self, tipo, datos, binario):
        if tipo == "chat":
            self.cola.put(("chat", datos.get("texto", "")))
            return
        if tipo == "imagen_servidor":
            self.cola.put(("imagen", binario))
            return
        if tipo == "estado":  # avisos del servidor (por ejemplo, error al capturar su pantalla)
            self.cola.put(("log", datos.get("mensaje", "")))
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
            self.cola.put(("log", mensaje))
            self.con.enviar("estado", {"ok": True, "mensaje": mensaje})
        except Exception as e:
            self.cola.put(("log", f"ERROR en {tipo}: {e}"))
            self.con.enviar("estado", {"ok": False, "mensaje": f"{tipo}: {e}"})

    def cerrar(self):
        self.desbloquear()
        if self.con:
            self.con.cerrar()
        self.raiz.destroy()


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else None
    nombre = sys.argv[2] if len(sys.argv) > 2 else socket.gethostname()
    if not ip:  # sin argumentos: la pide en una ventanita
        temporal = tk.Tk()
        temporal.withdraw()
        ip = simpledialog.askstring("Conectar", "IP del servidor:")
        temporal.destroy()
        if not ip:
            return
    Agente(ip.strip(), nombre).iniciar()


if __name__ == "__main__":
    main()
