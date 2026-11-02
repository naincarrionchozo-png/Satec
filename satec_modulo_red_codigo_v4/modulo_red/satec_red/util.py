"""Utilidades comunes: ejecución segura de comandos y marcas de tiempo."""
import subprocess
import sys
from datetime import datetime

# Códigos propios de ejecutar() (distintos de cualquier código de salida real)
NO_EXISTE = -1   # el programa no existe o no hay permisos para ejecutarlo
TIMEOUT = -2     # el programa no terminó dentro del tiempo permitido


def ahora():
    """Fecha y hora local en formato ISO 8601 con zona horaria."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ejecutar(comando, timeout=5):
    """Ejecuta un comando SIN shell (lista de argumentos) y devuelve (codigo, salida).

    Devuelve (NO_EXISTE, "") si el programa no existe o no hay permisos, y
    (TIMEOUT, "") si expira el tiempo. Así el llamador puede distinguir ambos casos.
    Nunca se construye el comando concatenando texto del usuario con un shell.
    """
    try:
        r = subprocess.run(comando, capture_output=True, text=True, errors="replace",
                           timeout=timeout, check=False)
        return r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        return TIMEOUT, ""
    except OSError:  # FileNotFoundError, PermissionError, etc.
        return NO_EXISTE, ""


ES_WINDOWS = sys.platform.startswith("win")


def resultado(estado, datos=None, mensaje=""):
    """Estructura uniforme que el Módulo 4 (motor de reglas) puede consumir.

    estado: 'ok' | 'no_disponible' | 'error'
    """
    return {"estado": estado, "mensaje": mensaje, "fecha": ahora(),
            "datos": datos if datos is not None else []}
