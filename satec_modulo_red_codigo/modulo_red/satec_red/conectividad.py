"""Requisito 6: comprobar conectividad SOLO con direcciones IP autorizadas."""
import ipaddress
import socket

from .util import ejecutar, resultado


class NoAutorizadoError(Exception):
    """Se intentó probar un destino que no está en la lista de autorizados."""


def validar_ipv4(texto):
    """Valida y normaliza una dirección IPv4. Lanza ValueError si es inválida."""
    texto = (texto or "").strip()
    try:
        return ipaddress.IPv4Address(texto)
    except ipaddress.AddressValueError:
        raise ValueError(f"'{texto}' no es una dirección IPv4 válida.") from None


def cargar_autorizados(ruta):
    """Lee la lista blanca (una IP o red CIDR por línea; # = comentario)."""
    redes = []
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.split("#", 1)[0].strip()
            if not linea:
                continue
            try:
                redes.append(ipaddress.IPv4Network(linea, strict=False))
            except ValueError:
                raise ValueError(f"Línea {n} inválida en {ruta}: '{linea}'") from None
    return redes


def esta_autorizada(ip, redes):
    return any(ip in red for red in redes)


def _verificar(ip_texto, redes):
    ip = validar_ipv4(ip_texto)
    if not esta_autorizada(ip, redes):
        raise NoAutorizadoError(
            f"{ip} no figura en la lista de equipos autorizados del laboratorio.")
    return ip


def probar_ping(ip_texto, redes, intentos=2, espera=2):
    """Envía ICMP echo (comando ping del sistema) a un equipo autorizado."""
    try:
        ip = _verificar(ip_texto, redes)
    except (ValueError, NoAutorizadoError) as e:
        return resultado("error", [], str(e))
    codigo, salida = ejecutar(["ping", "-c", str(intentos), "-W", str(espera), str(ip)],
                              timeout=intentos * (espera + 1) + 2)
    if codigo == -1:
        return resultado("no_disponible", [], "El comando 'ping' no está disponible.")
    linea_resumen = next((l for l in salida.splitlines() if "packets transmitted" in l), "")
    return resultado("ok", [{"destino": str(ip), "alcanzable": codigo == 0,
                             "resumen": linea_resumen}])


def probar_tcp(ip_texto, puerto, redes, espera=2.0):
    """Intenta conectar a un puerto TCP de un equipo autorizado (sin enviar datos)."""
    try:
        ip = _verificar(ip_texto, redes)
        if not (1 <= int(puerto) <= 65535):
            raise ValueError("El puerto debe estar entre 1 y 65535.")
    except (ValueError, NoAutorizadoError) as e:
        return resultado("error", [], str(e))
    try:
        with socket.create_connection((str(ip), int(puerto)), timeout=espera):
            abierto = True
    except (ConnectionRefusedError, socket.timeout, OSError):
        abierto = False
    return resultado("ok", [{"destino": str(ip), "puerto": int(puerto), "abierto": abierto}])
