<div align="center">

# 🖥️ AplicacionMonitoreo

**Monitoreo y control remoto de equipos en red local, hecho en Python.**
Un servidor central administra uno o varios clientes (agentes) con chat, llamadas, transferencia de archivos, vista de pantalla y órdenes de administración.

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/UI-Tkinter-1f6feb)
![Linux](https://img.shields.io/badge/Linux-only-FCC624?logo=linux&logoColor=black)
![nftables](https://img.shields.io/badge/Firewall-nftables-orange)

</div>

---

## ✨ Características

| Función | Descripción |
| --- | --- |
| 💬 **Chat** | Mensajería en tiempo real entre servidor y clientes. |
| 📞 **Llamadas** | Llamadas de audio y videollamadas entre servidor y cliente. |
| 📁 **Transferencia de archivos** | Envío de archivos en ambas direcciones (se guardan en `recibidos_servidor/` y `recibidos_agente/`). |
| 🖼️ **Vista de pantalla** | El servidor puede ver la pantalla del cliente, y el cliente la del servidor. |
| ⌨️ **Bloqueo de teclado y mouse** | Toma control exclusivo de los dispositivos de entrada (funciona en X11 y Wayland). Se desbloquea solo tras un tiempo máximo de seguridad (120 s). |
| 🌐 **Bloqueo de páginas web** | Agrega y quita sitios bloqueados editando `/etc/hosts` (IPv4 e IPv6, con y sin `www.`). |
| 📡 **Bloqueo de ping** | Impide que el cliente **envíe** pings (ICMP echo-request) con una regla de nftables. El servidor sí puede seguir haciendo ping al cliente. |
| ⏻ **Apagado remoto** | Apaga el equipo cliente con `systemctl poweroff`. |

---

## 🧩 Arquitectura

```
┌──────────────┐        órdenes / chat / archivos / video        ┌──────────────┐
│   SERVIDOR   │ ◀─────────────────────────────────────────────▶ │  CLIENTE     │
│ servidor.py  │                 conexión TCP                    │  agente.py   │
└──────────────┘                                                 └──────┬───────┘
                                                                        │ sudo -n
                                                                 ┌──────▼───────┐
                                                                 │privilegiado  │
                                                                 │    .py       │
                                                                 └──────────────┘
```

El **agente** corre con **tu usuario normal** (así funcionan la pantalla, el micrófono y la cámara). Solo las tareas que necesitan permisos de administrador las ejecuta `privilegiado.py` mediante `sudo`. Al iniciar, el agente pide la contraseña de administrador **una sola vez** en la terminal y la mantiene vigente mientras corre.

### 📂 Estructura del proyecto

```
.
├── cliente/
│   ├── agente.py          # Agente con ventana (Tkinter): corre en cada PC controlada
│   ├── privilegiado.py    # Ayudante con permisos de administrador (se llama con sudo -n)
│   ├── diagnostico.py     # Utilidad de diagnóstico del cliente
│   └── __init__.py
├── servidor/
│   └── servidor.py        # Servidor / panel de control
├── comun/                 # Código compartido por servidor y cliente
│   ├── protocolo.py       # Conexión, puerto y token
│   ├── llamada.py         # Audio y video de las llamadas
│   ├── pantalla.py        # Captura de pantalla
│   ├── archivos.py        # Utilidades de archivos
│   └── tema.py            # Estilos de la interfaz
├── recibidos_servidor/    # Archivos que el servidor recibe de los clientes
├── diagnostico.py         # Diagnóstico general
└── requirements.txt
```

---

## ⚙️ Requisitos

- **Linux** (probado en Arch/EndeavourOS).
- **Python 3** con `tkinter`.
- **nftables** (comando `nft`) en los clientes, para el bloqueo de ping.
- **sudo** configurado para el usuario que corre el agente.
- Servidor y clientes en la **misma red local**.

> En Arch/EndeavourOS: `sudo pacman -S tk nftables`

---

## 🚀 Instalación

```bash
git clone https://github.com/LindaTars/AplicacionMonitoreo.git
cd AplicacionMonitoreo

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Repite esto en el servidor y en cada cliente.

---

## ▶️ Uso

### 1. Iniciar el servidor

```bash
python servidor/servidor.py
```

### 2. Iniciar el agente en cada cliente

```bash
python cliente/agente.py IP_DEL_SERVIDOR [nombre]
```

- `IP_DEL_SERVIDOR`: la IP del equipo donde corre el servidor. Si no la pasas, el agente la pide en una ventanita.
- `nombre` *(opcional)*: cómo aparecerá el cliente en el servidor. Por defecto usa el nombre del equipo.

Al arrancar, el agente te pedirá tu **contraseña de administrador** en la terminal. Si no la das, el agente funciona, pero las órdenes de administrador (bloqueo de teclado, ping y webs) no.

> El puerto y el token de conexión se definen en `comun/protocolo.py`. Deben ser los mismos en el servidor y en los clientes.

---

## 🔧 Cómo funcionan las órdenes de administrador

Todas pasan por `cliente/privilegiado.py`, que solo corre como root y acepta estas acciones:

```text
bloquear-webs sitio1,sitio2     # agrega los sitios a /etc/hosts
permitir-webs                   # quita el bloqueo de /etc/hosts
ping negar | permitir           # bloquea / permite que el cliente envíe pings
bloquear-entrada SEGUNDOS       # teclado y mouse (se queda corriendo hasta que el agente cierre stdin)
```

- **Webs:** las entradas se escriben entre las marcas `# >>> BLOQUEO-APP` y `# <<< BLOQUEO-APP`, así que "permitir" solo borra lo que la app agregó.
- **Ping:** crea la tabla nftables `bloqueo_app_ping` con reglas en la cadena de **salida** para ICMP e ICMPv6. "Permitir" borra esa tabla y no toca el resto de tu firewall. Las reglas viven en memoria y desaparecen al reiniciar.
- **Teclado y mouse:** usa `EVIOCGRAB` sobre `/dev/input/event*`. Si el agente se cierra o pasan 120 s, el kernel libera los dispositivos.

### Comprobar el bloqueo de ping

Desde el **cliente**, después de mandar "negar ping" desde el servidor:

```bash
sudo nft list table inet bloqueo_app_ping   # debe mostrar las reglas
ping -c 3 IP_DEL_SERVIDOR                   # debe dar 100% de pérdida
```

Con "permitir ping", la tabla desaparece y el ping vuelve a responder.

---

## 🛡️ Seguridad

- Es una herramienta pensada para **redes locales de confianza** (laboratorio, escuela, equipos propios).
- Cuida el **token** de `comun/protocolo.py`: quien lo conozca puede mandar órdenes a los agentes.
- Usa la aplicación solo en equipos que administras o con permiso de sus dueños.

---

## 🛠️ Tecnologías

Python · Tkinter · Pillow · sockets TCP · nftables · sudo · `/dev/input` (evdev)

---

## 👩‍💻 Autora

Hecho por **[LindaTars](https://github.com/LindaTars)**.
