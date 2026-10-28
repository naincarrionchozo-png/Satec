"""Requisitos 4 y 5: puertos TCP en escucha y proceso asociado (solo lectura de /proc)."""
import csv
import io
import ipaddress
import os

from .util import ES_WINDOWS, ejecutar, resultado

ESTADO_LISTEN = "0A"

# Servicios conocidos y su riesgo asociado cuando quedan expuestos (apoyo a la investigación)
SERVICIOS_CONOCIDOS = {
    21: ("FTP", "Transmite credenciales sin cifrar."),
    22: ("SSH", "Administración remota; requiere configuración segura."),
    23: ("Telnet", "Protocolo sin cifrado; debe evitarse."),
    25: ("SMTP", "Puede ser usado para reenvío no autorizado de correo."),
    53: ("DNS", "Mal configurado permite abuso o filtración de información."),
    80: ("HTTP", "Tráfico web sin cifrar."),
    110: ("POP3", "Correo sin cifrado."),
    139: ("NetBIOS", "Exposición de recursos compartidos."),
    143: ("IMAP", "Correo sin cifrado."),
    443: ("HTTPS", "Servicio web cifrado; verificar certificados."),
    445: ("SMB", "Recursos compartidos; objetivo frecuente de ataques."),
    631: ("IPP/CUPS", "Servicio de impresión; innecesario en muchos equipos."),
    3306: ("MySQL", "Base de datos; no debería exponerse a la red."),
    3389: ("RDP", "Escritorio remoto; objetivo frecuente de ataques."),
    5432: ("PostgreSQL", "Base de datos; no debería exponerse a la red."),
    5900: ("VNC", "Escritorio remoto, a menudo débilmente protegido."),
}


def _ip_hex(texto):
    """Convierte la IP hexadecimal de /proc/net/tcp(6) a texto."""
    if len(texto) == 8:  # IPv4, little-endian
        return str(ipaddress.IPv4Address(bytes.fromhex(texto)[::-1]))
    # IPv6: cuatro palabras de 32 bits en little-endian
    b = b"".join(bytes.fromhex(texto[i:i + 8])[::-1] for i in range(0, 32, 8))
    return str(ipaddress.IPv6Address(b))


def parsear_proc_tcp(texto, familia="tcp"):
    """Devuelve los sockets en estado LISTEN de un archivo /proc/net/tcp o tcp6."""
    encontrados = []
    for linea in texto.splitlines()[1:]:
        c = linea.split()
        if len(c) < 10 or c[3] != ESTADO_LISTEN:
            continue
        ip_hex, puerto_hex = c[1].rsplit(":", 1)
        try:
            ip = _ip_hex(ip_hex)
        except ValueError:
            continue
        direccion = ipaddress.ip_address(ip)
        expuesto = direccion.is_unspecified or not direccion.is_loopback
        encontrados.append({
            "protocolo": familia, "direccion": ip, "puerto": int(puerto_hex, 16),
            "inodo": int(c[9]),
            "exposicion": "red" if expuesto else "solo_local",
        })
    return encontrados


def mapear_inodos_a_procesos(raiz_proc="/proc"):
    """Construye {inodo: (pid, nombre)}. Cuenta procesos inaccesibles por permisos."""
    mapa, inaccesibles = {}, 0
    try:
        pids = [p for p in os.listdir(raiz_proc) if p.isdigit()]
    except OSError:
        return mapa, -1
    for pid in pids:
        ruta_fd = os.path.join(raiz_proc, pid, "fd")
        try:
            descriptores = os.listdir(ruta_fd)
        except PermissionError:
            inaccesibles += 1
            continue
        except OSError:  # el proceso terminó mientras se leía
            continue
        nombre = "?"
        try:
            with open(os.path.join(raiz_proc, pid, "comm"), encoding="utf-8") as f:
                nombre = f.read().strip()
        except OSError:
            pass
        for fd in descriptores:
            try:
                destino = os.readlink(os.path.join(ruta_fd, fd))
            except OSError:
                continue
            if destino.startswith("socket:["):
                mapa[int(destino[8:-1])] = (int(pid), nombre)
    return mapa, inaccesibles


