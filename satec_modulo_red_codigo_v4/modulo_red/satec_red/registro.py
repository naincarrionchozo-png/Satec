"""Requisito 7: registrar los resultados con fecha y hora (JSON Lines)."""
import json
import os

from .util import ahora

RUTA_LOG_DEFECTO = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "logs", "diagnostico_red.jsonl")


def _ajustar_propietario(ruta):
    """Si el programa corre con sudo, deja el archivo a nombre del usuario real.

    Evita que logs/ quede como root y que las ejecuciones normales posteriores
    dejen de poder registrar.
    """
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    try:
        uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
        os.chown(ruta, uid, gid)
    except (KeyError, ValueError, OSError):
        pass


def registrar(evento, resultado_modulo, ruta=RUTA_LOG_DEFECTO):
    """Agrega una línea JSON al registro. Devuelve True si se pudo escribir."""
    linea = {"fecha": ahora(), "evento": evento, "estado": resultado_modulo.get("estado"),
             "mensaje": resultado_modulo.get("mensaje", ""),
             "datos": resultado_modulo.get("datos")}
    try:
        carpeta = os.path.dirname(ruta)
        os.makedirs(carpeta, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
        _ajustar_propietario(carpeta)
        _ajustar_propietario(ruta)
        return True
    except OSError:
        return False
