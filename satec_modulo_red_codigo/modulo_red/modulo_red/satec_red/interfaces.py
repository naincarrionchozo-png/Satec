"""Requisitos 1, 2, 3: interfaces, IPv4/máscara y puerta de enlace."""
import ipaddress
import json
import socket
import struct

from .util import ES_WINDOWS, ejecutar, resultado

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


def _interfaces_linux():
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


def _puerta_enlace_linux():
    """Puerta de enlace predeterminada, 'cuando exista'."""
    try:
        with open(RUTA_PROC_ROUTE, encoding="ascii") as f:
            ruta = parsear_ruta_defecto(f.read())
    except OSError as e:
        return resultado("no_disponible", [], f"No se pudo leer {RUTA_PROC_ROUTE}: {e}")
    if ruta is None:
        return resultado("ok", [], "No existe puerta de enlace predeterminada.")
    return resultado("ok", [ruta])


# ----------------------------- Windows (PowerShell) -----------------------------
def _lista(valor):
    """PowerShell devuelve un dict si hay un solo elemento y una lista si hay varios."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _powershell(comando, timeout=15):
    return ejecutar(["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
                    timeout=timeout)


def parsear_interfaces_windows(texto):
    """Interpreta el JSON {adaptadores:[{Name,Status}], ips:[{InterfaceAlias,IPAddress,PrefixLength}]}."""
    datos = json.loads(texto)
    estados = {a.get("Name"): str(a.get("Status", "")).upper()
               for a in _lista(datos.get("adaptadores"))}
    por_nombre = {n: [] for n in estados}
    for ip in _lista(datos.get("ips")):
        pref = int(ip["PrefixLength"])
        mascara = str(ipaddress.IPv4Network(f"0.0.0.0/{pref}").netmask)
        por_nombre.setdefault(ip["InterfaceAlias"], []).append(
            {"ip": ip["IPAddress"], "prefijo": pref, "mascara": mascara})
    return [{"nombre": n, "estado": estados.get(n, "UP"), "ipv4": ips}
            for n, ips in por_nombre.items()]


def parsear_gateway_windows(texto):
    """Interpreta el JSON de Get-NetRoute; NextHop 0.0.0.0 significa 'sin puerta de enlace'."""
    if not texto.strip():
        return None
    for ruta in _lista(json.loads(texto)):
        if ruta.get("NextHop") not in (None, "", "0.0.0.0"):
            return {"interfaz": ruta.get("InterfaceAlias", "?"), "puerta_enlace": ruta["NextHop"]}
    return None


def _interfaces_windows():
    cmd = ("$a=Get-NetAdapter | Select-Object Name,Status; "
           "$i=Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress,PrefixLength; "
           "@{adaptadores=@($a); ips=@($i)} | ConvertTo-Json -Depth 3")
    codigo, salida = _powershell(cmd)
    if codigo != 0 or not salida.strip():
        return resultado("no_disponible", [], "No se pudo ejecutar PowerShell (Get-NetIPAddress).")
    try:
        return resultado("ok", parsear_interfaces_windows(salida))
    except (ValueError, KeyError, TypeError) as e:
        return resultado("error", [], f"No se pudo interpretar la salida de PowerShell: {e}")


def _puerta_enlace_windows():
    cmd = ("Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | "
           "Select-Object InterfaceAlias,NextHop | ConvertTo-Json")
    codigo, salida = _powershell(cmd)
    if codigo != 0:
        return resultado("no_disponible", [], "No se pudo consultar la tabla de rutas.")
    try:
        ruta = parsear_gateway_windows(salida)
    except (ValueError, TypeError) as e:
        return resultado("error", [], f"No se pudo interpretar la salida de PowerShell: {e}")
    if ruta is None:
        return resultado("ok", [], "No existe puerta de enlace predeterminada.")
    return resultado("ok", [ruta])


def obtener_interfaces():
    return _interfaces_windows() if ES_WINDOWS else _interfaces_linux()


def obtener_puerta_enlace():
    return _puerta_enlace_windows() if ES_WINDOWS else _puerta_enlace_linux()
