"""Agente (cliente) con ventana: corre en cada PC que será controlada.

Uso:  .venv/bin/python cliente/agente.py IP_DEL_SERVIDOR [nombre]

Corre con TU usuario (sin sudo). Al iniciar pide tu contraseña de administrador una
sola vez en la terminal; con ella usa `privilegiado.py` para bloquear teclado/mouse,
editar /etc/hosts y cambiar el ping.
"""
import io
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import tema  # noqa: E402
from comun.archivos import abrir_carpeta, demasiado_grande, elegir_archivo  # noqa: E402
from comun.llamada import Llamada, VentanaLlamada  # noqa: E402
from comun.pantalla import capturar_jpeg  # noqa: E402
from comun.protocolo import Conexion, PUERTO, TOKEN  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_RECIBIDOS = RAIZ / "recibidos_agente"
AYUDANTE = Path(__file__).with_name("privilegiado.py")
SEGUNDOS_BLOQUEO_MAX = 120  # seguridad: el teclado se desbloquea solo


def correr(comando):
    r = subprocess.run(comando, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"falló {comando[0]}")
    return r.stdout


def como_admin(*args):
    """Ejecuta una acción de privilegiado.py con sudo (sin pedir contraseña otra vez)."""
    return correr(["sudo", "-n", sys.executable, str(AYUDANTE), *args])


def mantener_sudo():
    while True:
        time.sleep(120)
        subprocess.run(["sudo", "-n", "-v"], capture_output=True)


