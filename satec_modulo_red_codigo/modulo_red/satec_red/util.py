"""Utilidades comunes: ejecución segura de comandos y marcas de tiempo."""
import subprocess
from datetime import datetime


def ahora():
    """Fecha y hora local en formato ISO 8601 con zona horaria."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ejecutar(comando, timeout=5):
    """Ejecuta un comando SIN shell (lista de argumentos) y devuelve (codigo, salida).

    Devuelve (-1, "") si el programa no existe, no hay permisos o expira el tiempo.
    Nunca se construye el comando concatenando texto del usuario con un shell.
    """
    try:
        r = subprocess.run(comando, capture_output=True, text=True,
                           timeout=timeout, check=False)
        return r.returncode, r.stdout
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
        return -1, ""


def resultado(estado, datos=None, mensaje=""):
    """Estructura uniforme que el Módulo 4 (motor de reglas) puede consumir.

    estado: 'ok' | 'no_disponible' | 'error'
    """
    return {"estado": estado, "mensaje": mensaje, "fecha": ahora(),
            "datos": datos if datos is not None else []}
