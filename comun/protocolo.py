"""Protocolo común: cómo se mandan los mensajes entre el servidor y los agentes.

Cada mensaje tiene 3 partes:
  1. Dos números (8 bytes) con el tamaño de la cabecera y el del contenido binario.
  2. Una cabecera en JSON:  {"tipo": "...", "datos": {...}}
  3. Contenido binario opcional (imágenes, archivos).
"""
import json
import struct
import threading

PUERTO = 5000
TOKEN = "100424"  # debe ser IGUAL en servidor y agentes

MAX_CABECERA = 1024 * 1024        # 1 MB
MAX_BINARIO = 200 * 1024 * 1024   # 200 MB


class Conexion:
    """Envuelve un socket para enviar y recibir mensajes completos."""

    def __init__(self, sock):
        self.sock = sock
        self._candado = threading.Lock()  # evita que dos hilos mezclen mensajes

    def enviar(self, tipo, datos=None, binario=b""):
        cabecera = json.dumps({"tipo": tipo, "datos": datos or {}}).encode("utf-8")
        paquete = struct.pack("!II", len(cabecera), len(binario)) + cabecera + binario
        with self._candado:
            self.sock.sendall(paquete)

    def _leer(self, cantidad):
        partes = []
        while cantidad > 0:
            trozo = self.sock.recv(min(cantidad, 65536))
            if not trozo:
                raise ConnectionError("conexión cerrada")
            partes.append(trozo)
            cantidad -= len(trozo)
        return b"".join(partes)

    def recibir(self):
        """Devuelve (tipo, datos, binario) o None si la conexión se cerró."""
        try:
            tam_cab, tam_bin = struct.unpack("!II", self._leer(8))
            if tam_cab > MAX_CABECERA or tam_bin > MAX_BINARIO:
                raise ConnectionError("mensaje demasiado grande")
            cab = json.loads(self._leer(tam_cab).decode("utf-8"))
            binario = self._leer(tam_bin) if tam_bin else b""
            return cab["tipo"], cab.get("datos", {}), binario
        except (OSError, ValueError, KeyError):
            return None

    def cerrar(self):
        try:
            self.sock.close()
        except OSError:
            pass