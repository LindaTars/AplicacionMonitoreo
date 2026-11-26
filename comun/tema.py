"""Tema (claro y oscuro), fuentes, estilos y widgets redondeados compartidos por el servidor y el agente.

Lo viejo sigue funcionando igual (aplicar, tarjeta, botones, texto_con_barra, agregar_linea, COLORES...),
así que el agente se ve con la paleta nueva sin tocarlo. Lo nuevo (Carta, Pildora, Lateral, ListaPCs...)
dibuja formas suaves con Pillow, que el servidor ya usa.
"""
import tkinter as tk
from functools import lru_cache
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

# ---------------------------------------------------------------- paletas
TEMAS = {
    "claro": {
        "fondo": "#fbf2fb",      # fondo general (rosa muy claro)
        "panel": "#ffffff",      # tarjetas
        "panel2": "#f6edfc",     # filas, cajas de texto, botones suaves
        "borde": "#eadcf5",
        "texto": "#2a2145",
        "suave": "#8f84a8",
        "acento": "#a45df0",
        "acento2": "#c58af7",
        "grad1": "#8b5cf6",      # extremos del degradado de botones y logo
        "grad2": "#ec6fb8",
        "lateral1": "#e5dbfa",   # degradado de la barra lateral (arriba -> abajo)
        "lateral2": "#fdc8e7",
        "sobre_acento": "#ffffff",
        "verde": "#25b27a",
        "rojo": "#ee5d85",
        "rojo2": "#f58aa8",
        "amarillo": "#e99a2b",
    },
    "oscuro": {
        "fondo": "#1f2140",
        "panel": "#2b2e52",
        "panel2": "#353962",
        "borde": "#41457a",
        "texto": "#eeebff",
        "suave": "#9ca0cc",
        "acento": "#b673f5",
        "acento2": "#cda3f8",
        "grad1": "#8b5cf6",
        "grad2": "#ec6fb8",
        "lateral1": "#17182f",
        "lateral2": "#262851",
        "sobre_acento": "#ffffff",
        "verde": "#5fd8a0",
        "rojo": "#ff6f96",
        "rojo2": "#ff94b2",
        "amarillo": "#f6c46a",
    },
}

COLORES = {}          # la paleta activa (se rellena en cambiar_tema)
_nombre_tema = "claro"


def cambiar_tema(nombre):
    """Cambia la paleta activa. Después hay que volver a llamar a aplicar() y reconstruir la ventana."""
    global _nombre_tema
    _nombre_tema = nombre if nombre in TEMAS else "claro"
    COLORES.clear()
    COLORES.update(TEMAS[_nombre_tema])


def tema_actual():
    return _nombre_tema


cambiar_tema("claro")

# ---------------------------------------------------------------- fuentes
_FAMILIA = "Sans"
FUENTE = ("Sans", 10)
FUENTE_TITULO = ("Sans", 16, "bold")
FUENTE_SECCION = ("Sans", 11, "bold")


def _elegir_fuente(raiz):
    global _FAMILIA, FUENTE, FUENTE_TITULO, FUENTE_SECCION
    instaladas = set(tkfont.families(raiz))
    for nombre in ("Inter", "Roboto", "Poppins", "Noto Sans", "Cantarell", "DejaVu Sans"):
        if nombre in instaladas:
            _FAMILIA = nombre
            break
    FUENTE = (_FAMILIA, 10)
    FUENTE_TITULO = (_FAMILIA, 16, "bold")
    FUENTE_SECCION = (_FAMILIA, 11, "bold")


def fuente(tam=10, estilo=""):
    return (_FAMILIA, tam, estilo) if estilo else (_FAMILIA, tam)


# ---------------------------------------------------------------- estilos ttk (lo que ya usaba el agente)
def _boton(estilo, nombre, fondo, hover, texto):
    estilo.configure(
        nombre, background=fondo, foreground=texto, bordercolor=fondo, lightcolor=fondo,
        darkcolor=fondo, padding=(14, 8), borderwidth=0, relief="flat", focusthickness=0,
    )
    estilo.map(
        nombre,
        background=[("active", hover), ("pressed", hover)],
        bordercolor=[("active", hover), ("pressed", hover)],
        lightcolor=[("active", hover), ("pressed", hover)],
        darkcolor=[("active", hover), ("pressed", hover)],
    )


