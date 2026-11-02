"""Requisito 6: comprobar conectividad SOLO con direcciones IP autorizadas."""
import ipaddress
import os
import socket

from .util import ES_WINDOWS, NO_EXISTE, TIMEOUT, ahora, ejecutar, resultado

# Única zona que puede autorizarse: redes privadas de laboratorio y bucle local.
REDES_PERMITIDAS = tuple(ipaddress.IPv4Network(n) for n in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"))
MAX_AUTORIZADOS = 32  # lista corta: se autoriza solo lo estrictamente necesario


class NoAutorizadoError(Exception):
    """Se intentó probar un destino que no está en la lista de autorizados."""


def _es_red_de_laboratorio(red):
    return any(red.subnet_of(p) for p in REDES_PERMITIDAS)


def validar_ipv4(texto):
    """Valida y normaliza una dirección IPv4. Lanza ValueError si es inválida."""
    texto = (texto or "").strip()
    try:
        return ipaddress.IPv4Address(texto)
    except ipaddress.AddressValueError:
        raise ValueError(f"'{texto}' no es una dirección IPv4 válida.") from None


def validar_ip_laboratorio(texto):
    """Valida una IPv4 que puede agregarse a la lista de autorizados.

    Solo se aceptan direcciones de las redes privadas de laboratorio o bucle local:
    una IP pública, link-local, de red (.0) o de difusión (.255) no puede autorizarse.
    """
    ip = validar_ipv4(texto)
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local:
        raise ValueError(f"{ip} no es una dirección de equipo válida.")
    if not _es_red_de_laboratorio(ipaddress.IPv4Network(f"{ip}/32")):
        raise ValueError(f"{ip} es una IP pública. Solo se pueden autorizar equipos "
                         "de la red privada del laboratorio.")
    if not ip.is_loopback and int(str(ip).rsplit(".", 1)[1]) in (0, 255):
        raise ValueError(f"{ip} parece una dirección de red o de difusión, no de un equipo.")
    return ip


def parsear_objetivo(texto, maximo=MAX_AUTORIZADOS):
    """Convierte lo que escribe el usuario en una lista de IPv4 de laboratorio.

    Formatos aceptados:
      - una IP:               192.168.56.102
      - una red CIDR:         192.168.56.96/27      (solo equipos, sin red ni difusión)
      - un rango completo:    192.168.56.100-192.168.56.110
      - un rango abreviado:   192.168.56.100-110
    Cada IP pasa por validar_ip_laboratorio (solo redes privadas) y el total no puede
    superar `maximo` equipos. Lanza ValueError con un mensaje claro si algo no cumple.
    """
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("No ingresó ninguna IP ni rango.")
    if "/" in texto:
        try:
            red = ipaddress.IPv4Network(texto, strict=False)
        except ValueError:
            raise ValueError(f"'{texto}' no es una red válida (ej. 192.168.56.96/27).") from None
        if not _es_red_de_laboratorio(red):
            raise ValueError(f"{red} no pertenece a las redes privadas de laboratorio.")
        if red.num_addresses - 2 > maximo and red.prefixlen < 31:
            raise ValueError(f"{red} tiene demasiados equipos; el máximo por análisis es {maximo} "
                             f"(use /27 o más pequeña).")
        ips = list(red.hosts()) if red.prefixlen < 31 else list(red)
    elif "-" in texto:
        izq, _, der = (t.strip() for t in texto.partition("-"))
        inicio = validar_ipv4(izq)
        if der.isdigit():  # forma abreviada: 192.168.56.100-110
            der = ".".join(str(inicio).split(".")[:3] + [der])
        fin = validar_ipv4(der)
        if int(fin) < int(inicio):
            raise ValueError("El rango está al revés: la IP final es menor que la inicial.")
        if int(fin) - int(inicio) + 1 > maximo:
            raise ValueError(f"El rango tiene más de {maximo} equipos; reduzca el rango.")
        ips = [ipaddress.IPv4Address(n) for n in range(int(inicio), int(fin) + 1)]
    else:
        ips = [validar_ipv4(texto)]
    if len(ips) > maximo:
        raise ValueError(f"Máximo {maximo} equipos por análisis.")
    return [validar_ip_laboratorio(str(ip)) for ip in ips]


def validar_puertos(texto, maximo=5):
    """Convierte «22, 80» en [22, 80]. Vacío = sin puertos. Máximo 5 (no es un escáner)."""
    texto = (texto or "").strip()
    if not texto:
        return []
    puertos = []
    for trozo in texto.replace(";", ",").split(","):
        trozo = trozo.strip()
        if not trozo.isdigit() or not (1 <= int(trozo) <= 65535):
            raise ValueError(f"'{trozo}' no es un puerto válido (1-65535).")
        puertos.append(int(trozo))
    if len(puertos) > maximo:
        raise ValueError(f"Indique como máximo {maximo} puertos.")
    return puertos


def agregar_autorizado(ruta, ip):
    """Agrega una IP a la lista de autorizados. Devuelve False si ya estaba incluida."""
    ip = validar_ip_laboratorio(str(ip))  # defensa: nunca escribir algo no validado
    try:
        redes = cargar_autorizados(ruta)
    except FileNotFoundError:
        redes = []
    if esta_autorizada(ip, redes):
        return False
    if len(redes) >= MAX_AUTORIZADOS:
        raise ValueError(f"La lista ya tiene {MAX_AUTORIZADOS} equipos autorizados (máximo).")
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(f"{ip}  # agregada desde el programa el {ahora()}\n")
    return True


def cargar_autorizados(ruta):
    """Lee la lista blanca: UNA dirección IPv4 por línea (# = comentario).

    Política estricta (denegar por defecto):
    - Solo equipos individuales; no se admiten redes ni rangos (nada de «/24», «/8» ni «/0»).
    - Cada IP debe ser de laboratorio (privada o bucle local); no públicas, link-local,
      de red (.0) ni de difusión (.255).
    - Máximo MAX_AUTORIZADOS equipos.
    Cualquier línea que incumpla estas reglas invalida toda la lista (no se prueba nada).
    Devuelve una lista de IPv4Network /32 (una por equipo, sin duplicados).
    """
    redes = []
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.split("#", 1)[0].strip()
            if not linea:
                continue
            if "/" in linea:
                raise ValueError(f"Línea {n} de {ruta}: '{linea}' es una red o rango. "
                                 "Solo se admiten equipos individuales; liste cada IP por separado.")
            try:
                ip = validar_ip_laboratorio(linea)
            except ValueError as e:
                raise ValueError(f"Línea {n} de {ruta}: {e}") from None
            red = ipaddress.IPv4Network(f"{ip}/32")
            if red not in redes:
                redes.append(red)
    if len(redes) > MAX_AUTORIZADOS:
        raise ValueError(f"{ruta}: demasiados equipos autorizados ({len(redes)}); "
                         f"el máximo es {MAX_AUTORIZADOS}.")
    return redes


def esta_autorizada(ip, redes):
    return any(ip in red for red in redes)


def _verificar(ip_texto, redes):
    ip = validar_ipv4(ip_texto)
    if not esta_autorizada(ip, redes):
        raise NoAutorizadoError(
            f"{ip} no figura en la lista de equipos autorizados del laboratorio.")
    # Defensa en profundidad: aunque la lista se arme por código, nunca salir de la zona privada.
    if not _es_red_de_laboratorio(ipaddress.IPv4Network(f"{ip}/32")):
        raise NoAutorizadoError(f"{ip} está fuera de las redes privadas de laboratorio; "
                                "no puede autorizarse.")
    return ip


def probar_ping(ip_texto, redes, intentos=2, espera=2):
    """Envía ICMP echo (comando ping del sistema) a un equipo autorizado."""
    try:
        ip = _verificar(ip_texto, redes)
    except (ValueError, NoAutorizadoError) as e:
        return resultado("error", [], str(e))
    if ES_WINDOWS:
        cmd = ["ping", "-n", str(intentos), "-w", str(espera * 1000), str(ip)]
    else:
        cmd = ["ping", "-c", str(intentos), "-W", str(espera), str(ip)]
    codigo, salida = ejecutar(cmd, timeout=intentos * (espera + 1) + 2)
    if codigo == NO_EXISTE:
        return resultado("no_disponible", [],
                         "El comando 'ping' no está disponible o no hay permisos para usarlo.")
    if codigo == TIMEOUT:
        return resultado("error", [], "El comando 'ping' excedió el tiempo máximo de espera.")
    # En Windows el código de salida puede ser 0 aunque «el host de destino no sea
    # accesible»; una respuesta real siempre incluye TTL=.
    alcanzable = (("TTL=" in salida.upper()) if ES_WINDOWS else codigo == 0)
    resumen = next((l.strip() for l in salida.splitlines()
                    if "packets transmitted" in l or "%" in l), "")
    return resultado("ok", [{"destino": str(ip), "alcanzable": alcanzable, "resumen": resumen}])


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
    except OSError:  # incluye ConnectionRefusedError y socket.timeout
        abierto = False
    return resultado("ok", [{"destino": str(ip), "puerto": int(puerto), "abierto": abierto}])
