"""Servidor: el PC que controla a los demás.

Uso:  .venv/bin/python servidor/servidor.py
"""
import hmac
import io
import queue
import re
import socket
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun.archivos import abrir_carpeta, demasiado_grande, elegir_archivo  # noqa: E402
from comun.llamada import Llamada, VentanaLlamada  # noqa: E402
from comun.pantalla import capturar_jpeg  # noqa: E402
from comun.protocolo import Conexion, PUERTO, TOKEN  # noqa: E402

CARPETA_RECIBIDOS = Path(__file__).resolve().parent.parent / "recibidos_servidor"


class Servidor:
    def __init__(self):
        self.clientes = {}          # nombre -> Conexion
        self.candado = threading.Lock()
        self.cola = queue.Queue()   # los hilos de red dejan aquí lo que pasa
        self.viendo = None          # nombre de la PC que estamos viendo
        self.foto = None
        self.transmitiendo = set()  # PCs que están viendo la pantalla del servidor (3.5)

        # llamadas (una a la vez)
        self.llamada = Llamada(lambda t: self.cola.put(("aviso", "", t)))
        self.par_llamada = None     # PC con la que estamos en llamada
        self.llamando_a = None      # PC a la que estamos llamando (esperando respuesta)
        self.video_pedido = False
        self.ventana_llamada = None

        self._armar_ventana()
        threading.Thread(target=self._aceptar, daemon=True).start()
        threading.Thread(target=self._transmitir_pantalla, daemon=True).start()
        self.raiz.after(100, self._procesar_cola)

    # ---------- ventana ----------
    def _armar_ventana(self):
        self.raiz = tk.Tk()
        self.raiz.title(f"Servidor - puerto {PUERTO}")

        izq = tk.Frame(self.raiz)
        izq.pack(side="left", fill="y", padx=6, pady=6)
        tk.Label(izq, text="PCs conectadas").pack()
        self.lista = tk.Listbox(izq, width=22, exportselection=False)
        self.lista.pack(fill="y", expand=True)

        der = tk.Frame(self.raiz)
        der.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        self.vacio = tk.PhotoImage(width=800, height=450)
        self.vacio.put("black", to=(0, 0, 800, 450))
        self.pantalla = tk.Label(der, image=self.vacio)
        self.pantalla.pack()

        botones = tk.Frame(der)
        botones.pack(fill="x", pady=4)
        self.boton_pantalla = tk.Button(botones, text="Ver pantalla", command=self.alternar_pantalla)
        acciones = [
            self.boton_pantalla,
            tk.Button(botones, text="Bloquear teclado/mouse", command=lambda: self._orden("bloquear")),
            tk.Button(botones, text="Desbloquear", command=lambda: self._orden("desbloquear")),
            tk.Button(botones, text="Apagar PC", command=self.apagar),
            tk.Button(botones, text="Bloquear páginas web", command=self.bloquear_webs),
            tk.Button(botones, text="Permitir páginas web", command=lambda: self._orden("permitir_webs")),
            tk.Button(botones, text="Negar ping", command=lambda: self._orden("ping", {"permitir": False})),
            tk.Button(botones, text="Permitir ping", command=lambda: self._orden("ping", {"permitir": True})),
            tk.Button(botones, text="Llamar", command=lambda: self.llamar(False)),
            tk.Button(botones, text="Videollamada", command=lambda: self.llamar(True)),
            tk.Button(botones, text="Enviar archivo", command=self.enviar_archivo),
            tk.Button(botones, text="Abrir recibidos", command=lambda: abrir_carpeta(CARPETA_RECIBIDOS)),
        ]
        for i, boton in enumerate(acciones):
            boton.grid(row=i // 4, column=i % 4, sticky="ew", padx=2, pady=2)

        self.chat = tk.Text(der, height=8, state="disabled")
        self.chat.pack(fill="both", expand=True)
        escribir = tk.Frame(der)
        escribir.pack(fill="x")
        self.entrada = tk.Entry(escribir)
        self.entrada.pack(side="left", fill="x", expand=True)
        self.entrada.bind("<Return>", lambda e: self.enviar_chat())
        tk.Button(escribir, text="Enviar", command=self.enviar_chat).pack(side="left")

    def _escribir(self, texto):
        self.chat.config(state="normal")
        self.chat.insert("end", texto + "\n")
        self.chat.see("end")
        self.chat.config(state="disabled")

    # ---------- acciones de los botones ----------
    def _seleccionada(self):
        seleccion = self.lista.curselection()
        if not seleccion:
            messagebox.showinfo("Aviso", "Primero elige una PC de la lista.")
            return None
        return self.lista.get(seleccion[0])

    def _orden(self, tipo, datos=None, binario=b"", nombre=None):
        nombre = nombre or self._seleccionada()
        if not nombre:
            return False
        con = self.clientes.get(nombre)
        if not con:
            self._escribir(f"[sistema] {nombre} ya no está conectada")
            return False
        try:
            con.enviar(tipo, datos, binario)
            return True
        except OSError as e:
            self._escribir(f"[sistema] error enviando a {nombre}: {e}")
            return False

    def alternar_pantalla(self):
        if self.viendo:
            self._orden("ver_pantalla", {"activo": False}, nombre=self.viendo)
            self._dejar_de_ver()
            return
        nombre = self._seleccionada()
        if nombre:
            self._orden("ver_pantalla", {"activo": True}, nombre=nombre)
            self.viendo = nombre
            self.boton_pantalla.config(text="Dejar de ver")

    def _dejar_de_ver(self):
        self.viendo = None
        self.boton_pantalla.config(text="Ver pantalla")
        self.pantalla.config(image=self.vacio)

    def apagar(self):
        nombre = self._seleccionada()
        if nombre and messagebox.askyesno("Confirmar", f"¿Apagar {nombre}?"):
            self._orden("apagar", nombre=nombre)

    def bloquear_webs(self):
        texto = simpledialog.askstring("Bloquear páginas", "Sitios separados por coma (ej: facebook.com, youtube.com):")
        if texto:
            sitios = [s for s in texto.split(",") if s.strip()]
            self._orden("bloquear_webs", {"sitios": sitios})

    def enviar_chat(self):
        texto = self.entrada.get().strip()
        nombre = self._seleccionada() if texto else None
        if nombre and self._orden("chat", {"texto": texto}, nombre=nombre):
            self._escribir(f"Tú -> {nombre}: {texto}")
            self.entrada.delete(0, "end")

    # ---------- archivos ----------
    def enviar_archivo(self):
        nombre = self._seleccionada()
        if not nombre:
            return
        ruta = elegir_archivo(f"Elegir archivo para enviar a {nombre}")
        if not ruta:
            return
        ruta = Path(ruta)
        if demasiado_grande(ruta):
            self._escribir("[sistema] el archivo es demasiado grande (máximo 150 MB)")
            return
        threading.Thread(target=self._enviar_archivo_hilo, args=(nombre, ruta), daemon=True).start()

    def _enviar_archivo_hilo(self, nombre, ruta):
        self.cola.put(("aviso", "", f"Enviando '{ruta.name}' a {nombre}..."))
        con = self.clientes.get(nombre)
        try:
            con.enviar("archivo", {"nombre": ruta.name}, ruta.read_bytes())
            self.cola.put(("aviso", "", f"Archivo '{ruta.name}' enviado a {nombre}"))
        except Exception as e:
            self.cola.put(("aviso", "", f"No se pudo enviar '{ruta.name}': {e}"))

    # ---------- llamadas ----------
    def llamar(self, con_video):
        if self.par_llamada or self.llamando_a:
            self._escribir("[sistema] ya hay una llamada en curso")
            return
        nombre = self._seleccionada()
        if nombre and self._orden("llamada_solicitud", {"video": con_video}, nombre=nombre):
            self.llamando_a = nombre
            self.video_pedido = con_video
            self._escribir(f"[sistema] llamando a {nombre}...")

    def _empezar_llamada(self, nombre, con_video):
        con = self.clientes.get(nombre)
        if not con:
            return
        self.llamando_a = None
        self.par_llamada = nombre
        self.llamada.iniciar(con_video, con.enviar)
        self.ventana_llamada = VentanaLlamada(self.raiz, f"Llamada con {nombre}", con_video, self.colgar)

    def colgar(self):
        if self.par_llamada:
            self._orden("llamada_fin", nombre=self.par_llamada)
        self._terminar_llamada()

    def _terminar_llamada(self):
        self.llamada.detener()
        self.par_llamada = None
        self.llamando_a = None
        if self.ventana_llamada:
            self.ventana_llamada.cerrar()
            self.ventana_llamada = None

    def _llamada_recibida(self, nombre, tipo, datos):
        if tipo == "llamada_solicitud":
            if self.par_llamada or self.llamando_a:
                self._orden("llamada_respuesta", {"aceptar": False}, nombre=nombre)
                return
            clase = "videollamada" if datos.get("video") else "llamada"
            if messagebox.askyesno("Llamada entrante", f"{nombre} te está haciendo una {clase}. ¿Contestar?"):
                self._orden("llamada_respuesta", {"aceptar": True}, nombre=nombre)
                self._empezar_llamada(nombre, bool(datos.get("video")))
            else:
                self._orden("llamada_respuesta", {"aceptar": False}, nombre=nombre)
        elif tipo == "llamada_respuesta" and nombre == self.llamando_a:
            if datos.get("aceptar"):
                self._empezar_llamada(nombre, self.video_pedido)
            else:
                self.llamando_a = None
                self._escribir(f"[sistema] {nombre} no contestó la llamada")
        elif tipo == "llamada_fin" and nombre in (self.par_llamada, self.llamando_a):
            self._terminar_llamada()
            self._escribir(f"[sistema] {nombre} terminó la llamada")

    # ---------- red ----------
    def _aceptar(self):
        servidor = socket.socket()
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind(("0.0.0.0", PUERTO))
        servidor.listen()
        while True:
            sock, _ = servidor.accept()
            threading.Thread(target=self._atender, args=(Conexion(sock),), daemon=True).start()

    def _atender(self, con):
        con.sock.settimeout(10)  # si no se presenta rápido, se cierra
        saludo = con.recibir()
        if not saludo or saludo[0] != "hola" or not hmac.compare_digest(
            str(saludo[1].get("token", "")), TOKEN
        ):
            con.cerrar()
            return
        con.sock.settimeout(None)

        base = re.sub(r"[^\w.-]", "_", str(saludo[1].get("nombre", "pc")))[:30] or "pc"
        with self.candado:
            nombre, n = base, 1
            while nombre in self.clientes:
                n += 1
                nombre = f"{base}-{n}"
            self.clientes[nombre] = con
        self.cola.put(("conectado", nombre, None))

        while True:
            msg = con.recibir()
            if msg is None:
                break
            if msg[0] == "audio":  # el audio no pasa por la ventana: va directo, para no atrasarse
                if nombre == self.par_llamada:
                    self.llamada.recibir_audio(msg[2])
                continue
            self.cola.put(("mensaje", nombre, msg))

        with self.candado:
            self.clientes.pop(nombre, None)
            self.transmitiendo.discard(nombre)
        con.cerrar()
        self.cola.put(("desconectado", nombre, None))

    def _procesar_cola(self):
        try:
            while True:
                evento, nombre, dato = self.cola.get_nowait()
                if evento == "conectado":
                    self.lista.insert("end", nombre)
                    self._escribir(f"[sistema] {nombre} se conectó")
                elif evento == "desconectado":
                    nombres = self.lista.get(0, "end")
                    if nombre in nombres:
                        self.lista.delete(nombres.index(nombre))
                    if nombre == self.viendo:
                        self._dejar_de_ver()
                    if nombre in (self.par_llamada, self.llamando_a):
                        self._terminar_llamada()
                    self._escribir(f"[sistema] {nombre} se desconectó")
                elif evento == "aviso":
                    self._escribir(f"[sistema] {dato}")
                else:
                    self._mensaje(nombre, *dato)
        except queue.Empty:
            pass
        self.raiz.after(100, self._procesar_cola)

    def _mensaje(self, nombre, tipo, datos, binario):
        if tipo == "chat":
            self._escribir(f"{nombre}: {datos.get('texto', '')}")
        elif tipo == "estado":
            estado = "OK" if datos.get("ok") else "ERROR"
            self._escribir(f"[{nombre}] {estado}: {datos.get('mensaje', '')}")
        elif tipo == "imagen" and nombre == self.viendo:
            imagen = Image.open(io.BytesIO(binario))
            imagen.thumbnail((800, 450))
            self.foto = ImageTk.PhotoImage(imagen)
            self.pantalla.config(image=self.foto)
        elif tipo == "video":
            if nombre == self.par_llamada and self.ventana_llamada:
                self.ventana_llamada.mostrar(binario)
        elif tipo in ("llamada_solicitud", "llamada_respuesta", "llamada_fin"):
            self._llamada_recibida(nombre, tipo, datos)
        elif tipo == "ver_servidor":
            with self.candado:
                if datos.get("activo"):
                    self.transmitiendo.add(nombre)
                else:
                    self.transmitiendo.discard(nombre)
        elif tipo == "archivo":
            CARPETA_RECIBIDOS.mkdir(exist_ok=True)
            destino = CARPETA_RECIBIDOS / f"{nombre}_{Path(datos.get('nombre', 'archivo')).name}"
            destino.write_bytes(binario)
            self._escribir(f"[sistema] archivo recibido de {nombre}: {destino}")

    # 3.5: mostrar a los agentes lo que hace el servidor
    def _transmitir_pantalla(self):
        while True:
            time.sleep(0.5)
            with self.candado:
                destinos = [(n, self.clientes.get(n)) for n in self.transmitiendo]
            if not destinos:
                continue
            try:
                jpeg = capturar_jpeg()
            except Exception as e:
                for _, con in destinos:
                    try:
                        con.enviar("estado", {"ok": False, "mensaje": f"el servidor no pudo capturar su pantalla: {e}"})
                    except (OSError, AttributeError):
                        pass
                with self.candado:
                    self.transmitiendo.clear()
                continue
            for n, con in destinos:
                try:
                    con.enviar("imagen_servidor", binario=jpeg)
                except (OSError, AttributeError):
                    with self.candado:
                        self.transmitiendo.discard(n)

    def iniciar(self):
        self.raiz.mainloop()


if __name__ == "__main__":
    Servidor().iniciar()
