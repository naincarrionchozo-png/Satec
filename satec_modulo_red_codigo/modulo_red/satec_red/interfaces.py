"""Requisitos 1, 2, 3: interfaces, IPv4/máscara y puerta de enlace."""
import ipaddress
import json
import socket
import struct

from .util import ejecutar, resultado

RUTA_PROC_ROUTE = "/proc/net/route"


def parsear_ip_json(texto):
    """Convierte la salida de `ip -j -4 addr show` en una lista de interfaces."""
    interfaces = []
    for item in json.loads(texto):
        direcciones = []
        for a in item.get("addr_info", []):
            if a.get("family") != "inet":
                continue
            mascara = str(ipaddress.IPv4Network(f"0.0.0.0/{a['prefixlen']}").netmask)
            direcciones.append({"ip": a["local"], "prefijo": a["prefixlen"],
                                "mascara": mascara})
        interfaces.append({"nombre": item.get("ifname", "?"),
                           "estado": item.get("operstate", "DESCONOCIDO"),
                           "ipv4": direcciones})
    return interfaces


def obtener_interfaces():
    """Lista interfaces con sus direcciones IPv4 y máscaras."""
    codigo, salida = ejecutar(["ip", "-j", "-4", "addr", "show"])
    if codigo == 0 and salida.strip():
        try:
            return resultado("ok", parsear_ip_json(salida))
        except (ValueError, KeyError) as e:
            return resultado("error", [], f"No se pudo interpretar la salida de 'ip': {e}")
    # Alternativa: solo nombres de interfaz (sin IP) usando la biblioteca estándar
    try:
        datos = [{"nombre": n, "estado": "DESCONOCIDO", "ipv4": []}
                 for _, n in socket.if_nameindex()]
        return resultado("no_disponible", datos,
                         "Comando 'ip' no disponible; solo se listan nombres de interfaz.")
    except OSError as e:
        return resultado("no_disponible", [], f"No se pudo obtener interfaces: {e}")


def parsear_ruta_defecto(texto):
    """Extrae la puerta de enlace predeterminada del contenido de /proc/net/route."""
    for linea in texto.splitlines()[1:]:
        c = linea.split()
        if len(c) < 8:
            continue
        iface, destino, gw, flags = c[0], c[1], c[2], int(c[3], 16)
        if destino == "00000000" and flags & 0x2:  # RTF_GATEWAY
            ip = socket.inet_ntoa(struct.pack("<L", int(gw, 16)))
            return {"interfaz": iface, "puerta_enlace": ip}
    return None


def obtener_puerta_enlace():
    """Puerta de enlace predeterminada, 'cuando exista'."""
    try:
        with open(RUTA_PROC_ROUTE, encoding="ascii") as f:
            ruta = parsear_ruta_defecto(f.read())
    except OSError as e:
        return resultado("no_disponible", [], f"No se pudo leer {RUTA_PROC_ROUTE}: {e}")
    if ruta is None:
        return resultado("ok", [], "No existe puerta de enlace predeterminada.")
    return resultado("ok", [ruta])