class Agente:
    def __init__(self, ip, nombre):
        self.ip = ip
        self.nombre = nombre
        self.con = None
        self.cola = queue.Queue()          # lo que pasa en los hilos de red
        self.viendo = threading.Event()    # ¿el servidor está viendo mi pantalla?
        self.viendo_servidor = False
        self.foto = None
        self.bloqueador = None             # proceso que tiene bloqueados teclado y mouse
        self.llamada = Llamada(lambda t: self.cola.put(("log", t)))
        self.ventana_llamada = None
        self.en_llamada = False
        self.llamando = False
        self.video_pedido = False
        self._armar_ventana()

    # ---------- ventana ----------
    def _armar_ventana(self):
        self.raiz = tk.Tk()
        self.raiz.title(f"Agente {self.nombre}")
        self.raiz.geometry("900x720")
        self.raiz.minsize(800, 640)
        tema.aplicar(self.raiz)

        cabecera = ttk.Frame(self.raiz, padding=(20, 14))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text=f"Agente: {self.nombre}", style="Titulo.TLabel").pack(side="left")
        self.estado = ttk.Label(cabecera, text="Conectando...", style="Suave.TLabel")
        self.estado.configure(foreground=tema.COLORES["amarillo"])
        self.estado.pack(side="right")

        self.apartados = ttk.Notebook(self.raiz)
        self.apartados.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # --- apartado Servidor: ver lo que hace el servidor (punto 3.5)
        servidor = ttk.Frame(self.apartados, padding=18)
        self.apartados.add(servidor, text="Servidor")
        ttk.Label(servidor, text="Pantalla del servidor", style="Seccion.TLabel").pack(anchor="w", pady=(0, 10))
        tarjeta = ttk.Frame(servidor, style="Tarjeta.TFrame", padding=10)
        tarjeta.pack(anchor="w")
        self.vacio = tk.PhotoImage(width=640, height=360)
        self.vacio.put("#000000", to=(0, 0, 640, 360))
        self.pantalla = tk.Label(tarjeta, image=self.vacio, bd=0, bg="#000000")
        self.pantalla.pack()
        self.boton_ver = ttk.Button(servidor, text="Ver pantalla del servidor", style="Acento.TButton",
                                    command=self.alternar_servidor)
        self.boton_ver.pack(anchor="w", pady=14)

        # --- apartado Comunicación: chat, archivos y llamadas
        self.marco_comunicacion = ttk.Frame(self.apartados, padding=18)
        comunicacion = self.marco_comunicacion
        self.apartados.add(comunicacion, text="Comunicación")
        comunicacion.columnconfigure(0, weight=1)
        comunicacion.rowconfigure(0, weight=1)

        chat = tema.tarjeta(comunicacion, "Chat con el servidor")
        chat.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        zona, self.chat = tema.texto_con_barra(chat)
        zona.pack(fill="both", expand=True)
        escribir = ttk.Frame(chat, style="Tarjeta.TFrame")
        escribir.pack(fill="x", pady=(10, 0))
        self.entrada = ttk.Entry(escribir)
        self.entrada.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entrada.bind("<Return>", lambda e: self.enviar_chat())
        ttk.Button(escribir, text="Enviar", style="Acento.TButton", command=self.enviar_chat).pack(side="left")

        lado = ttk.Frame(comunicacion)
        lado.grid(row=0, column=1, sticky="n")
        archivos = tema.tarjeta(lado, "Archivos")
        archivos.pack(fill="x", padx=8, pady=8)
        tema.botones(archivos, [
            ("Enviar archivo", "Acento.TButton", self.enviar_archivo),
            ("Abrir recibidos", "TButton", lambda: abrir_carpeta(CARPETA_RECIBIDOS)),
        ], "Los archivos recibidos se guardan en la carpeta recibidos_agente.")
        llamadas = tema.tarjeta(lado, "Llamadas")
        llamadas.pack(fill="x", padx=8, pady=8)
        tema.botones(llamadas, [
            ("Llamar", "TButton", lambda: self.llamar(False)),
            ("Videollamada", "Acento.TButton", lambda: self.llamar(True)),
        ], "Usen audífonos para evitar el eco.")

        # --- apartado Registro: lo que va pasando
        registro = ttk.Frame(self.apartados, padding=18)
        self.apartados.add(registro, text="Registro")
        zona, self.registro = tema.texto_con_barra(registro, alto=20)
        zona.pack(fill="both", expand=True)

        self.apartados.bind("<<NotebookTabChanged>>", self._pestana_cambio)
        self.raiz.protocol("WM_DELETE_WINDOW", self.cerrar)

    def _escribir(self, texto):
        """Escribe en el apartado Registro."""
        etiqueta = "error" if ("ERROR" in texto or "no se pudo" in texto.lower()) else "suave"
        tema.agregar_linea(self.registro, texto, etiqueta)

    def _escribir_chat(self, texto, propio=False):
        tema.agregar_linea(self.chat, texto, "propio" if propio else "otro")

    def _aviso_chat(self):
        """Marca el apartado Comunicación si llega un mensaje y no se está viendo."""
        if self.apartados.select() != str(self.marco_comunicacion):
            self.apartados.tab(self.marco_comunicacion, text="Comunicación ●")

    def _pestana_cambio(self, _evento=None):
        self.apartados.tab(self.marco_comunicacion, text="Comunicación")

    def _enviar(self, tipo, datos=None, binario=b""):
        try:
            self.con.enviar(tipo, datos, binario)
            return True
        except Exception as e:
            self._escribir(f"[sistema] no se pudo enviar: {e}")
            return False

    # ---------- chat, archivos, pantalla del servidor ----------
    def enviar_chat(self):
        texto = self.entrada.get().strip()
        if texto and self._enviar("chat", {"texto": texto}):
            self._escribir_chat(f"Tú: {texto}", propio=True)
            self.entrada.delete(0, "end")

    def enviar_archivo(self):
        ruta = elegir_archivo("Elegir archivo para enviar al servidor")
        if not ruta:
            return
        ruta = Path(ruta)
        if demasiado_grande(ruta):
            self._escribir("[sistema] el archivo es demasiado grande (máximo 150 MB)")
            return
        threading.Thread(target=self._enviar_archivo_hilo, args=(ruta,), daemon=True).start()

    def _enviar_archivo_hilo(self, ruta):
        self.cola.put(("log", f"Enviando '{ruta.name}'..."))
        try:
            self.con.enviar("archivo", {"nombre": ruta.name}, ruta.read_bytes())
            self.cola.put(("log", f"Archivo '{ruta.name}' enviado al servidor"))
        except Exception as e:
            self.cola.put(("log", f"No se pudo enviar '{ruta.name}': {e}"))

    def alternar_servidor(self):
        self.viendo_servidor = not self.viendo_servidor
        self._enviar("ver_servidor", {"activo": self.viendo_servidor})
        if self.viendo_servidor:
            self.boton_ver.config(text="Dejar de ver el servidor")
        else:
            self.boton_ver.config(text="Ver pantalla del servidor")
            self.pantalla.config(image=self.vacio)

    # ---------- llamadas ----------
    def llamar(self, con_video):
        if self.en_llamada or self.llamando:
            self._escribir("[sistema] ya hay una llamada en curso")
            return
        self.llamando = True
        self.video_pedido = con_video
        self._enviar("llamada_solicitud", {"video": con_video})
        self._escribir("[sistema] llamando al servidor...")

    def _empezar_llamada(self, con_video):
        self.llamando = False
        self.en_llamada = True
        self.llamada.iniciar(con_video, self.con.enviar)
        self.ventana_llamada = VentanaLlamada(self.raiz, "Llamada con el servidor", con_video, self.colgar)

    def colgar(self):
        self._enviar("llamada_fin")
        self._terminar_llamada()

    def _terminar_llamada(self):
        self.llamada.detener()
        self.en_llamada = False
        self.llamando = False
        if self.ventana_llamada:
            self.ventana_llamada.cerrar()
            self.ventana_llamada = None

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
        self.estado.config(text=f"● Conectado a {self.ip}", foreground=tema.COLORES["verde"])
        threading.Thread(target=self._hilo_red, daemon=True).start()
        threading.Thread(target=self._hilo_pantalla, daemon=True).start()
        self.raiz.after(100, self._procesar_cola)
        try:
            self.raiz.mainloop()
        finally:
            self.desbloquear()

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
                    self._escribir_chat(f"Servidor: {dato}")
                    self._aviso_chat()
                elif evento == "log":
                    self._escribir(f"[sistema] {dato}")
                elif evento == "imagen":
                    imagen = Image.open(io.BytesIO(dato))
                    imagen.thumbnail((640, 360))
                    self.foto = ImageTk.PhotoImage(imagen)
                    if self.viendo_servidor:
                        self.pantalla.config(image=self.foto)
                elif evento == "video":
                    if self.ventana_llamada:
                        self.ventana_llamada.mostrar(dato)
                elif evento == "llamada":
                    self._llamada_recibida(*dato)
                elif evento == "desconectado":
                    self.desbloquear()
                    self._terminar_llamada()
                    self.estado.config(text="● Desconectado", foreground=tema.COLORES["rojo"])
                    self._escribir("[sistema] se perdió la conexión con el servidor")
        except queue.Empty:
            pass
        self.raiz.after(100, self._procesar_cola)

    def _llamada_recibida(self, tipo, datos):
        if tipo == "llamada_solicitud":
            if self.en_llamada or self.llamando:
                self._enviar("llamada_respuesta", {"aceptar": False})
                return
            clase = "videollamada" if datos.get("video") else "llamada"
            if messagebox.askyesno("Llamada entrante", f"El servidor te está haciendo una {clase}. ¿Contestar?"):
                self._enviar("llamada_respuesta", {"aceptar": True})
                self._empezar_llamada(bool(datos.get("video")))
            else:
                self._enviar("llamada_respuesta", {"aceptar": False})
        elif tipo == "llamada_respuesta" and self.llamando:
            if datos.get("aceptar"):
                self._empezar_llamada(self.video_pedido)
            else:
                self.llamando = False
                self._escribir("[sistema] el servidor no contestó la llamada")
        elif tipo == "llamada_fin" and (self.en_llamada or self.llamando):
            self._terminar_llamada()
            self._escribir("[sistema] la llamada terminó")

    # ---------- 3.6 / 3.7: bloquear y desbloquear teclado y mouse ----------
    def bloquear(self):
        if self.bloqueador and self.bloqueador.poll() is None:
            return "Ya estaba bloqueado"
        self.bloqueador = subprocess.Popen(
            ["sudo", "-n", sys.executable, str(AYUDANTE), "bloquear-entrada", str(SEGUNDOS_BLOQUEO_MAX)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        linea = self.bloqueador.stdout.readline().strip()
        if not linea.startswith("listo"):
            error = linea or self.bloqueador.stderr.read().strip() or "no se pudo bloquear"
            self.bloqueador = None
            raise RuntimeError(error)
        return f"Bloqueado (se desbloquea solo en {SEGUNDOS_BLOQUEO_MAX} s)"

    def desbloquear(self):
        if self.bloqueador and self.bloqueador.poll() is None:
            try:
                self.bloqueador.stdin.close()  # el ayudante lo nota y suelta los dispositivos
            except OSError:
                pass
            try:
                self.bloqueador.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.bloqueador.kill()
        self.bloqueador = None
        return "Desbloqueado"

    # ---------- órdenes del servidor (corren en el hilo de red) ----------
    def ejecutar(self, tipo, datos, binario):
        if tipo == "chat":
            self.cola.put(("chat", datos.get("texto", "")))
            return
        if tipo == "audio":
            self.llamada.recibir_audio(binario)
            return
        if tipo == "video":
            self.cola.put(("video", binario))
            return
        if tipo in ("llamada_solicitud", "llamada_respuesta", "llamada_fin"):
            self.cola.put(("llamada", (tipo, datos)))
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
                mensaje = f"Archivo recibido: {destino}"
            elif tipo == "bloquear":
                mensaje = self.bloquear()
            elif tipo == "desbloquear":
                mensaje = self.desbloquear()
            elif tipo == "bloquear_webs":
                como_admin("bloquear-webs", ",".join(datos.get("sitios", [])))
                mensaje = "Páginas bloqueadas"
            elif tipo == "permitir_webs":
                como_admin("permitir-webs")
                mensaje = "Páginas permitidas"
            elif tipo == "ping":
                como_admin("ping", "permitir" if datos.get("permitir") else "negar")
                mensaje = "Ping permitido" if datos.get("permitir") else "Ping negado"
            elif tipo == "apagar":
                self.con.enviar("estado", {"ok": True, "mensaje": "Apagando..."})
                try:
                    correr(["systemctl", "poweroff"])
                except RuntimeError:
                    correr(["sudo", "-n", "systemctl", "poweroff"])
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
        self._terminar_llamada()
        if self.con:
            self.con.cerrar()
        self.raiz.destroy()


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else None
    nombre = sys.argv[2] if len(sys.argv) > 2 else socket.gethostname()

    print("Se necesita tu contraseña de administrador (bloqueo de teclado, ping y páginas web).")
    if subprocess.run(["sudo", "-v"]).returncode == 0:
        threading.Thread(target=mantener_sudo, daemon=True).start()
    else:
        print("Sin sudo: las órdenes de administrador no van a funcionar.")

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