def _puertos_linux(raiz_proc="/proc"):
    """Enumera puertos TCP en escucha y, si los permisos lo permiten, su proceso."""
    sockets = []
    for archivo, familia in (("net/tcp", "tcp"), ("net/tcp6", "tcp6")):
        try:
            with open(os.path.join(raiz_proc, archivo), encoding="ascii") as f:
                sockets += parsear_proc_tcp(f.read(), familia)
        except OSError:
            continue
    if not sockets and not os.path.exists(os.path.join(raiz_proc, "net/tcp")):
        return resultado("no_disponible", [], "No se pudo leer /proc/net/tcp.")

    mapa, inaccesibles = mapear_inodos_a_procesos(raiz_proc)
    for s in sockets:
        pid_nombre = mapa.get(s["inodo"])
        s["pid"], s["proceso"] = pid_nombre if pid_nombre else (None, "no disponible")
        servicio = SERVICIOS_CONOCIDOS.get(s["puerto"])
        s["servicio"] = servicio[0] if servicio else "desconocido"
        s["riesgo_asociado"] = servicio[1] if servicio else ""
        del s["inodo"]
    sockets.sort(key=lambda s: (s["puerto"], s["protocolo"]))

    mensaje = ""
    if inaccesibles:
        mensaje = ("Algunos procesos no pudieron inspeccionarse por falta de permisos; "
                   "ejecute con sudo para ver todos los procesos asociados.")
    return resultado("ok", sockets, mensaje)


# ----------------------------- Windows (netstat + tasklist) -----------------------------
def parsear_netstat_windows(texto, familia="tcp"):
    """Sockets en escucha de «netstat -ano». Se detectan por dirección remota 0.0.0.0:0 o [::]:0,
    así no depende del idioma de Windows (LISTENING / ESCUCHANDO)."""
    encontrados = []
    for linea in texto.splitlines():
        c = linea.split()
        if len(c) < 5 or c[0].upper() != "TCP" or c[2] not in ("0.0.0.0:0", "[::]:0"):
            continue
        ip, puerto = c[1].rsplit(":", 1)
        ip = ip.strip("[]").split("%")[0]
        try:
            direccion = ipaddress.ip_address(ip)
            pid = int(c[4])
        except ValueError:
            continue
        expuesto = direccion.is_unspecified or not direccion.is_loopback
        encontrados.append({"protocolo": familia, "direccion": ip, "puerto": int(puerto),
                            "pid": pid, "exposicion": "red" if expuesto else "solo_local"})
    return encontrados


def parsear_tasklist_windows(texto):
    """Convierte «tasklist /FO CSV /NH» en {pid: nombre}."""
    mapa = {}
    for fila in csv.reader(io.StringIO(texto)):
        if len(fila) >= 2 and fila[1].isdigit():
            mapa[int(fila[1])] = fila[0]
    return mapa


def _puertos_windows():
    sockets = []
    hubo_datos = False
    for parametro, familia in (("TCP", "tcp"), ("TCPv6", "tcp6")):
        codigo, salida = ejecutar(["netstat", "-ano", "-p", parametro], timeout=15)
        if codigo == 0:
            hubo_datos = True
            sockets += parsear_netstat_windows(salida, familia)
    if not hubo_datos:
        return resultado("no_disponible", [], "No se pudo ejecutar netstat.")
    codigo, salida = ejecutar(["tasklist", "/FO", "CSV", "/NH"], timeout=15)
    nombres = parsear_tasklist_windows(salida) if codigo == 0 else {}
    for s in sockets:
        s["proceso"] = nombres.get(s["pid"], "no disponible")
        servicio = SERVICIOS_CONOCIDOS.get(s["puerto"])
        s["servicio"] = servicio[0] if servicio else "desconocido"
        s["riesgo_asociado"] = servicio[1] if servicio else ""
    sockets.sort(key=lambda x: (x["puerto"], x["protocolo"]))
    return resultado("ok", sockets)


def obtener_puertos_escucha(raiz_proc="/proc"):
    """Enumera puertos TCP en escucha y su proceso (Linux: /proc; Windows: netstat)."""
    return _puertos_windows() if ES_WINDOWS else _puertos_linux(raiz_proc)