def aplicar(raiz):
    """Aplica el tema a toda la aplicación. Se llama justo después de crear la ventana (y al cambiar de tema)."""
    _elegir_fuente(raiz)
    c = COLORES
    raiz.configure(bg=c["fondo"])
    raiz.option_add("*Font", FUENTE)
    e = ttk.Style(raiz)
    e.theme_use("clam")
    e.configure(
        ".", background=c["fondo"], foreground=c["texto"], fieldbackground=c["panel2"],
        bordercolor=c["borde"], lightcolor=c["fondo"], darkcolor=c["fondo"],
        troughcolor=c["panel"], font=FUENTE, focuscolor=c["fondo"],
    )

    # marcos y textos
    e.configure("TFrame", background=c["fondo"])
    e.configure("Tarjeta.TFrame", background=c["panel"])
    e.configure("TLabel", background=c["fondo"], foreground=c["texto"])
    e.configure("Tarjeta.TLabel", background=c["panel"], foreground=c["texto"])
    e.configure("Titulo.TLabel", font=FUENTE_TITULO, foreground=c["acento"])
    e.configure("Seccion.TLabel", font=FUENTE_SECCION, foreground=c["texto"])
    e.configure("TarjetaSeccion.TLabel", font=FUENTE_SECCION, background=c["panel"], foreground=c["texto"])
    e.configure("Suave.TLabel", foreground=c["suave"])
    e.configure("Nota.TLabel", background=c["panel"], foreground=c["suave"])

    # tarjetas con título
    e.configure(
        "Tarjeta.TLabelframe", background=c["panel"], bordercolor=c["borde"],
        lightcolor=c["panel"], darkcolor=c["panel"],
    )
    e.configure("Tarjeta.TLabelframe.Label", background=c["panel"], foreground=c["acento"], font=FUENTE_SECCION)

    # apartados (pestañas)
    e.configure("TNotebook", background=c["fondo"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    e.configure("TNotebook.Tab", background=c["panel"], foreground=c["suave"], padding=(20, 10), borderwidth=0)
    e.map(
        "TNotebook.Tab",
        background=[("selected", c["panel2"]), ("active", c["panel2"])],
        foreground=[("selected", c["acento"]), ("active", c["texto"])],
    )

    # botones
    _boton(e, "TButton", c["panel2"], c["borde"], c["texto"])
    _boton(e, "Acento.TButton", c["acento"], c["acento2"], c["sobre_acento"])
    _boton(e, "Peligro.TButton", c["rojo"], c["rojo2"], c["sobre_acento"])

    # cajas de texto y barras de desplazamiento
    e.configure(
        "TEntry", fieldbackground=c["panel2"], foreground=c["texto"], insertcolor=c["texto"],
        bordercolor=c["borde"], lightcolor=c["panel2"], darkcolor=c["panel2"], padding=8,
    )
    e.map("TEntry", bordercolor=[("focus", c["acento"])])
    pulgar = _mezclar(c["borde"], c["suave"], 0.45)
    e.layout("Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
        ]}),
    ])
    e.configure(
        "Vertical.TScrollbar", background=pulgar, troughcolor=c["panel"], bordercolor=c["panel"],
        lightcolor=pulgar, darkcolor=pulgar, width=10, gripcount=0, relief="flat", borderwidth=0,
    )
    e.map(
        "Vertical.TScrollbar",
        background=[("active", c["acento2"]), ("pressed", c["acento"])],
        lightcolor=[("active", c["acento2"]), ("pressed", c["acento"])],
        darkcolor=[("active", c["acento2"]), ("pressed", c["acento"])],
    )


# ---------------------------------------------------------------- ayudas para armar ventanas (igual que antes)
def estilo_lista(lista):
    c = COLORES
    lista.configure(
        bg=c["panel2"], fg=c["texto"], selectbackground=c["acento"], selectforeground=c["sobre_acento"],
        highlightthickness=0, bd=0, relief="flat", activestyle="none", font=FUENTE,
    )


def estilo_texto(texto):
    c = COLORES
    texto.configure(
        bg=c["panel"], fg=c["texto"], insertbackground=c["texto"], relief="flat", bd=0,
        highlightthickness=0, padx=12, pady=10, font=FUENTE, selectbackground=c["borde"], wrap="word",
    )
    texto.tag_configure("propio", foreground=c["acento"])
    texto.tag_configure("otro", foreground=c["texto"])
    texto.tag_configure("suave", foreground=c["suave"])
    texto.tag_configure("error", foreground=c["rojo"])
    texto.tag_configure("ok", foreground=c["verde"])


