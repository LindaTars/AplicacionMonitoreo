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
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import tema  # noqa: E402
from comun.archivos import abrir_carpeta, demasiado_grande, elegir_archivo  # noqa: E402
from comun.llamada import Llamada, VentanaLlamada  # noqa: E402
from comun.pantalla import capturar_jpeg  # noqa: E402
from comun.protocolo import Conexion, PUERTO, TOKEN  # noqa: E402

CARPETA_RECIBIDOS = Path(__file__).resolve().parent.parent / "recibidos_servidor"
MAX_PANTALLAS = 3          # punto 3.4: ver hasta 3 PCs a la vez
ANCHO, ALTO = 270, 152     # tamaño de cada cuadro de pantalla


def _ip_local():
    """IP de esta PC en la red (la que hay que escribir en los agentes)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))  # no envía nada, solo elige la tarjeta de red
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class Servidor:
    def __init__(self):
        self.clientes = {}          # nombre -> Conexion
        self.candado = threading.Lock()
        self.cola = queue.Queue()   # los hilos de red dejan aquí lo que pasa
        self.viendo = {}            # nombre de la PC -> posición (0, 1 o 2) en la cuadrícula
        self.fotos = [None] * MAX_PANTALLAS
        self.transmitiendo = set()  # PCs que están viendo la pantalla del servidor (3.5)

        # llamadas (una a la vez)
        self.llamada = Llamada(lambda t: self.cola.put(("aviso", "", t)))
        self.par_llamada = None     # PC con la que estamos en llamada
        self.llamando_a = None      # PC a la que estamos llamando (esperando respuesta)
        self.video_pedido = False
        self.ventana_llamada = None

        self.ip_local = _ip_local()
        self._armar_ventana()
        threading.Thread(target=self._aceptar, daemon=True).start()
        threading.Thread(target=self._transmitir_pantalla, daemon=True).start()
        self.raiz.after(100, self._procesar_cola)

    # ---------- ventana ----------
    def _armar_ventana(self):
        self.raiz = tk.Tk()
        self.raiz.title("Monitoreo de red - Servidor")
        self.raiz.geometry("1280x780")
        self.raiz.minsize(1100, 680)
        tema.aplicar(self.raiz)

        cabecera = ttk.Frame(self.raiz, padding=(20, 14))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Panel del servidor", style="Titulo.TLabel").pack(side="left")
        self.estado = ttk.Label(cabecera, text="", style="Suave.TLabel")
        self.estado.pack(side="right")

        cuerpo = ttk.Frame(self.raiz, padding=(20, 0, 20, 16))
        cuerpo.pack(fill="both", expand=True)

        lateral = ttk.Frame(cuerpo, style="Tarjeta.TFrame", padding=14)
        lateral.pack(side="left", fill="y")
        ttk.Label(lateral, text="PCs conectadas", style="TarjetaSeccion.TLabel").pack(anchor="w")
        ttk.Label(lateral, text="Elige una para controlarla", style="Nota.TLabel").pack(anchor="w", pady=(2, 8))
        self.lista = tk.Listbox(lateral, width=20, exportselection=False)
        tema.estilo_lista(self.lista)
        self.lista.pack(fill="both", expand=True)

        self.apartados = ttk.Notebook(cuerpo)
        self.apartados.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self._armar_monitoreo()
        self._armar_control()
        self._armar_comunicacion()
        self._armar_registro()
        self.apartados.bind("<<NotebookTabChanged>>", self._pestana_cambio)
        self._actualizar_estado()

    def _armar_monitoreo(self):
        marco = ttk.Frame(self.apartados, padding=18)
        self.apartados.add(marco, text="Monitoreo")
        ttk.Label(marco, text="Pantallas de las PCs (hasta 3 a la vez)", style="Seccion.TLabel").pack(anchor="w", pady=(0, 10))

        self.vacio = tk.PhotoImage(width=ANCHO, height=ALTO)
        self.vacio.put("#000000", to=(0, 0, ANCHO, ALTO))
        fila = ttk.Frame(marco)
        fila.pack(anchor="w")
        self.titulos, self.pantallas = [], []
        for i in range(MAX_PANTALLAS):
            tarjeta = ttk.Frame(fila, style="Tarjeta.TFrame", padding=10)
            tarjeta.grid(row=0, column=i, padx=(0, 12))
            titulo = ttk.Label(tarjeta, text="(libre)", style="TarjetaSeccion.TLabel")
            titulo.pack(anchor="w", pady=(0, 8))
            pantalla = tk.Label(tarjeta, image=self.vacio, bd=0, bg="#000000")
            pantalla.pack()
            self.titulos.append(titulo)
            self.pantallas.append(pantalla)

        botones = ttk.Frame(marco)
        botones.pack(anchor="w", pady=18)
        ttk.Button(botones, text="Ver / dejar de ver la PC elegida", style="Acento.TButton",
                   command=self.alternar_pantalla).pack(side="left", padx=(0, 10))
        self.boton_todas = ttk.Button(botones, text="Ver todas (hasta 3)", command=self.ver_todas)
        self.boton_todas.pack(side="left")

    def _armar_control(self):
        marco = ttk.Frame(self.apartados, padding=18)
        self.apartados.add(marco, text="Control")
        marco.columnconfigure(0, weight=1)
        marco.columnconfigure(1, weight=1)
        ttk.Label(marco, text="Estas acciones se aplican a la PC elegida en la lista",
                  style="Seccion.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        teclado = tema.tarjeta(marco, "Teclado y mouse")
        teclado.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        tema.botones(teclado, [
            ("Bloquear", "TButton", lambda: self._orden("bloquear")),
            ("Desbloquear", "Acento.TButton", lambda: self._orden("desbloquear")),
        ], "El bloqueo se quita solo a los 2 minutos.")

        energia = tema.tarjeta(marco, "Energía")
        energia.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)
        tema.botones(energia, [("Apagar PC", "Peligro.TButton", self.apagar)],
                     "Apaga la PC elegida (pide confirmación).")

        ping = tema.tarjeta(marco, "Ping")
        ping.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        tema.botones(ping, [
            ("Negar ping", "TButton", lambda: self._orden("ping", {"permitir": False})),
            ("Permitir ping", "Acento.TButton", lambda: self._orden("ping", {"permitir": True})),
        ], "Una PC con el ping negado no contesta cuando otra le hace ping.")

        webs = tema.tarjeta(marco, "Páginas web")
        webs.grid(row=2, column=1, sticky="nsew", padx=8, pady=8)
        tema.botones(webs, [
            ("Bloquear páginas...", "TButton", self.bloquear_webs),
            ("Permitir páginas", "Acento.TButton", lambda: self._orden("permitir_webs")),
        ], "Si el navegador las sigue abriendo, desactiva el DNS seguro.")

    def _armar_comunicacion(self):
        self.marco_comunicacion = ttk.Frame(self.apartados, padding=18)
        marco = self.marco_comunicacion
        self.apartados.add(marco, text="Comunicación")
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)

        chat = tema.tarjeta(marco, "Chat con la PC elegida")
        chat.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        zona, self.chat = tema.texto_con_barra(chat)
        zona.pack(fill="both", expand=True)
        escribir = ttk.Frame(chat, style="Tarjeta.TFrame")
        escribir.pack(fill="x", pady=(10, 0))
        self.entrada = ttk.Entry(escribir)
        self.entrada.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entrada.bind("<Return>", lambda e: self.enviar_chat())
        ttk.Button(escribir, text="Enviar", style="Acento.TButton", command=self.enviar_chat).pack(side="left")

        lado = ttk.Frame(marco)
        lado.grid(row=0, column=1, sticky="n")
        archivos = tema.tarjeta(lado, "Archivos")
        archivos.pack(fill="x", padx=8, pady=8)
        tema.botones(archivos, [
            ("Enviar archivo", "Acento.TButton", self.enviar_archivo),
            ("Abrir recibidos", "TButton", lambda: abrir_carpeta(CARPETA_RECIBIDOS)),
        ], "Los archivos recibidos se guardan en la carpeta recibidos_servidor.")
        llamadas = tema.tarjeta(lado, "Llamadas")
        llamadas.pack(fill="x", padx=8, pady=8)
        tema.botones(llamadas, [
            ("Llamar", "TButton", lambda: self.llamar(False)),
            ("Videollamada", "Acento.TButton", lambda: self.llamar(True)),
        ], "Usen audífonos para evitar el eco.")

    def _armar_registro(self):
        marco = ttk.Frame(self.apartados, padding=18)
        self.apartados.add(marco, text="Registro")
        zona, self.registro = tema.texto_con_barra(marco, alto=20)
        zona.pack(fill="both", expand=True)

    def _actualizar_estado(self):
        n = len(self.clientes)
        texto = f"● {n} PC{'s' if n != 1 else ''} conectada{'s' if n != 1 else ''}   |   {self.ip_local}:{PUERTO}"
        self.estado.configure(text=texto, foreground=tema.COLORES["verde"] if n else tema.COLORES["amarillo"])

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

    def _posicion_libre(self):
        usadas = set(self.viendo.values())
        for i in range(MAX_PANTALLAS):
            if i not in usadas:
                return i
        return None

    def _empezar_a_ver(self, nombre):
        if nombre in self.viendo:
            return
        posicion = self._posicion_libre()
        if posicion is None:
            self._escribir(f"[sistema] solo se pueden ver {MAX_PANTALLAS} pantallas a la vez")
            return
        if self._orden("ver_pantalla", {"activo": True}, nombre=nombre):
            self.viendo[nombre] = posicion
            self.titulos[posicion].config(text=nombre)

    def _dejar_de_ver(self, nombre, avisar=True):
        posicion = self.viendo.pop(nombre, None)
        if posicion is None:
            return
        if avisar:
            self._orden("ver_pantalla", {"activo": False}, nombre=nombre)
        self.titulos[posicion].config(text="(libre)")
        self.pantallas[posicion].config(image=self.vacio)

    def alternar_pantalla(self):
        """Ver (o dejar de ver) la PC elegida en la lista."""
        nombre = self._seleccionada()
        if not nombre:
            return
        if nombre in self.viendo:
            self._dejar_de_ver(nombre)
        else:
            self._empezar_a_ver(nombre)

    def ver_todas(self):
        """Ver las primeras 3 PCs conectadas a la vez (punto 3.4)."""
        if self.viendo:
            for nombre in list(self.viendo):
                self._dejar_de_ver(nombre)
            self.boton_todas.config(text="Ver todas (hasta 3)")
            return
        for nombre in list(self.clientes)[:MAX_PANTALLAS]:
            self._empezar_a_ver(nombre)
        if self.viendo:
            self.boton_todas.config(text="Dejar de ver todas")

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
            self._escribir_chat(f"Tú -> {nombre}: {texto}", propio=True)
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
                    self._actualizar_estado()
                elif evento == "desconectado":
                    nombres = self.lista.get(0, "end")
                    if nombre in nombres:
                        self.lista.delete(nombres.index(nombre))
                    self._dejar_de_ver(nombre, avisar=False)
                    if nombre in (self.par_llamada, self.llamando_a):
                        self._terminar_llamada()
                    self._escribir(f"[sistema] {nombre} se desconectó")
                    self._actualizar_estado()
                elif evento == "aviso":
                    self._escribir(f"[sistema] {dato}")
                else:
                    self._mensaje(nombre, *dato)
        except queue.Empty:
            pass
        self.raiz.after(100, self._procesar_cola)

    def _mensaje(self, nombre, tipo, datos, binario):
        if tipo == "chat":
            self._escribir_chat(f"{nombre}: {datos.get('texto', '')}")
            self._aviso_chat()
        elif tipo == "estado":
            estado = "OK" if datos.get("ok") else "ERROR"
            self._escribir(f"[{nombre}] {estado}: {datos.get('mensaje', '')}")
        elif tipo == "imagen" and nombre in self.viendo:
            posicion = self.viendo[nombre]
            imagen = Image.open(io.BytesIO(binario))
            imagen.thumbnail((ANCHO, ALTO))
            self.fotos[posicion] = ImageTk.PhotoImage(imagen)
            self.pantallas[posicion].config(image=self.fotos[posicion])
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
