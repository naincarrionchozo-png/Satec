"""Punto de integración: ejecuta todo el diagnóstico y devuelve un único diccionario.

El Practicante 3 (motor de reglas / base de datos) puede importar `ejecutar_diagnostico`
y pasar su resultado a las reglas y a SQLite sin conocer los detalles internos.
"""
from .interfaces import obtener_interfaces, obtener_puerta_enlace
from .puertos import obtener_puertos_escucha
from .registro import registrar
from .util import ahora


def ejecutar_diagnostico(guardar_log=True):
    resultados = {
        "modulo": "diagnostico_red",
        "fecha": ahora(),
        "interfaces": obtener_interfaces(),
        "puerta_enlace": obtener_puerta_enlace(),
        "puertos_escucha": obtener_puertos_escucha(),
    }
    # log_guardado: True/False si se intentó registrar; None si guardar_log=False
    resultados["log_guardado"] = None
    if guardar_log:
        guardados = [registrar(clave, resultados[clave])
                     for clave in ("interfaces", "puerta_enlace", "puertos_escucha")]
        resultados["log_guardado"] = all(guardados)
    return resultados