def texto_con_barra(padre, alto=10):
    """Caja de texto de solo lectura con barra de desplazamiento. Devuelve (marco, texto)."""
    marco = ttk.Frame(padre, style="Tarjeta.TFrame")
    texto = tk.Text(marco, height=alto, state="disabled")
    estilo_texto(texto)
    barra = ttk.Scrollbar(marco, orient="vertical", command=texto.yview)
    texto.pack(side="left", fill="both", expand=True)

    def ajustar(primero, ultimo):
        """La barra solo aparece cuando hay texto de sobra."""
        barra.set(primero, ultimo)
        if float(primero) <= 0.0 and float(ultimo) >= 1.0:
            if barra.winfo_manager():
                barra.pack_forget()
        elif not barra.winfo_manager():
            barra.pack(side="right", fill="y", before=texto)

    texto.configure(yscrollcommand=ajustar)
    return marco, texto


def agregar_linea(texto, linea, etiqueta=None):
    texto.config(state="normal")
    texto.insert("end", linea + "\n", (etiqueta,) if etiqueta else ())
    texto.see("end")
    texto.config(state="disabled")


def tarjeta(padre, titulo):
    """Tarjeta con título (el que la llama decide cómo colocarla: pack o grid)."""
    return ttk.LabelFrame(padre, text=f" {titulo} ", style="Tarjeta.TLabelframe", padding=14)


def botones(tarjeta_, lista, nota=""):
    """Pone una fila de botones [(texto, estilo, comando), ...] y una nota debajo."""
    fila = ttk.Frame(tarjeta_, style="Tarjeta.TFrame")
    fila.pack(anchor="w")
    for texto, estilo, comando in lista:
        ttk.Button(fila, text=texto, style=estilo, command=comando).pack(side="left", padx=(0, 8))
    if nota:
        ttk.Label(tarjeta_, text=nota, style="Nota.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(10, 0))


# ================================================================ formas suaves (Pillow)
_RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
_ROTAR_90 = getattr(Image, "Transpose", Image).ROTATE_90


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mezclar(c1, c2, t):
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _aclarar(c, t=0.18):
    return _mezclar(c, "#ffffff", t)


def _fondo_de(widget):
    try:
        return widget.cget("bg")
    except tk.TclError:  # los widgets ttk no tienen bg
        return COLORES["fondo"]


@lru_cache(maxsize=96)
def _forma(w, h, radio, c1, c2, borde=None, grosor=0, horizontal=True):
    """Rectángulo redondeado con degradado (c1 -> c2) y borde opcionales, suavizado, con transparencia."""
    s = 3
    ancho, alto = w * s, h * s
    r = max(0, min(radio * s, min(ancho, alto) // 2))
    mascara = Image.new("L", (ancho, alto), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, ancho - 1, alto - 1), r, fill=255)
    if c1 == c2:
        relleno = Image.new("RGBA", (ancho, alto), c1)
    else:
        grad = Image.linear_gradient("L")           # negro arriba -> blanco abajo
        if horizontal:
            grad = grad.transpose(_ROTAR_90)         # negro izquierda -> blanco derecha
        grad = grad.resize((ancho, alto))
        relleno = Image.composite(Image.new("RGB", (ancho, alto), c2), Image.new("RGB", (ancho, alto), c1), grad)
        relleno = relleno.convert("RGBA")
    if borde and grosor:
        base = Image.new("RGBA", (ancho, alto), borde)
        g = grosor * s
        interior = Image.new("L", (ancho, alto), 0)
        ImageDraw.Draw(interior).rounded_rectangle((g, g, ancho - 1 - g, alto - 1 - g), max(r - g, 0), fill=255)
        base.paste(relleno, (0, 0), interior)
        relleno = base
    relleno.putalpha(mascara)
    return relleno.resize((w, h), _RESAMPLE)


@lru_cache(maxsize=8)
def _degradado_v(w, h, c1, c2):
    grad = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), grad)


