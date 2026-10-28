import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from satec_red import conectividad, interfaces, puertos  # noqa: E402

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
            f.write("# c\n10.0.0.5\n192.168.1.0/24  # lab\n")
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


if __name__ == "__main__":
    unittest.main()
