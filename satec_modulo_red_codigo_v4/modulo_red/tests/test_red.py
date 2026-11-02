import contextlib
import io
import ipaddress
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from satec_red import cli, conectividad, interfaces, puertos, registro, util  # noqa: E402

RUTA = """Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT
enp0s3\t00000000\t0202A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0
enp0s3\t0002A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0
"""
TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:0CEA 00000000:0000 0A 00000000:00000000 00:00000000 00000000   128        0 12345 1 0 100 0 0 10 0
   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22222 1 0 100 0 0 10 0
   2: 0F02A8C0:9C40 0102A8C0:0050 01 00000000:00000000 00:00000000 00000000  1000        0 33333 1 0 100 0 0 10 0
"""
IPJ = '[{"ifname":"lo","operstate":"UNKNOWN","addr_info":[{"family":"inet","local":"127.0.0.1","prefixlen":8}]},' \
      '{"ifname":"enp0s3","operstate":"UP","addr_info":[{"family":"inet","local":"192.168.2.15","prefixlen":24}]}]'


class TestInterfaces(unittest.TestCase):
    def test_gateway(self):
        g = interfaces.parsear_ruta_defecto(RUTA)
        self.assertEqual(g, {"interfaz": "enp0s3", "puerta_enlace": "192.168.2.2"})

    def test_sin_gateway(self):
        self.assertIsNone(interfaces.parsear_ruta_defecto(RUTA.splitlines()[0] + "\n"))

    def test_ip_json(self):
        r = interfaces.parsear_ip_json(IPJ)
        self.assertEqual(r[1]["ipv4"][0]["mascara"], "255.255.255.0")
        self.assertEqual(r[0]["ipv4"][0]["mascara"], "255.0.0.0")


class TestPuertos(unittest.TestCase):
    def test_solo_listen(self):
        r = puertos.parsear_proc_tcp(TCP)
        self.assertEqual([s["puerto"] for s in r], [3306, 22])  # 0CEA=3306, 0016=22

    def test_exposicion(self):
        r = {s["puerto"]: s["exposicion"] for s in puertos.parsear_proc_tcp(TCP)}
        self.assertEqual(r[3306], "solo_local")
        self.assertEqual(r[22], "red")

    def test_ipv6(self):
        self.assertEqual(puertos._ip_hex("00000000000000000000000001000000"), "::1")

    def test_permisos_no_rompen(self):
        mapa, _ = puertos.mapear_inodos_a_procesos("/ruta/inexistente")
        self.assertEqual(mapa, {})


class TestConectividad(unittest.TestCase):
    def setUp(self):
        self.redes = [conectividad.ipaddress.IPv4Network("192.168.56.0/24")]

    def test_validar(self):
        with self.assertRaises(ValueError):
            conectividad.validar_ipv4("999.1.1.1")
        with self.assertRaises(ValueError):
            conectividad.validar_ipv4("abc; rm -rf /")

    def test_no_autorizada(self):
        r = conectividad.probar_ping("8.8.8.8", self.redes)
        self.assertEqual(r["estado"], "error")
        self.assertIn("autorizados", r["mensaje"])

    def test_cargar_lista(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# c\n10.0.0.5\n192.168.1.7  # lab\n")
        self.assertEqual(len(conectividad.cargar_autorizados(f.name)), 2)
        os.unlink(f.name)

    def test_lista_invalida(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("no-es-ip\n")
        with self.assertRaises(ValueError):
            conectividad.cargar_autorizados(f.name)
        os.unlink(f.name)


class TestWindows(unittest.TestCase):
    def test_interfaces_json(self):
        j = ('{"adaptadores":[{"Name":"Ethernet","Status":"Up"}],'
             '"ips":{"InterfaceAlias":"Ethernet","IPAddress":"192.168.56.101","PrefixLength":24}}')
        r = interfaces.parsear_interfaces_windows(j)
        self.assertEqual(r[0]["nombre"], "Ethernet")
        self.assertEqual(r[0]["estado"], "UP")
        self.assertEqual(r[0]["ipv4"][0]["mascara"], "255.255.255.0")

    def test_gateway_json(self):
        g = interfaces.parsear_gateway_windows('{"InterfaceAlias":"Ethernet","NextHop":"192.168.1.1"}')
        self.assertEqual(g["puerta_enlace"], "192.168.1.1")
        self.assertIsNone(interfaces.parsear_gateway_windows('{"InterfaceAlias":"X","NextHop":"0.0.0.0"}'))
        self.assertIsNone(interfaces.parsear_gateway_windows(""))

    def test_netstat(self):
        t = ("  Proto  Direccion local   Direccion remota   Estado   PID\n"
             "  TCP    0.0.0.0:135       0.0.0.0:0          ESCUCHANDO   1088\n"
             "  TCP    127.0.0.1:5432    0.0.0.0:0          LISTENING    4200\n"
             "  TCP    192.168.1.5:50000 142.250.1.1:443    ESTABLISHED  999\n")
        r = puertos.parsear_netstat_windows(t)
        self.assertEqual([(s["puerto"], s["exposicion"], s["pid"]) for s in r],
                         [(135, "red", 1088), (5432, "solo_local", 4200)])

    def test_tasklist(self):
        t = '"svchost.exe","1088","Services","0","12,000 K"\n"postgres.exe","4200","Services","0","9,000 K"\n'
        self.assertEqual(puertos.parsear_tasklist_windows(t)[4200], "postgres.exe")


class TestAgregarIP(unittest.TestCase):
    def test_ip_privada_ok_y_publica_no(self):
        self.assertEqual(str(conectividad.validar_ip_laboratorio("192.168.56.102")), "192.168.56.102")
        for mala in ("8.8.8.8", "0.0.0.0", "224.0.0.1", "abc", ""):
            with self.assertRaises(ValueError):
                conectividad.validar_ip_laboratorio(mala)

    def test_puertos(self):
        self.assertEqual(conectividad.validar_puertos("22, 80"), [22, 80])
        self.assertEqual(conectividad.validar_puertos(""), [])
        for malo in ("0", "70000", "22,abc", "1,2,3,4,5,6"):
            with self.assertRaises(ValueError):
                conectividad.validar_puertos(malo)

    def test_agregar_a_lista(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "cfg", "autorizados.txt")
            ip = conectividad.validar_ip_laboratorio("10.0.0.7")
            self.assertTrue(conectividad.agregar_autorizado(ruta, ip))
            self.assertFalse(conectividad.agregar_autorizado(ruta, ip))  # duplicada
            redes = conectividad.cargar_autorizados(ruta)
            self.assertTrue(conectividad.esta_autorizada(ip, redes))



# ============================ Pruebas de las correcciones v1.1 ============================
def _lista(texto):
    """Carga una lista blanca desde un texto (archivo temporal)."""
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "lista.txt")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        return conectividad.cargar_autorizados(ruta)


class TestListaBlancaSegura(unittest.TestCase):
    def test_rechaza_todo_internet(self):
        with self.assertRaises(ValueError):
            _lista("0.0.0.0/0\n")

    def test_rechaza_cualquier_red_o_rango(self):
        for cidr in ("0.0.0.0/0", "8.8.8.0/24", "10.0.0.0/8", "192.168.56.0/24",
                     "192.168.56.5/24", "192.168.56.20/32"):
            with self.assertRaises(ValueError, msg=cidr):
                _lista(cidr + "\n")

    def test_lista_vacia_deniega_todo(self):
        self.assertEqual(_lista("# solo comentarios\n\n"), [])
        r = conectividad.probar_ping("127.0.0.1", [])
        self.assertEqual(r["estado"], "error")
        self.assertIn("autorizados", r["mensaje"])

    def test_config_de_fabrica_solo_autoriza_localhost(self):
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config", "equipos_autorizados.txt")
        self.assertEqual([str(r) for r in conectividad.cargar_autorizados(ruta)], ["127.0.0.1/32"])

    def test_acepta_solo_equipos_individuales(self):
        self.assertEqual(len(_lista("127.0.0.1\n192.168.56.20  # lab\n10.1.2.3\n")), 3)

    def test_deduplica(self):
        self.assertEqual(len(_lista("192.168.56.20\n192.168.56.20\n")), 1)

    def test_rechaza_en_la_lista_ips_no_de_equipo(self):
        for mala in ("192.168.56.0", "192.168.56.255", "169.254.1.1", "8.8.8.8", "0.0.0.0"):
            with self.assertRaises(ValueError, msg=mala):
                _lista(mala + "\n")

    def test_limite_de_equipos(self):
        base = "\n".join(f"192.168.56.{n}" for n in range(1, conectividad.MAX_AUTORIZADOS + 2))
        with self.assertRaises(ValueError):
            _lista(base + "\n")
        self.assertEqual(len(_lista("\n".join(f"192.168.56.{n}" for n in range(1, conectividad.MAX_AUTORIZADOS + 1)))),
                         conectividad.MAX_AUTORIZADOS)

    def test_una_linea_mala_invalida_toda_la_lista(self):
        with self.assertRaises(ValueError):
            _lista("192.168.56.20\n8.8.8.8\n")

    def test_publica_no_pasa_aunque_la_lista_se_arme_por_codigo(self):
        todo = [ipaddress.IPv4Network("0.0.0.0/0")]
        r = conectividad.probar_ping("8.8.8.8", todo)
        self.assertEqual(r["estado"], "error")
        r = conectividad.probar_tcp("8.8.8.8", 80, todo)
        self.assertEqual(r["estado"], "error")

    def test_ip_laboratorio_casos_borde(self):
        for mala in ("192.168.56.0", "192.168.56.255", "169.254.1.1", "255.255.255.255"):
            with self.assertRaises(ValueError, msg=mala):
                conectividad.validar_ip_laboratorio(mala)
        self.assertEqual(str(conectividad.validar_ip_laboratorio("127.0.0.1")), "127.0.0.1")

    def test_agregar_rechaza_publica(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                conectividad.agregar_autorizado(os.path.join(d, "l.txt"), "8.8.8.8")


class TestEjecutar(unittest.TestCase):
    def test_programa_inexistente(self):
        self.assertEqual(util.ejecutar(["programa_que_no_existe_satec"]), (util.NO_EXISTE, ""))

    def test_timeout_distinto_de_inexistente(self):
        cmd = [sys.executable, "-c", "import time; time.sleep(3)"]
        self.assertEqual(util.ejecutar(cmd, timeout=1), (util.TIMEOUT, ""))

    def test_salida_normal(self):
        codigo, salida = util.ejecutar([sys.executable, "-c", "print('hola')"])
        self.assertEqual(codigo, 0)
        self.assertIn("hola", salida)


class TestPing(unittest.TestCase):
    def setUp(self):
        self.redes = [ipaddress.IPv4Network("192.168.56.0/24")]
        p = mock.patch.object(conectividad, "ES_WINDOWS", False)
        p.start()
        self.addCleanup(p.stop)

    def _ping(self, retorno):
        with mock.patch.object(conectividad, "ejecutar", return_value=retorno):
            return conectividad.probar_ping("192.168.56.10", self.redes)

    def test_sin_comando(self):
        self.assertEqual(self._ping((util.NO_EXISTE, ""))["estado"], "no_disponible")

    def test_timeout_no_se_reporta_como_inexistente(self):
        r = self._ping((util.TIMEOUT, ""))
        self.assertEqual(r["estado"], "error")
        self.assertIn("tiempo", r["mensaje"])

    def test_alcanzable(self):
        r = self._ping((0, "2 packets transmitted, 2 received, 0% packet loss"))
        self.assertTrue(r["datos"][0]["alcanzable"])

    def test_sin_respuesta(self):
        r = self._ping((1, "2 packets transmitted, 0 received, 100% packet loss"))
        self.assertEqual(r["estado"], "ok")
        self.assertFalse(r["datos"][0]["alcanzable"])


class TestTCPReal(unittest.TestCase):
    def test_puerto_abierto_y_cerrado(self):
        redes = [ipaddress.IPv4Network("127.0.0.1/32")]
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        puerto = srv.getsockname()[1]
        try:
            self.assertTrue(conectividad.probar_tcp("127.0.0.1", puerto, redes)["datos"][0]["abierto"])
        finally:
            srv.close()
        self.assertFalse(conectividad.probar_tcp("127.0.0.1", puerto, redes)["datos"][0]["abierto"])


class TestExposicionIPv6(unittest.TestCase):
    def _t(self, ip_hex):
        return ("  sl local rem st\n   0: %s:1F90 00000000000000000000000000000000:0000 0A "
                "0:0 0:0 0 0 0 1 1 0\n" % ip_hex)

    def test_ipv4_mapeada_loopback_es_local(self):
        r = puertos.parsear_proc_tcp(self._t("0000000000000000FFFF00000100007F"), "tcp6")
        self.assertEqual(r[0]["exposicion"], "solo_local")

    def test_ipv4_mapeada_no_loopback_es_red(self):
        r = puertos.parsear_proc_tcp(self._t("0000000000000000FFFF00000F02A8C0"), "tcp6")
        self.assertEqual(r[0]["exposicion"], "red")

    def test_loopback_y_cualquiera_ipv6(self):
        self.assertEqual(puertos.parsear_proc_tcp(self._t("00000000000000000000000001000000"), "tcp6")[0]["exposicion"], "solo_local")
        self.assertEqual(puertos.parsear_proc_tcp(self._t("00000000000000000000000000000000"), "tcp6")[0]["exposicion"], "red")


class TestRegistro(unittest.TestCase):
    def test_escribe_linea_json(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "logs", "x.jsonl")
            self.assertTrue(registro.registrar("prueba", {"estado": "ok", "datos": [1]}, ruta=ruta))
            with open(ruta, encoding="utf-8") as f:
                self.assertIn('"evento": "prueba"', f.read())

    def test_devuelve_false_si_no_puede_escribir(self):
        with tempfile.NamedTemporaryFile() as f:  # una carpeta no puede colgar de un archivo
            self.assertFalse(registro.registrar("x", {"estado": "ok"}, ruta=os.path.join(f.name, "a", "b.jsonl")))

    def test_cli_avisa_una_sola_vez(self):
        cli._log_avisado = False
        out = io.StringIO()
        with mock.patch.object(cli, "registrar", return_value=False), contextlib.redirect_stdout(out):
            cli._registrar("a", {"estado": "ok"})
            cli._registrar("b", {"estado": "ok"})
        self.assertEqual(out.getvalue().count("No se pudo escribir el registro"), 1)
        cli._log_avisado = False


@unittest.skipIf(interfaces.fcntl is None or not sys.platform.startswith("linux"), "solo Linux")
class TestInterfacesSinIp(unittest.TestCase):
    def test_loopback_por_ioctl(self):
        self.assertEqual(interfaces._ipv4_principal("lo"), ("127.0.0.1", 8))

    def test_respaldo_cuando_no_hay_comando_ip(self):
        with mock.patch.object(interfaces, "ejecutar", return_value=(util.NO_EXISTE, "")):
            r = interfaces._interfaces_linux()
        self.assertEqual(r["estado"], "ok")
        lo = next(i for i in r["datos"] if i["nombre"] == "lo")
        self.assertEqual(lo["ipv4"][0]["mascara"], "255.0.0.0")


class TestParsearObjetivo(unittest.TestCase):
    def test_ip_unica(self):
        self.assertEqual([str(i) for i in conectividad.parsear_objetivo("192.168.56.10")],
                         ["192.168.56.10"])

    def test_rango_abreviado_y_completo(self):
        esperado = ["192.168.56.100", "192.168.56.101", "192.168.56.102"]
        self.assertEqual([str(i) for i in conectividad.parsear_objetivo("192.168.56.100-102")], esperado)
        self.assertEqual([str(i) for i in conectividad.parsear_objetivo(
            "192.168.56.100-192.168.56.102")], esperado)

    def test_cidr_excluye_red_y_difusion(self):
        ips = [str(i) for i in conectividad.parsear_objetivo("192.168.56.0/29")]
        self.assertEqual(ips[0], "192.168.56.1")
        self.assertEqual(ips[-1], "192.168.56.6")

    def test_rechazos(self):
        for malo in ("", "8.8.8.8", "8.8.8.0/29", "192.168.56.0/24", "192.168.56.10-5",
                     "192.168.56.1-192.168.56.200", "10.0.0.0/8", "abc", "192.168.56.1-999"):
            with self.assertRaises(ValueError, msg=malo):
                conectividad.parsear_objetivo(malo)

    def test_rango_que_cruza_a_zona_publica_se_rechaza(self):
        with self.assertRaises(ValueError):
            conectividad.parsear_objetivo("172.31.255.250-172.32.0.5")


class TestOpcionAgregar(unittest.TestCase):
    def _ejecutar(self, entradas):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "autorizados.txt")

            def ping_falso(ip, redes, **kw):
                return util.resultado("ok", [{"destino": str(ip), "alcanzable": str(ip).endswith("1"),
                                              "resumen": ""}])
            with mock.patch.object(cli, "RUTA_AUTORIZADOS", ruta), \
                 mock.patch.object(cli, "registrar", return_value=True), \
                 mock.patch.object(conectividad, "probar_ping", side_effect=ping_falso), \
                 mock.patch.object(conectividad, "probar_tcp", return_value=util.resultado(
                     "ok", [{"destino": "x", "puerto": 80, "abierto": True}])), \
                 mock.patch("builtins.input", side_effect=entradas), \
                 contextlib.redirect_stdout(io.StringIO()) as salida:
                cli.agregar_y_analizar()
            contenido = None
            if os.path.exists(ruta):
                with open(ruta, encoding="utf-8") as f:
                    contenido = f.read()
            return contenido, salida.getvalue()

    def test_es_la_primera_opcion_del_menu(self):
        self.assertEqual(next(iter(cli.MENU)), "1")
        self.assertIs(cli.MENU["1"][1], cli.agregar_y_analizar)

    def test_ip_unica_se_agrega_reescribiendo_la_ip(self):
        contenido, _ = self._ejecutar(["192.168.56.102", "192.168.56.102", ""])
        self.assertIn("192.168.56.102", contenido)

    def test_rango_agrega_cada_equipo_y_resume(self):
        contenido, salida = self._ejecutar(["192.168.56.100-102", "192.168.56.100-102", "80"])
        for n in (100, 101, 102):
            self.assertIn(f"192.168.56.{n}", contenido)
        self.assertIn("1 de 3 equipos respondieron", salida)
        self.assertIn("192.168.56.101:80: ABIERTO", salida)  # puertos solo en el que respondió
        self.assertNotIn("192.168.56.100:80", salida)

    def test_confirmacion_distinta_no_escribe(self):
        contenido, _ = self._ejecutar(["192.168.56.100-102", "192.168.56.100-101"])
        self.assertIsNone(contenido)

    def test_rechaza_ip_publica_y_rango_publico(self):
        for malo in ("8.8.8.8", "8.8.8.1-8.8.8.5"):
            contenido, salida = self._ejecutar([malo])
            self.assertIsNone(contenido)
            self.assertIn("[!]", salida)


if __name__ == "__main__":
    unittest.main()
