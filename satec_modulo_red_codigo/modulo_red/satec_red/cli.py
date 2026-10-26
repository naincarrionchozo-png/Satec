"""Interfaz de línea de comandos del Módulo 1 (presentación; no contiene lógica de red)."""
import argparse
import json
import os
import sys

from . import conectividad
from .diagnostico import ejecutar_diagnostico
from .interfaces import obtener_interfaces, obtener_puerta_enlace
from .puertos import obtener_puertos_escucha
from .registro import registrar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_AUTORIZADOS = os.path.join(RAIZ, "config", "equipos_autorizados.txt")


def _aviso(res):
    if res["mensaje"]:
        print(f"  [!] {res['mensaje']}")


def mostrar_interfaces():
    res = obtener_interfaces()
    print("\n=== INTERFACES DE RED ===")
    _aviso(res)
    for i in res["datos"]:
        print(f"- {i['nombre']} (estado: {i['estado']})")
        for a in i["ipv4"]:
            print(f"    IPv4: {a['ip']}/{a['prefijo']}  máscara: {a['mascara']}")
        if not i["ipv4"]:
            print("    (sin dirección IPv4)")
    registrar("interfaces", res)


def mostrar_puerta_enlace():
    res = obtener_puerta_enlace()
    print("\n=== PUERTA DE ENLACE PREDETERMINADA ===")
    _aviso(res)
    for g in res["datos"]:
        print(f"- {g['puerta_enlace']} (interfaz {g['interfaz']})")
    registrar("puerta_enlace", res)


def mostrar_puertos():
    res = obtener_puertos_escucha()
    print("\n=== PUERTOS TCP EN ESCUCHA ===")
    _aviso(res)
    if not res["datos"]:
        print("  No se detectaron puertos en escucha.")
    else:
        print(f"{'PUERTO':<8}{'PROTO':<7}{'DIRECCIÓN':<18}{'EXPOSICIÓN':<12}"
              f"{'SERVICIO':<12}PROCESO (PID)")
        for s in res["datos"]:
            pid = f"{s['proceso']} ({s['pid']})" if s["pid"] else s["proceso"]
            print(f"{s['puerto']:<8}{s['protocolo']:<7}{s['direccion']:<18}"
                  f"{s['exposicion']:<12}{s['servicio']:<12}{pid}")
    registrar("puertos_escucha", res)


def _cargar_redes():
    try:
        redes = conectividad.cargar_autorizados(RUTA_AUTORIZADOS)
    except OSError:
        print(f"  [!] No se encontró {RUTA_AUTORIZADOS}. Cree la lista de equipos autorizados.")
        return None
    except ValueError as e:
        print(f"  [!] {e}")
        return None
    if not redes:
        print("  [!] La lista de equipos autorizados está vacía.")
        return None
    return redes


def probar_conectividad():
    print("\n=== CONECTIVIDAD CON EQUIPO AUTORIZADO ===")
    redes = _cargar_redes()
    if redes is None:
        return
    ip = input("IP del equipo de laboratorio (ej. 192.168.56.10): ")
    res = conectividad.probar_ping(ip, redes)
    _aviso(res)
    for d in res["datos"]:
        estado = "ALCANZABLE" if d["alcanzable"] else "SIN RESPUESTA"
        print(f"- {d['destino']}: {estado}\n  {d['resumen']}")
    registrar(f"ping {ip.strip()}", res)


def diagnostico_completo():
    mostrar_interfaces()
    mostrar_puerta_enlace()
    mostrar_puertos()


def exportar_json():
    datos = ejecutar_diagnostico(guardar_log=True)
    print(json.dumps(datos, indent=2, ensure_ascii=False))


MENU = {"1": ("Ver interfaces, IPv4 y máscaras", mostrar_interfaces),
        "2": ("Ver puerta de enlace predeterminada", mostrar_puerta_enlace),
        "3": ("Ver puertos TCP en escucha y procesos", mostrar_puertos),
        "4": ("Probar conectividad con equipo autorizado", probar_conectividad),
        "5": ("Diagnóstico completo (1 + 2 + 3)", diagnostico_completo)}


def menu():
    while True:
        print("\n--- SATEC · Diagnóstico de red y servicios ---")
        for k, (texto, _) in MENU.items():
            print(f"{k}. {texto}")
        print("0. Salir")
        op = input("Seleccione una opción: ").strip()
        if op == "0":
            print("Hasta luego.")
            return
        if op in MENU:
            try:
                MENU[op][1]()
            except (KeyboardInterrupt, EOFError):
                print("\nOperación cancelada.")
            except Exception as e:  # el menú nunca debe cerrarse por un error inesperado
                print(f"  [!] Error inesperado: {e}")
        else:
            print("  [!] Opción inválida. Ingrese un número del menú.")


def main(argv=None):
    p = argparse.ArgumentParser(description="SATEC - Módulo 1: diagnóstico de red (solo lectura)")
    p.add_argument("--json", action="store_true",
                   help="ejecuta el diagnóstico completo y lo imprime en JSON")
    args = p.parse_args(argv)
    if args.json:
        exportar_json()
    else:
        menu()
    return 0


if __name__ == "__main__":
    sys.exit(main())