@lru_cache(maxsize=16)
def ilustracion_monitor(ancho=150, tema_nombre="claro"):
    """Dibujito de una pantalla con gráfica, para decorar la bienvenida."""
    c = COLORES
    w = ancho
    h = int(w * 0.86)
    alto_pantalla = int(h * 0.72)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.alpha_composite(_forma(w, alto_pantalla, 14, c["grad1"], c["grad2"], None, 0, True), (0, 0))
    margen = max(8, w // 14)
    img.alpha_composite(
        _forma(w - 2 * margen, alto_pantalla - 2 * margen, 9, c["panel"], c["panel"], None, 0, True), (margen, margen))
    dib = ImageDraw.Draw(img)
    # barritas de la gráfica
    zona_x0, zona_x1 = margen + 12, w - margen - 12
    zona_y1 = alto_pantalla - margen - 10
    n = 5
    paso = (zona_x1 - zona_x0) / n
    for i, f in enumerate((0.35, 0.6, 0.45, 0.85, 0.55)):
        x0 = zona_x0 + i * paso + paso * 0.18
        x1 = zona_x0 + (i + 1) * paso - paso * 0.18
        y0 = zona_y1 - (zona_y1 - (margen + 12)) * f
        dib.rounded_rectangle((x0, y0, x1, zona_y1), 3, fill=_rgb(_mezclar(c["grad1"], c["grad2"], i / (n - 1))))
    # pie y base
    cuello_w = max(10, w // 8)
    dib.rectangle(((w - cuello_w) // 2, alto_pantalla - 2, (w + cuello_w) // 2, h - 8), fill=_rgb(c["acento2"]))
    img.alpha_composite(_forma(int(w * 0.5), 9, 4, c["acento"], c["acento2"], None, 0, True), (int(w * 0.25), h - 10))
    return img


def decorar_monitor(lienzo, w, h):
    """Dibuja la pantallita con papelitos flotantes a la derecha de una Carta (úsalo como decoracion=).
    Solo se dibuja si queda espacio libre a la derecha del contenido, para no encimarse con el texto."""
    c = COLORES
    ancho = int(max(90, min(150, (h - 24) / 0.86)))
    cx, cy = w - 30 - ancho // 2 - 54, h // 2
    izquierda = cx - ancho // 2 - 48 - 17            # el papelito más a la izquierda
    try:
        interior = lienzo.master.interior
        fin_texto = interior.winfo_x() + interior.winfo_width()
    except (AttributeError, tk.TclError):
        fin_texto = 0
    if izquierda < fin_texto + 16:
        return
    mon = ImageTk.PhotoImage(ilustracion_monitor(ancho, _nombre_tema))
    lienzo._deco = [mon]
    lienzo.create_image(cx, cy, image=mon, anchor="center")
    for dx, dy, lado, angulo, a, b in (
        (-ancho // 2 - 48, -h * 0.22, 34, 12, c["grad2"], c["acento2"]),
        (ancho // 2 + 26, -h * 0.26, 40, -10, c["acento2"], c["grad1"]),
        (ancho // 2 + 50, h * 0.14, 30, 16, c["grad1"], c["grad2"]),
    ):
        papel = _forma(lado, lado, 9, a, b, None, 0, False).rotate(angulo, expand=True, resample=Image.BICUBIC)
        foto = ImageTk.PhotoImage(papel)
        lienzo._deco.append(foto)
        lienzo.create_image(cx + dx, cy + dy, image=foto, anchor="center")


# ================================================================ widgets redondeados
class Carta(tk.Frame):
    """Tarjeta de esquinas redondeadas. Lo que va dentro se pone en `carta.interior`."""

    def __init__(self, padre, relleno=None, borde=None, radio=18, margen=16, expandir=True, decoracion=None, **kw):
        fondo = _fondo_de(padre)
        super().__init__(padre, bg=fondo, **kw)
        c = COLORES
        self._relleno = relleno or c["panel"]
        self._borde = c["borde"] if borde is None else borde
        self._grosor = 1 if self._borde else 0
        self._radio = radio
        self._decoracion = decoracion
        self._job = None
        self._foto = None
        mx, my = margen if isinstance(margen, tuple) else (margen, margen)
        self._lienzo = tk.Canvas(self, bg=fondo, highlightthickness=0, bd=0)
        self._lienzo.place(x=0, y=0, relwidth=1, relheight=1)
        self.interior = tk.Frame(self, bg=self._relleno)
        if expandir:
            self.interior.pack(fill="both", expand=True, padx=mx, pady=my)
        else:
            self.interior.pack(side="left", fill="y", padx=mx, pady=my)
        self.bind("<Configure>", self._pedir)

    def pintar(self, relleno=None, borde=None, grosor=None):
        """Cambia el color de relleno y/o del borde (por ejemplo, para marcar una fila elegida)."""
        if relleno:
            self._relleno = relleno
            self.interior.configure(bg=relleno)
        if borde is not None:
            self._borde = borde
        if grosor is not None:
            self._grosor = grosor
        self._dibujar()

    def _pedir(self, _evento=None):
        if self._job is None:
            self._job = self.after(12, self._dibujar)

    def _dibujar(self):
        self._job = None
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            return
        imagen = _forma(w, h, self._radio, self._relleno, self._relleno, self._borde, self._grosor, True)
        self._foto = ImageTk.PhotoImage(imagen)
        self._lienzo.delete("all")
        self._lienzo.create_image(0, 0, anchor="nw", image=self._foto)
        if self._decoracion:
            self._decoracion(self._lienzo, w, h)

    def destroy(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        super().destroy()


class Pildora(tk.Canvas):
    """Botón en forma de píldora. variante: 'acento' (degradado), 'peligro' o 'suave'."""

    def __init__(self, padre, texto, comando, variante="suave", alto=38, ancho=None, tam=10):
        self._fuente = fuente(tam, "bold")
        self._texto = texto
        self._comando = comando
        self._variante = variante
        self._alto = alto
        self._fijo = ancho
        self._adentro = False
        self._fotos = {}
        super().__init__(padre, height=alto, bg=_fondo_de(padre), highlightthickness=0, bd=0, cursor="hand2")
        self._medir()
        self._dibujar()
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonRelease-1>", self._soltar)

    def _medir(self):
        ancho = self._fijo or tkfont.Font(font=self._fuente).measure(self._texto) + 40
        self._ancho = ancho
        self.configure(width=ancho)

    def cambiar_texto(self, texto):
        self._texto = texto
        self._medir()
        self._dibujar()

    def _colores(self):
        c = COLORES
        if self._variante == "acento":
            a, b, t, borde = c["grad1"], c["grad2"], c["sobre_acento"], None
            if self._adentro:
                a, b = _aclarar(a), _aclarar(b)
        elif self._variante == "peligro":
            a, b, t, borde = c["rojo"], c["rojo2"], c["sobre_acento"], None
            if self._adentro:
                a, b = _aclarar(a), _aclarar(b)
        else:
            a = b = c["borde"] if self._adentro else c["panel2"]
            t, borde = c["texto"], c["borde"]
        return a, b, t, borde

    def _dibujar(self):
        a, b, t, borde = self._colores()
        imagen = _forma(self._ancho, self._alto, self._alto // 2, a, b, borde, 1 if borde else 0, True)
        self._foto = ImageTk.PhotoImage(imagen)
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._foto)
        self.create_text(self._ancho / 2, self._alto / 2, text=self._texto, fill=t, font=self._fuente)

    def _hover(self, dentro):
        self._adentro = dentro
        self._dibujar()

    def _soltar(self, evento):
        if 0 <= evento.x <= self._ancho and 0 <= evento.y <= self._alto and self._comando:
            self._comando()


_PARES_AVATAR = [("#8b5cf6", "#ec6fb8"), ("#6366f1", "#8b5cf6"), ("#f59e0b", "#ef6f9a"), ("#14b8a6", "#6366f1")]


def avatar(padre, nombre, d=40, fondo=None):
    """Círculo con degradado y la inicial del nombre."""
    nombre = nombre or "?"
    par = _PARES_AVATAR[sum(map(ord, nombre)) % len(_PARES_AVATAR)]
    lienzo = tk.Canvas(padre, width=d, height=d, bg=fondo or _fondo_de(padre), highlightthickness=0, bd=0)
    lienzo._foto = ImageTk.PhotoImage(_forma(d, d, d // 2, par[0], par[1], None, 0, True))
    lienzo.create_image(0, 0, anchor="nw", image=lienzo._foto)
    lienzo.create_text(d / 2, d / 2, text=nombre[0].upper(), fill="#ffffff", font=fuente(max(9, int(d * 0.38)), "bold"))
    return lienzo


class Lateral(tk.Canvas):
    """Barra lateral con degradado: logo, secciones (la activa en píldora) y una tarjetita de información."""

    def __init__(self, padre, secciones, al_elegir, titulo="Monitoreo", info=(), ancho=224):
        c = COLORES
        super().__init__(padre, width=ancho, bg=c["lateral2"], highlightthickness=0, bd=0)
        self.secciones = secciones          # [(clave, icono, texto), ...]
        self.al_elegir = al_elegir
        self.titulo = titulo
        self.info = list(info)              # primera línea = título de la tarjetita
        self.activa = secciones[0][0]
        self.insignias = set()
        self._fotos = []
        self._job = None
        self._inicio_y, self._paso, self._alto_item = 112, 52, 42
        self.bind("<Configure>", self._pedir)
        self.bind("<Button-1>", self._clic)
        self.bind("<Motion>", self._mover)

    def activar(self, clave):
        self.activa = clave
        self._dibujar()

    def marcar(self, clave, valor=True):
        if valor and clave not in self.insignias:
            self.insignias.add(clave)
            self._dibujar()
        elif not valor and clave in self.insignias:
            self.insignias.discard(clave)
            self._dibujar()

    def _pedir(self, _evento=None):
        if self._job is None:
            self._job = self.after(12, self._dibujar)

    def _item_en(self, x, y):
        w = self.winfo_width()
        if not (16 <= x <= w - 16):
            return None
        for i, (clave, _icono, _texto) in enumerate(self.secciones):
            arriba = self._inicio_y + i * self._paso
            if arriba <= y <= arriba + self._alto_item:
                return clave
        return None

    def _clic(self, e):
        clave = self._item_en(e.x, e.y)
        if clave:
            self.al_elegir(clave)

    def _mover(self, e):
        self.configure(cursor="hand2" if self._item_en(e.x, e.y) else "")

    def _dibujar(self):
        self._job = None
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        c = COLORES
        self.delete("all")
        self._fotos = []

        def poner(imagen, x, y):
            foto = ImageTk.PhotoImage(imagen)
            self._fotos.append(foto)
            self.create_image(x, y, anchor="nw", image=foto)

        poner(_degradado_v(w, h, c["lateral1"], c["lateral2"]), 0, 0)

        # logo
        poner(_forma(42, 42, 21, c["grad1"], c["grad2"], None, 0, True), 22, 30)
        self.create_text(43, 51, text="M", fill="#ffffff", font=fuente(15, "bold"))
        self.create_text(76, 51, text=self.titulo, fill=c["texto"], font=fuente(13, "bold"), anchor="w")

        # secciones
        for i, (clave, icono, texto) in enumerate(self.secciones):
            arriba = self._inicio_y + i * self._paso
            activa = clave == self.activa
            if activa:
                poner(_forma(w - 32, self._alto_item, self._alto_item // 2, c["grad1"], c["grad2"], None, 0, True), 16, arriba)
            color = c["sobre_acento"] if activa else c["texto"]
            medio = arriba + self._alto_item / 2
            self.create_text(42, medio, text=icono, fill=color, font=fuente(13))
            self.create_text(66, medio, text=texto, fill=color, font=fuente(11, "bold" if activa else ""), anchor="w")
            if clave in self.insignias:
                self.create_oval(w - 44, medio - 5, w - 34, medio + 5, fill=c["rojo"] if not activa else "#ffffff", outline="")

        # tarjetita de información abajo
        if self.info:
            alto_tarjeta = 34 + 22 * (len(self.info) - 1)
            y = h - 22 - alto_tarjeta
            if y > self._inicio_y + len(self.secciones) * self._paso:
                poner(_forma(w - 32, alto_tarjeta, 18, c["panel"], c["panel"], c["borde"], 1, True), 16, y)
                self.create_text(32, y + 20, text=self.info[0], fill=c["acento"], font=fuente(11, "bold"), anchor="w")
                for i, linea in enumerate(self.info[1:]):
                    self.create_text(32, y + 42 + i * 21, text=linea, fill=c["suave"], font=fuente(10), anchor="w")

    def destroy(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        super().destroy()


class ListaPCs(tk.Frame):
    """Lista de PCs conectadas: una fila (tarjeta redondeada) por PC, con avatar, nombre y estado."""

    def __init__(self, padre, al_elegir=None):
        fondo = _fondo_de(padre)
        super().__init__(padre, bg=fondo)
        self._fondo = fondo
        self.al_elegir = al_elegir
        self._filas = {}
        self._elegida = None

        self._lienzo = tk.Canvas(self, bg=fondo, highlightthickness=0, bd=0)
        self._lienzo.pack(fill="both", expand=True)
        self._cuerpo = tk.Frame(self._lienzo, bg=fondo)
        self._ventana = self._lienzo.create_window((0, 0), window=self._cuerpo, anchor="nw")
        self._cuerpo.bind("<Configure>", lambda e: self._lienzo.configure(scrollregion=self._lienzo.bbox("all")))
        self._lienzo.bind("<Configure>", lambda e: self._lienzo.itemconfigure(self._ventana, width=e.width))
        self._enlazar_rueda(self._lienzo)
        self._enlazar_rueda(self._cuerpo)

        c = COLORES
        self._vacio = tk.Label(
            self._cuerpo, text="Esperando conexiones...\nEscribe la IP del servidor\nen cada agente.",
            bg=fondo, fg=c["suave"], font=fuente(10), justify="center",
        )
        self._vacio.pack(pady=28)

    # --- desplazamiento con la rueda
    def _enlazar_rueda(self, widget):
        widget.bind("<MouseWheel>", self._rueda, add="+")
        widget.bind("<Button-4>", self._rueda, add="+")
        widget.bind("<Button-5>", self._rueda, add="+")

    def _rueda(self, evento):
        if self._cuerpo.winfo_reqheight() <= self._lienzo.winfo_height():
            return
        arriba = getattr(evento, "num", 0) == 4 or getattr(evento, "delta", 0) > 0
        self._lienzo.yview_scroll(-2 if arriba else 2, "units")

    # --- uso
    def nombres(self):
        return list(self._filas)

    def seleccionada(self):
        return self._elegida

    def agregar(self, nombre):
        if nombre in self._filas:
            return
        c = COLORES
        self._vacio.pack_forget()
        carta = Carta(self._cuerpo, relleno=c["panel2"], borde=c["panel2"], radio=16, margen=(12, 9))
        carta.pack(fill="x", pady=(0, 8))
        interior = carta.interior
        foto = avatar(interior, nombre, 38, c["panel2"])
        foto.pack(side="left")
        textos = tk.Frame(interior, bg=c["panel2"])
        textos.pack(side="left", padx=(10, 0))
        titulo = tk.Label(textos, text=nombre, bg=c["panel2"], fg=c["texto"], font=fuente(11, "bold"), anchor="w")
        titulo.pack(anchor="w")
        sub = tk.Label(textos, text="● Conectada", bg=c["panel2"], fg=c["verde"], font=fuente(9), anchor="w")
        sub.pack(anchor="w")
        self._filas[nombre] = {"carta": carta, "sub": sub}
        self._enlazar(carta, nombre)
        if self._elegida == nombre:
            self._pintar(nombre, True)

    def quitar(self, nombre):
        fila = self._filas.pop(nombre, None)
        if not fila:
            return
        fila["carta"].destroy()
        if self._elegida == nombre:
            self._elegida = None
        if not self._filas:
            self._vacio.pack(pady=28)

    def seleccionar(self, nombre):
        if nombre not in self._filas:
            return
        anterior = self._elegida
        self._elegida = nombre
        if anterior in self._filas:
            self._pintar(anterior, False)
        self._pintar(nombre, True)
        if self.al_elegir:
            self.al_elegir(nombre)

    def estado(self, nombre, texto, color=None):
        fila = self._filas.get(nombre)
        if fila:
            fila["sub"].configure(text=texto, fg=color or COLORES["verde"])

    # --- interno
    def _pintar(self, nombre, elegida):
        c = COLORES
        fila = self._filas.get(nombre)
        if fila:
            fila["carta"].pintar(c["panel2"], c["acento"] if elegida else c["panel2"], 2 if elegida else 1)

    def _enlazar(self, widget, nombre):
        widget.bind("<Button-1>", lambda e, n=nombre: self.seleccionar(n), add="+")
        widget.configure(cursor="hand2")
        self._enlazar_rueda(widget)
        for hijo in widget.winfo_children():
            self._enlazar(hijo, nombre)