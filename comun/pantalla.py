"""Captura de pantalla (la usan tanto el servidor como el agente)."""
import io


def capturar_jpeg(calidad=50):
    import mss
    from PIL import Image

    # Las versiones nuevas de mss usan MSS; las viejas, mss.mss
    clase = getattr(mss, "MSS", None) or mss.mss
    with clase() as sct:
        foto = sct.grab(sct.monitors[1])
        imagen = Image.frombytes("RGB", foto.size, foto.bgra, "raw", "BGRX")
    imagen.thumbnail((1280, 720))
    buffer = io.BytesIO()
    imagen.save(buffer, "JPEG", quality=calidad)
    return buffer.getvalue()
