"""Llamadas de voz y video (las usan el servidor y el agente).

Audio:  micrófono -> paquetes de 32 ms -> red -> bocinas   (librería sounddevice)
Video:  cámara -> fotos JPEG pequeñas, ~12 por segundo -> red -> ventana (librería opencv)

Recomendación: usar audífonos, si no el micrófono capta las bocinas y hay eco.
"""
import io
import queue
import threading
import time
import tkinter as tk

from PIL import Image, ImageTk

TASA = 16000   # muestras de audio por segundo
BLOQUE = 512   # muestras por paquete (32 ms)


class Llamada:
    def __init__(self, al_error):
        self.al_error = al_error          # función que recibe un texto con el error
        self.activa = threading.Event()
        self.cola_audio = queue.Queue(maxsize=30)

    def iniciar(self, con_video, enviar):
        """`enviar` es la función enviar(tipo, datos=None, binario=b'') de la conexión."""
        self.cola_audio = queue.Queue(maxsize=30)
        self.activa.set()
        threading.Thread(target=self._mandar_audio, args=(enviar,), daemon=True).start()
        threading.Thread(target=self._reproducir, daemon=True).start()
        if con_video:
            threading.Thread(target=self._mandar_video, args=(enviar,), daemon=True).start()

    def detener(self):
        self.activa.clear()

    def recibir_audio(self, datos):
        if not self.activa.is_set():
            return
        try:
            self.cola_audio.put_nowait(datos)
        except queue.Full:  # si nos atrasamos, tiramos el paquete más viejo
            try:
                self.cola_audio.get_nowait()
                self.cola_audio.put_nowait(datos)
            except (queue.Empty, queue.Full):
                pass

    def _mandar_audio(self, enviar):
        try:
            import sounddevice as sd

            with sd.RawInputStream(samplerate=TASA, channels=1, dtype="int16", blocksize=BLOQUE) as entrada:
                while self.activa.is_set():
                    datos, _ = entrada.read(BLOQUE)
                    enviar("audio", binario=bytes(datos))
        except Exception as e:
            self.al_error(f"micrófono: {e}")

    def _reproducir(self):
        try:
            import sounddevice as sd

            with sd.RawOutputStream(samplerate=TASA, channels=1, dtype="int16", blocksize=BLOQUE) as salida:
                while self.activa.is_set():
                    try:
                        datos = self.cola_audio.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    salida.write(datos)
        except Exception as e:
            self.al_error(f"bocinas: {e}")

    def _mandar_video(self, enviar):
        camara = None
        try:
            import cv2

            camara = cv2.VideoCapture(0)
            if not camara.isOpened():
                self.al_error("no se pudo abrir la cámara")
                return
            while self.activa.is_set():
                ok, cuadro = camara.read()
                if ok:
                    cuadro = cv2.resize(cuadro, (320, 240))
                    ok, jpg = cv2.imencode(".jpg", cuadro, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    if ok:
                        enviar("video", binario=jpg.tobytes())
                time.sleep(0.08)
        except Exception as e:
            self.al_error(f"cámara: {e}")
        finally:
            if camara is not None:
                camara.release()


class VentanaLlamada:
    """Ventanita que muestra el video de la otra persona y el botón Colgar."""

    def __init__(self, raiz, titulo, con_video, al_colgar):
        self.ventana = tk.Toplevel(raiz)
        self.ventana.title(titulo)
        self.ventana.protocol("WM_DELETE_WINDOW", al_colgar)
        texto = "Esperando video..." if con_video else "Llamada de voz en curso"
        self.etiqueta = tk.Label(self.ventana, text=texto, padx=60, pady=40)
        self.etiqueta.pack(padx=6, pady=6)
        tk.Button(self.ventana, text="Colgar", command=al_colgar).pack(pady=6)
        self.foto = None

    def mostrar(self, jpeg):
        imagen = Image.open(io.BytesIO(jpeg))
        self.foto = ImageTk.PhotoImage(imagen)
        self.etiqueta.config(image=self.foto, text="", padx=0, pady=0)

    def cerrar(self):
        try:
            self.ventana.destroy()
        except tk.TclError:
            pass
