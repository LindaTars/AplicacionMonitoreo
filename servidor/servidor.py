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
from comun import tema  # noqa: E402
from comun.archivos import abrir_carpeta, demasiado_grande, elegir_archivo  # noqa: E402
from comun.llamada import Llamada, VentanaLlamada  # noqa: E402
from comun.pantalla import capturar_jpeg  # noqa: E402
from comun.protocolo import Conexion, PUERTO, TOKEN  # noqa: E402

CARPETA_RECIBIDOS = Path(__file__).resolve().parent.parent / "recibidos_servidor"
MAX_PANTALLAS = 3          # punto 3.4: ver hasta 3 PCs a la vez
ANCHO, ALTO = 164, 92      # tamaño de cada cuadro de pantalla
MAX_HISTORIAL = 500        # líneas que se recuerdan del chat y del registro (para el cambio de tema)

SECCIONES = [
    ("monitoreo", "▣", "Monitoreo"),
    ("control", "⚙", "Control"),
    ("comunicacion", "✉", "Comunicación"),
    ("registro", "☰", "Registro"),
]
TITULOS = {
    "monitoreo": "Monitoreo",
    "control": "Control",
    "comunicacion": "Comunicación",
    "registro": "Registro",
}


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
        self.exhibiciones = {}      # PC origen -> PCs donde se muestra su pantalla ("exhibir un cliente")

        # llamadas (una a la vez)
        self.llamada = Llamada(lambda t: self.cola.put(("aviso", "", t)))
        self.par_llamada = None     # PC con la que estamos en llamada
        self.llamando_a = None      # PC a la que estamos llamando (esperando respuesta)
        self.video_pedido = False
        self.ventana_llamada = None

        # lo que se recuerda para poder reconstruir la ventana al cambiar de tema
        self.hist_chat = []
        self.hist_registro = []
        self.seccion = "monitoreo"

        self.ip_local = _ip_local()
        self._armar_ventana()
        threading.Thread(target=self._aceptar, daemon=True).start()
        threading.Thread(target=self._transmitir_pantalla, daemon=True).start()
        self.raiz.after(100, self._procesar_cola)

    # ---------- ventana ----------
    def _armar_ventana(self):
        self.raiz = tk.Tk()
        self.raiz.title("Monitoreo de red - Servidor")
        self.raiz.geometry("1360x800")
        self.raiz.minsize(1240, 720)
        tema.aplicar(self.raiz)
        self._construir()

    def _construir(self):
        """Arma toda la interfaz con la paleta activa. Se vuelve a llamar al cambiar de tema."""
        c = tema.COLORES
        self.raiz.configure(bg=c["fondo"])
        self.base = tk.Frame(self.raiz, bg=c["fondo"])
        self.base.pack(fill="both", expand=True)
        self.base.columnconfigure(1, weight=1)
        self.base.rowconfigure(0, weight=1)

        # barra lateral
        self.lateral = tema.Lateral(
            self.base, SECCIONES, self._ir_a, titulo="Monitoreo",
            info=["Servidor", f"IP  {self.ip_local}", f"Puerto  {PUERTO}"], ancho=224,
        )
        self.lateral.grid(row=0, column=0, sticky="ns")

        # centro
        centro = tk.Frame(self.base, bg=c["fondo"])
        centro.grid(row=0, column=1, sticky="nsew", padx=24, pady=18)
        centro.columnconfigure(0, weight=1)
        centro.rowconfigure(3, weight=1)
        self._armar_cabecera(centro)
        self._armar_bienvenida(centro)
        self._armar_estadisticas(centro)

        zona = tk.Frame(centro, bg=c["fondo"])
        zona.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        zona.columnconfigure(0, weight=1)
        zona.rowconfigure(0, weight=1)
        self.marcos = {}
        for clave, armar in (
            ("monitoreo", self._armar_monitoreo),
            ("control", self._armar_control),
            ("comunicacion", self._armar_comunicacion),
            ("registro", self._armar_registro),
        ):
            marco = tk.Frame(zona, bg=c["fondo"])
            marco.grid(row=0, column=0, sticky="nsew")
            armar(marco)
            self.marcos[clave] = marco

        # panel derecho
        derecho = tk.Frame(self.base, bg=c["fondo"], width=292)
        derecho.grid(row=0, column=2, sticky="ns", padx=(0, 24), pady=18)
        derecho.pack_propagate(False)
        self._armar_derecha(derecho)

        # volver a poner lo que ya había (importa al cambiar de tema)
        for texto, etiqueta in self.hist_chat:
            tema.agregar_linea(self.chat, texto, etiqueta)
        for texto, etiqueta in self.hist_registro:
            tema.agregar_linea(self.registro, texto, etiqueta)
        self._ir_a(self.seccion)
        self._actualizar_estado()

    def _armar_cabecera(self, centro):
        c = tema.COLORES
        fila = tk.Frame(centro, bg=c["fondo"])
        fila.grid(row=0, column=0, sticky="ew")
        izquierda = tk.Frame(fila, bg=c["fondo"])
        izquierda.pack(side="left")
        self.lbl_titulo = tk.Label(izquierda, text="", font=tema.fuente(20, "bold"), bg=c["fondo"], fg=c["texto"])
        self.lbl_titulo.pack(anchor="w")
        tk.Label(izquierda, text="Panel del servidor", font=tema.fuente(10), bg=c["fondo"], fg=c["suave"]).pack(anchor="w")

        derecha = tk.Frame(fila, bg=c["fondo"])
        derecha.pack(side="right")
        etiqueta = "☾  Oscuro" if tema.tema_actual() == "claro" else "☀  Claro"
        tema.Pildora(derecha, etiqueta, self._cambiar_tema, "suave", alto=38).pack(side="right", padx=(12, 0))
        chip = tema.Carta(derecha, radio=19, margen=(16, 9))
        chip.pack(side="right")
        self.estado = tk.Label(chip.interior, text="", bg=c["panel"], fg=c["suave"], font=tema.fuente(10, "bold"))
        self.estado.pack()

    def _armar_bienvenida(self, centro):
        c = tema.COLORES
        hero = tema.Carta(centro, radio=24, margen=(26, 18), expandir=False, decoracion=tema.decorar_monitor)
        hero.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        i = hero.interior
        tk.Label(i, text="Panel de monitoreo", font=tema.fuente(10), bg=c["panel"], fg=c["suave"]).pack(anchor="w")
        tk.Label(i, text="Controla y observa las PCs de tu red", font=tema.fuente(17, "bold"),
                 bg=c["panel"], fg=c["texto"]).pack(anchor="w", pady=(2, 4))
        tk.Label(i, text=f"En cada agente escribe la IP  {self.ip_local}", font=tema.fuente(10),
                 bg=c["panel"], fg=c["suave"]).pack(anchor="w")

    def _armar_estadisticas(self, centro):
        c = tema.COLORES
        fila = tk.Frame(centro, bg=c["fondo"])
        fila.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        for col in range(3):
            fila.columnconfigure(col, weight=1, uniform="estadistica")

        def estadistica(col, titulo):
            carta = tema.Carta(fila, radio=20, margen=(18, 13))
            carta.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 7, 0 if col == 2 else 7))
            numero = tk.Label(carta.interior, text="0", font=tema.fuente(22, "bold"), bg=c["panel"], fg=c["acento"])
            numero.pack(side="left")
            tk.Label(carta.interior, text=titulo, font=tema.fuente(10), bg=c["panel"], fg=c["suave"],
                     justify="left").pack(side="left", padx=(12, 0))
            return numero

        self.num_pcs = estadistica(0, "PCs\nconectadas")
        self.num_pantallas = estadistica(1, "Pantallas\nen vivo")
        self.num_transmitiendo = estadistica(2, "Ven tu\npantalla")

    def _armar_derecha(self, derecho):
        c = tema.COLORES
        perfil = tema.Carta(derecho, radio=24, margen=(20, 18))
        perfil.pack(fill="x")
        tk.Label(perfil.interior, text="PC seleccionada", font=tema.fuente(11, "bold"),
                 bg=c["panel"], fg=c["texto"]).pack(anchor="w")
        self.zona_perfil = tk.Frame(perfil.interior, bg=c["panel"])
        self.zona_perfil.pack(fill="x", pady=(12, 0))

        listado = tema.Carta(derecho, radio=24, margen=(16, 18))
        listado.pack(fill="both", expand=True, pady=(14, 0))
        tk.Label(listado.interior, text="PCs conectadas", font=tema.fuente(11, "bold"),
                 bg=c["panel"], fg=c["texto"]).pack(anchor="w", padx=4)
        tk.Label(listado.interior, text="Elige una para controlarla", font=tema.fuente(9),
                 bg=c["panel"], fg=c["suave"]).pack(anchor="w", padx=4, pady=(1, 10))
        self.lista = tema.ListaPCs(listado.interior, al_elegir=self._al_elegir)
        self.lista.pack(fill="both", expand=True)

    def _carta_accion(self, padre, titulo, botones, nota, ancho_nota=270):
        """Tarjeta con un título, una fila de botones y una nota."""
        c = tema.COLORES
        carta = tema.Carta(padre, radio=22, margen=(20, 18))
        i = carta.interior
        tk.Label(i, text=titulo, font=tema.fuente(11, "bold"), bg=c["panel"], fg=c["texto"]).pack(anchor="w")
        fila = tk.Frame(i, bg=c["panel"])
        fila.pack(anchor="w", pady=(12, 0))
        for texto, variante, comando in botones:
            tema.Pildora(fila, texto, comando, variante).pack(side="left", padx=(0, 8))
        if nota:
            tk.Label(i, text=nota, font=tema.fuente(9), bg=c["panel"], fg=c["suave"],
                     wraplength=ancho_nota, justify="left").pack(anchor="w", pady=(12, 0))
        return carta

    def _armar_monitoreo(self, marco):
        c = tema.COLORES
        carta = tema.Carta(marco, radio=24, margen=(22, 18))
        carta.pack(fill="x", anchor="n")
        i = carta.interior
        tk.Label(i, text="Pantallas de las PCs", font=tema.fuente(12, "bold"), bg=c["panel"], fg=c["texto"]).pack(anchor="w")
        tk.Label(i, text="Puedes ver hasta 3 a la vez", font=tema.fuente(9), bg=c["panel"], fg=c["suave"]).pack(anchor="w", pady=(1, 12))

        self.vacio = tk.PhotoImage(width=ANCHO, height=ALTO)
        self.vacio.put("#000000", to=(0, 0, ANCHO, ALTO))
        fila = tk.Frame(i, bg=c["panel"])
        fila.pack(fill="x")
        self.titulos, self.pantallas = [], []
        for n in range(MAX_PANTALLAS):
            fila.columnconfigure(n, weight=1, uniform="pantalla")
            cuadro = tema.Carta(fila, relleno=c["panel2"], borde=c["panel2"], radio=16, margen=(10, 10))
            cuadro.grid(row=0, column=n, sticky="ew", padx=(0 if n == 0 else 6, 0 if n == MAX_PANTALLAS - 1 else 6))
            titulo = tk.Label(cuadro.interior, text="(libre)", font=tema.fuente(10, "bold"),
                              bg=c["panel2"], fg=c["texto"], anchor="w")
            titulo.pack(fill="x", pady=(0, 7))
            pantalla = tk.Label(cuadro.interior, image=self.vacio, bd=0, bg="#000000")
            pantalla.pack()
            self.titulos.append(titulo)
            self.pantallas.append(pantalla)

        botones = tk.Frame(i, bg=c["panel"])
        botones.pack(anchor="w", pady=(16, 0))
        tema.Pildora(botones, "Ver / dejar de ver la PC elegida", self.alternar_pantalla, "acento").pack(side="left", padx=(0, 10))
        self.boton_todas = tema.Pildora(
            botones, "Dejar de ver todas" if self.viendo else "Ver todas (hasta 3)", self.ver_todas, "suave")
        self.boton_todas.pack(side="left")

        exhibir = tk.Frame(i, bg=c["panel"])
        exhibir.pack(anchor="w", pady=(10, 0))
        self.boton_exhibir = tema.Pildora(exhibir, "Exhibir PC elegida en...", self.elegir_destino, "acento")
        self.boton_exhibir.pack(side="left", padx=(0, 10))
        tema.Pildora(exhibir, "Dejar de exhibir", self.dejar_de_exhibir, "suave").pack(side="left")
        self.lbl_exhibicion = tk.Label(i, text="", font=tema.fuente(9), bg=c["panel"], fg=c["suave"])
        self.lbl_exhibicion.pack(anchor="w", pady=(8, 0))

        # si se cambió de tema con pantallas abiertas, se vuelven a poner
        for nombre, posicion in self.viendo.items():
            self.titulos[posicion].config(text=nombre)
            if self.fotos[posicion] is not None:
                self.pantallas[posicion].config(image=self.fotos[posicion])

    def _armar_control(self, marco):
        c = tema.COLORES
        marco.columnconfigure(0, weight=1, uniform="control")
        marco.columnconfigure(1, weight=1, uniform="control")
        self.lbl_objetivo = tk.Label(marco, text="", font=tema.fuente(11, "bold"), bg=c["fondo"], fg=c["texto"])
        self.lbl_objetivo.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        tarjetas = [
            ("Teclado y mouse", [
                ("Bloquear", "suave", lambda: self._orden("bloquear")),
                ("Desbloquear", "acento", lambda: self._orden("desbloquear")),
            ], "El bloqueo se quita solo a los 2 minutos."),
            ("Energía", [("Apagar PC", "peligro", self.apagar)],
             "Apaga la PC elegida (pide confirmación)."),
            ("Ping", [
                ("Negar ping", "suave", lambda: self._orden("ping", {"permitir": False})),
                ("Permitir ping", "acento", lambda: self._orden("ping", {"permitir": True})),
            ], "Una PC con el ping negado no puede hacer ping hacia otras."),
            ("Páginas web", [
                ("Bloquear...", "suave", self.bloquear_webs),
                ("Permitir todas", "acento", lambda: self._orden("permitir_webs")),
            ], "Si el navegador las sigue abriendo, desactiva el DNS seguro."),
        ]
        for n, (titulo, botones, nota) in enumerate(tarjetas):
            carta = self._carta_accion(marco, titulo, botones, nota)
            carta.grid(row=1 + n // 2, column=n % 2, sticky="nsew",
                       padx=(0 if n % 2 == 0 else 7, 7 if n % 2 == 0 else 0), pady=(0, 14))

    def _armar_comunicacion(self, marco):
        c = tema.COLORES
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)

        chat = tema.Carta(marco, radio=24, margen=(20, 18))
        chat.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        tk.Label(chat.interior, text="Chat con la PC elegida", font=tema.fuente(11, "bold"),
                 bg=c["panel"], fg=c["texto"]).pack(anchor="w", pady=(0, 10))
        zona, self.chat = tema.texto_con_barra(chat.interior)
        zona.pack(fill="both", expand=True)
        escribir = tk.Frame(chat.interior, bg=c["panel"])
        escribir.pack(fill="x", pady=(12, 0))
        caja = tema.Carta(escribir, relleno=c["panel2"], radio=19, margen=(14, 4))
        caja.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entrada = tk.Entry(
            caja.interior, bg=c["panel2"], fg=c["texto"], insertbackground=c["texto"],
            relief="flat", bd=0, highlightthickness=0, font=tema.fuente(10),
        )
        self.entrada.pack(fill="x", ipady=7)
        self.entrada.bind("<Return>", lambda e: self.enviar_chat())
        tema.Pildora(escribir, "Enviar", self.enviar_chat, "acento").pack(side="left")

        lado = tk.Frame(marco, bg=c["fondo"])
        lado.grid(row=0, column=1, sticky="n", padx=(7, 0))
        archivos = self._carta_accion(lado, "Archivos", [
            ("Enviar", "acento", self.enviar_archivo),
            ("Recibidos", "suave", lambda: abrir_carpeta(CARPETA_RECIBIDOS)),
        ], "Los archivos recibidos se guardan en la carpeta recibidos_servidor.", ancho_nota=210)
        archivos.pack(fill="x", pady=(0, 14))
        llamadas = self._carta_accion(lado, "Llamadas", [
            ("Llamar", "suave", lambda: self.llamar(False)),
            ("Videollamada", "acento", lambda: self.llamar(True)),
        ], "Usen audífonos para evitar el eco.", ancho_nota=210)
        llamadas.pack(fill="x")

    def _armar_registro(self, marco):
        c = tema.COLORES
        carta = tema.Carta(marco, radio=24, margen=(20, 18))
        carta.pack(fill="both", expand=True)
        tk.Label(carta.interior, text="Registro de actividad", font=tema.fuente(11, "bold"),
                 bg=c["panel"], fg=c["texto"]).pack(anchor="w", pady=(0, 10))
        zona, self.registro = tema.texto_con_barra(carta.interior, alto=20)
        zona.pack(fill="both", expand=True)

    # ---------- estado y navegación ----------
    def _ir_a(self, clave):
        self.seccion = clave
        self.marcos[clave].tkraise()
        self.lateral.activar(clave)
        self.lbl_titulo.config(text=TITULOS[clave])
        if clave == "comunicacion":
            self.lateral.marcar("comunicacion", False)

    def _cambiar_tema(self):
        """Alterna entre tema claro y oscuro reconstruyendo la ventana (sin perder chat, registro ni pantallas)."""
        elegida = self.lista.seleccionada()
        nombres = self.lista.nombres()
        tema.cambiar_tema("oscuro" if tema.tema_actual() == "claro" else "claro")
        tema.aplicar(self.raiz)
        self.base.destroy()
        self._construir()
        for nombre in nombres:
            self.lista.agregar(nombre)
            self._poner_estado_pc(nombre)
        if elegida in nombres:
            self.lista.seleccionar(elegida)
        self._actualizar_estado()

    def _actualizar_estado(self):
        c = tema.COLORES
        n = len(self.clientes)
        self.estado.configure(
            text=f"● {n} PC{'s' if n != 1 else ''} conectada{'s' if n != 1 else ''}",
            fg=c["verde"] if n else c["amarillo"],
        )
        self.num_pcs.config(text=str(n))
        self.num_pantallas.config(text=f"{len(self.viendo)}/{MAX_PANTALLAS}")
        self.num_transmitiendo.config(text=str(len(self.transmitiendo)))
        for nombre in self.lista.nombres():
            self._poner_estado_pc(nombre)
        self._refrescar_perfil()
        self._texto_objetivo()
        self._texto_exhibicion()

    def _texto_exhibicion(self):
        if hasattr(self, "lbl_exhibicion") and self.lbl_exhibicion.winfo_exists():
            if self.exhibiciones:
                partes = [f"{o} → {', '.join(sorted(d))}" for o, d in self.exhibiciones.items()]
                self.lbl_exhibicion.config(text="Exhibiendo:  " + "   ·   ".join(partes), fg=tema.COLORES["acento"])
            else:
                self.lbl_exhibicion.config(text="Sin exhibiciones activas", fg=tema.COLORES["suave"])

    def _poner_estado_pc(self, nombre):
        c = tema.COLORES
        origen = next((o for o, d in self.exhibiciones.items() if nombre in d), None)
        if nombre in self.viendo:
            self.lista.estado(nombre, "● Pantalla en vivo", c["acento"])
        elif nombre in self.exhibiciones:
            self.lista.estado(nombre, "● Se está exhibiendo", c["acento"])
        elif origen:
            self.lista.estado(nombre, f"● Viendo a {origen}", c["acento"])
        elif nombre == self.par_llamada:
            self.lista.estado(nombre, "● En llamada", c["amarillo"])
        else:
            self.lista.estado(nombre, "● Conectada", c["verde"])

    def _texto_objetivo(self):
        nombre = self.lista.seleccionada()
        if hasattr(self, "lbl_objetivo") and self.lbl_objetivo.winfo_exists():
            self.lbl_objetivo.config(
                text=f"Las acciones se aplican a:  {nombre}" if nombre else "Elige una PC de la lista para controlarla")

    def _al_elegir(self, _nombre=None):
        self._refrescar_perfil()
        self._texto_objetivo()

    def _refrescar_perfil(self):
        """Dibuja la tarjeta 'PC seleccionada' (nombre, estado y datos de la PC elegida)."""
        if not hasattr(self, "zona_perfil") or not self.zona_perfil.winfo_exists():
            return
        c = tema.COLORES
        for hijo in self.zona_perfil.winfo_children():
            hijo.destroy()
        nombre = self.lista.seleccionada()
        fila = tk.Frame(self.zona_perfil, bg=c["panel"])
        fila.pack(fill="x")
        tema.avatar(fila, nombre or "?", 58, c["panel"]).pack(side="left")
        textos = tk.Frame(fila, bg=c["panel"])
        textos.pack(side="left", padx=(12, 0))
        if not nombre:
            tk.Label(textos, text="Ninguna elegida", font=tema.fuente(12, "bold"), bg=c["panel"], fg=c["texto"]).pack(anchor="w")
            tk.Label(textos, text="Elige una de la lista", font=tema.fuente(9), bg=c["panel"], fg=c["suave"]).pack(anchor="w")
            return
        tk.Label(textos, text=nombre, font=tema.fuente(13, "bold"), bg=c["panel"], fg=c["texto"]).pack(anchor="w")
        tk.Label(textos, text="● Conectada", font=tema.fuente(9), bg=c["panel"], fg=c["verde"]).pack(anchor="w")

        datos = tk.Frame(self.zona_perfil, bg=c["panel"])
        datos.pack(fill="x", pady=(14, 0))
        for etiqueta, valor in (
            ("Su pantalla", "en vivo" if nombre in self.viendo else "sin ver"),
            ("Ve la tuya", "sí" if nombre in self.transmitiendo else "no"),
            ("Exhibida en", ", ".join(sorted(self.exhibiciones.get(nombre, ()))) or "ninguna"),
            ("Llamada", "en curso" if nombre == self.par_llamada else "ninguna"),
        ):
            linea = tk.Frame(datos, bg=c["panel"])
            linea.pack(fill="x", pady=1)
            tk.Label(linea, text=etiqueta, font=tema.fuente(10), bg=c["panel"], fg=c["suave"]).pack(side="left")
            tk.Label(linea, text=valor, font=tema.fuente(10, "bold"), bg=c["panel"], fg=c["texto"]).pack(side="right")
        tema.Pildora(self.zona_perfil, "Ver / dejar de ver", self.alternar_pantalla, "acento", alto=36).pack(anchor="w", pady=(14, 0))

    def _escribir(self, texto):
        """Escribe en el apartado Registro."""
        etiqueta = "error" if ("ERROR" in texto or "no se pudo" in texto.lower()) else "suave"
        self.hist_registro.append((texto, etiqueta))
        del self.hist_registro[:-MAX_HISTORIAL]
        tema.agregar_linea(self.registro, texto, etiqueta)

    def _escribir_chat(self, texto, propio=False):
        etiqueta = "propio" if propio else "otro"
        self.hist_chat.append((texto, etiqueta))
        del self.hist_chat[:-MAX_HISTORIAL]
        tema.agregar_linea(self.chat, texto, etiqueta)

    def _aviso_chat(self):
        """Marca la sección Comunicación si llega un mensaje y no se está viendo."""
        if self.seccion != "comunicacion":
            self.lateral.marcar("comunicacion", True)

    # ---------- acciones de los botones ----------
    def _seleccionada(self):
        nombre = self.lista.seleccionada()
        if not nombre:
            messagebox.showinfo("Aviso", "Primero elige una PC de la lista.")
            return None
        return nombre

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
            self._actualizar_estado()

    def _dejar_de_ver(self, nombre, avisar=True):
        posicion = self.viendo.pop(nombre, None)
        if posicion is None:
            return
        if avisar and nombre not in self.exhibiciones:  # si se exhibe, su pantalla debe seguir capturándose
            self._orden("ver_pantalla", {"activo": False}, nombre=nombre)
        self.fotos[posicion] = None
        self.titulos[posicion].config(text="(libre)")
        self.pantallas[posicion].config(image=self.vacio)
        self._actualizar_estado()

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
            self.boton_todas.cambiar_texto("Ver todas (hasta 3)")
            return
        for nombre in list(self.clientes)[:MAX_PANTALLAS]:
            self._empezar_a_ver(nombre)
        if self.viendo:
            self.boton_todas.cambiar_texto("Dejar de ver todas")

    # ---------- exhibir un cliente: mostrar la pantalla de una PC en otra ----------
    def elegir_destino(self):
        """Muestra un menú con las demás PCs; la que se elija verá la pantalla de la PC seleccionada."""
        origen = self._seleccionada()
        if not origen:
            return
        otras = [n for n in self.clientes if n != origen]
        if not otras:
            messagebox.showinfo("Aviso", "Necesitas al menos otra PC conectada para exhibir.")
            return
        c = tema.COLORES
        menu = tk.Menu(self.raiz, tearoff=0, bg=c["panel"], fg=c["texto"], activebackground=c["acento"],
                       activeforeground=c["sobre_acento"], bd=0, font=tema.fuente(10))
        menu.add_command(label=f"Mostrar la pantalla de {origen} en:", state="disabled")
        menu.add_separator()
        for destino in otras:
            activa = destino in self.exhibiciones.get(origen, ())
            menu.add_command(label=("✓  " if activa else "     ") + destino,
                             command=lambda d=destino: self._alternar_exhibicion(origen, d))
        x = self.boton_exhibir.winfo_rootx()
        y = self.boton_exhibir.winfo_rooty() + self.boton_exhibir.winfo_height() + 4
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _alternar_exhibicion(self, origen, destino):
        if destino in self.exhibiciones.get(origen, ()):
            self._detener_exhibicion(origen, destino)
        else:
            self._iniciar_exhibicion(origen, destino)

    def _iniciar_exhibicion(self, origen, destino):
        if origen == destino or origen not in self.clientes or destino not in self.clientes:
            return
        if destino in self.exhibiciones.get(origen, ()):
            return
        if not self._orden("exhibir", {"origen": origen, "activo": True}, nombre=destino):
            return
        if not self._orden("ver_pantalla", {"activo": True}, nombre=origen):  # que la origen mande su pantalla
            self._orden("exhibir", {"origen": origen, "activo": False}, nombre=destino)
            return
        self.exhibiciones.setdefault(origen, set()).add(destino)
        self._escribir(f"[sistema] exhibiendo la pantalla de {origen} en {destino}")
        self._actualizar_estado()

    def _detener_exhibicion(self, origen, destino=None):
        """Quita una exhibición (origen -> destino) o todas las de esa PC origen."""
        destinos = self.exhibiciones.get(origen)
        if not destinos:
            return
        for d in ([destino] if destino else list(destinos)):
            if d in destinos:
                destinos.discard(d)
                if d in self.clientes:
                    self._orden("exhibir", {"origen": origen, "activo": False}, nombre=d)
                self._escribir(f"[sistema] se dejó de exhibir {origen} en {d}")
        if not destinos:
            self.exhibiciones.pop(origen, None)
            if origen not in self.viendo and origen in self.clientes:
                self._orden("ver_pantalla", {"activo": False}, nombre=origen)
        self._actualizar_estado()

    def dejar_de_exhibir(self):
        """Termina todas las exhibiciones de la PC elegida."""
        origen = self._seleccionada()
        if not origen:
            return
        if origen in self.exhibiciones:
            self._detener_exhibicion(origen)
        else:
            self._escribir(f"[sistema] {origen} no se está exhibiendo")

    def _quitar_de_exhibiciones(self, nombre):
        """Una PC se desconectó: se cancela lo que exhibía y lo que veía."""
        self._detener_exhibicion(nombre)
        for origen in list(self.exhibiciones):
            if nombre in self.exhibiciones.get(origen, ()):
                self._detener_exhibicion(origen, nombre)

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
        self._actualizar_estado()

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
        self._actualizar_estado()

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
                    self.lista.agregar(nombre)
                    self._escribir(f"[sistema] {nombre} se conectó")
                    self._actualizar_estado()
                elif evento == "desconectado":
                    self.lista.quitar(nombre)
                    self._quitar_de_exhibiciones(nombre)
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
        elif tipo == "imagen":
            if nombre in self.viendo:
                posicion = self.viendo[nombre]
                imagen = Image.open(io.BytesIO(binario))
                imagen.thumbnail((ANCHO, ALTO))
                self.fotos[posicion] = ImageTk.PhotoImage(imagen)
                self.pantallas[posicion].config(image=self.fotos[posicion])
            for destino in list(self.exhibiciones.get(nombre, ())):  # exhibir: reenviar tal cual a las PCs destino
                try:
                    self.clientes[destino].enviar("imagen_exhibida", {"origen": nombre}, binario)
                except (OSError, KeyError, AttributeError):
                    self._detener_exhibicion(nombre, destino)
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
            self._actualizar_estado()
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