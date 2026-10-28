"""Requisito 7: registrar los resultados con fecha y hora (JSON Lines)."""
import json
import os

from .util import ahora

RUTA_LOG_DEFECTO = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "logs", "diagnostico_red.jsonl")


def registrar(evento, resultado_modulo, ruta=RUTA_LOG_DEFECTO):
    """Agrega una línea JSON al registro. Devuelve True si se pudo escribir."""
    linea = {"fecha": ahora(), "evento": evento, "estado": resultado_modulo.get("estado"),
             "mensaje": resultado_modulo.get("mensaje", ""),
             "datos": resultado_modulo.get("datos")}
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False
