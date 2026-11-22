"""Tema oscuro (colores, fuentes y estilos) compartido por el servidor y el agente."""
import tkinter as tk
from tkinter import ttk

COLORES = {
    "fondo": "#1e1e2e",
    "panel": "#2a2b3c",
    "panel2": "#33344a",
    "borde": "#45475a",
    "texto": "#cdd6f4",
    "suave": "#9399b2",
    "acento": "#cba6f7",
    "acento2": "#b4befe",
    "verde": "#a6e3a1",
    "rojo": "#f38ba8",
    "rojo2": "#eba0ac",
    "amarillo": "#f9e2af",
}

FUENTE = ("Sans", 10)
FUENTE_TITULO = ("Sans", 16, "bold")
FUENTE_SECCION = ("Sans", 11, "bold")


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
    """Aplica el tema a toda la aplicación. Se llama una vez, justo después de crear la ventana."""
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
    e.configure("Tarjeta.TLabelframe.Label", background=c["panel"], foreground=c["acento2"], font=FUENTE_SECCION)

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
    _boton(e, "Acento.TButton", c["acento"], c["acento2"], c["fondo"])
    _boton(e, "Peligro.TButton", c["rojo"], c["rojo2"], c["fondo"])

    # cajas de texto y barras de desplazamiento
    e.configure(
        "TEntry", fieldbackground=c["panel2"], foreground=c["texto"], insertcolor=c["texto"],
        bordercolor=c["borde"], lightcolor=c["panel2"], darkcolor=c["panel2"], padding=8,
    )
    e.map("TEntry", bordercolor=[("focus", c["acento"])])
    e.configure(
        "Vertical.TScrollbar", background=c["panel2"], troughcolor=c["panel"],
        bordercolor=c["panel"], arrowcolor=c["texto"], lightcolor=c["panel2"], darkcolor=c["panel2"],
    )


# ---------- ayudas para armar ventanas ----------
def estilo_lista(lista):
    c = COLORES
    lista.configure(
        bg=c["panel2"], fg=c["texto"], selectbackground=c["acento"], selectforeground=c["fondo"],
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
    texto.configure(yscrollcommand=barra.set)
    barra.pack(side="right", fill="y")
    texto.pack(side="left", fill="both", expand=True)
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
