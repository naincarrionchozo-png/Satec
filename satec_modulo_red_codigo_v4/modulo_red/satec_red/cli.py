"""Interfaz de línea de comandos del Módulo 1 (presentación; no contiene lógica de red)."""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from . import conectividad
from .diagnostico import ejecutar_diagnostico
from .interfaces import obtener_interfaces, obtener_puerta_enlace
from .puertos import obtener_puertos_escucha
from .registro import registrar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_AUTORIZADOS = os.path.join(RAIZ, "config", "equipos_autorizados.txt")
_log_avisado = False


def _registrar(evento, res):
    """Registra el resultado y avisa (una vez) si no se pudo escribir el log."""
    global _log_avisado
    if not registrar(evento, res) and not _log_avisado:
        print("  [!] No se pudo escribir el registro (logs/diagnostico_red.jsonl). "
              "Revise los permisos de la carpeta logs/.")
        _log_avisado = True


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
    _registrar("interfaces", res)


def mostrar_puerta_enlace():
    res = obtener_puerta_enlace()
    print("\n=== PUERTA DE ENLACE PREDETERMINADA ===")
    _aviso(res)
    for g in res["datos"]:
        print(f"- {g['puerta_enlace']} (interfaz {g['interfaz']})")
    _registrar("puerta_enlace", res)


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
    _registrar("puertos_escucha", res)


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
    _registrar(f"ping {ip.strip()}", res)


def listar_autorizados():
    print("\n=== EQUIPOS AUTORIZADOS ===")
    redes = _cargar_redes()
    if redes is None:
        return
    for r in redes:
        print(f"- {r}")


def _ping_rapido(ip, redes):
    return conectividad.probar_ping(str(ip), redes, intentos=1, espera=1)


def agregar_y_analizar():
    """Pide la IP o el rango de IP a analizar, lo autoriza (con confirmación) y lo analiza."""
    print("\n=== AGREGAR IP O RANGO DE IP A ANALIZAR ===")
    print("  Solo redes privadas de su laboratorio, con permiso. Formatos:")
    print("    IP única:  192.168.56.102")
    print("    Rango:     192.168.56.100-110   o   192.168.56.100-192.168.56.110")
    print("    Red CIDR:  192.168.56.96/27")
    print(f"  Máximo {conectividad.MAX_AUTORIZADOS} equipos por análisis.")
    texto = input("IP o rango de IP a analizar: ").strip()
    try:
        ips = conectividad.parsear_objetivo(texto)
    except ValueError as e:
        print(f"  [!] {e}")
        return
    try:
        redes = conectividad.cargar_autorizados(RUTA_AUTORIZADOS)
    except FileNotFoundError:
        redes = []
    except ValueError as e:
        print(f"  [!] {e}")
        return

    nuevas = [ip for ip in ips if not conectividad.esta_autorizada(ip, redes)]
    print(f"  Equipos a analizar: {len(ips)} ({len(nuevas)} aún no autorizados).")
    if nuevas:
        resp = input(f"Confirme que tiene autorización escribiendo de nuevo «{texto}»: ").strip()
        if resp != texto:
            print("  Cancelado: la confirmación no coincide; nada fue agregado.")
            return
        try:
            for ip in nuevas:
                conectividad.agregar_autorizado(RUTA_AUTORIZADOS, ip)
        except (OSError, ValueError) as e:
            print(f"  [!] No se pudo guardar la lista: {e}")
            return
        _registrar("autorizacion", {"estado": "ok", "mensaje": f"Autorizado: {texto}",
                                    "datos": [str(ip) for ip in nuevas]})
        print(f"  {len(nuevas)} equipo(s) agregado(s) a la lista de autorizados.")
        redes = conectividad.cargar_autorizados(RUTA_AUTORIZADOS)

    print("\n--- Análisis ---")
    if len(ips) == 1:
        resultados = [(ips[0], conectividad.probar_ping(str(ips[0]), redes))]
    else:
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(zip(ips, pool.map(lambda i: _ping_rapido(i, redes), ips)))
    vivos = []
    for ip, res in resultados:
        _aviso(res)
        for d in res["datos"]:
            if d["alcanzable"]:
                vivos.append(ip)
            print(f"- Ping a {d['destino']}: {'ALCANZABLE' if d['alcanzable'] else 'SIN RESPUESTA'}")
            if len(ips) == 1 and d["resumen"]:
                print(f"  {d['resumen']}")
        _registrar(f"analisis ping {ip}", res)
    if len(ips) > 1:
        print(f"  Resumen: {len(vivos)} de {len(ips)} equipos respondieron.")

    try:
        puertos = conectividad.validar_puertos(
            input("Puertos TCP a comprobar, separados por coma (Enter para omitir, máx. 5): "))
    except ValueError as e:
        print(f"  [!] {e}")
        return
    objetivos = ips if len(ips) == 1 else vivos
    if puertos and len(ips) > 1:
        print(f"  Se comprobarán solo los {len(vivos)} equipos que respondieron al ping.")
    for ip in objetivos:
        for pto in puertos:
            r = conectividad.probar_tcp(str(ip), pto, redes)
            _aviso(r)
            for d in r["datos"]:
                print(f"- {ip}:{d['puerto']}: {'ABIERTO' if d['abierto'] else 'cerrado o filtrado'}")
            _registrar(f"analisis tcp {ip}:{pto}", r)


def diagnostico_completo():
    mostrar_interfaces()
    mostrar_puerta_enlace()
    mostrar_puertos()


def exportar_json():
    datos = ejecutar_diagnostico(guardar_log=True)
    print(json.dumps(datos, indent=2, ensure_ascii=False))


MENU = {"1": ("Agregar IP o rango de IP a analizar", agregar_y_analizar),
        "2": ("Ver interfaces, IPv4 y máscaras", mostrar_interfaces),
        "3": ("Ver puerta de enlace predeterminada", mostrar_puerta_enlace),
        "4": ("Ver puertos TCP en escucha y procesos", mostrar_puertos),
        "5": ("Probar conectividad con equipo autorizado", probar_conectividad),
        "6": ("Diagnóstico completo (2 + 3 + 4)", diagnostico_completo),
        "7": ("Ver equipos autorizados", listar_autorizados)}


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
