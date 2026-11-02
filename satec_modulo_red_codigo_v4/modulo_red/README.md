# SATEC · Módulo 1: Diagnóstico de red y servicios

Parte del proyecto SATEC (SENATI). Herramienta de **diagnóstico de solo lectura** sobre el
equipo local: no modifica la configuración del sistema ni prueba equipos no autorizados.
La única escritura es su propio registro (`logs/`) y, si el administrador lo habilita, la
lista `config/equipos_autorizados.txt` (opción 1).

## Requisitos
- Ubuntu o Debian (sistema oficial del proyecto), Python 3.8+
- Windows 10/11 con Python 3.8+ (soporte adicional; usa PowerShell, netstat, tasklist y ping)
- Solo biblioteca estándar de Python (sin `pip install`)
- Paquetes del sistema: `iproute2` (comando `ip`) e `iputils-ping`. Si `ip` falta, el módulo
  obtiene interfaces, IPv4 y máscara desde el sistema (solo la dirección principal de cada una).

## Ejecución
```bash
cd modulo_red
python3 -m satec_red              # menú interactivo
sudo python3 -m satec_red         # idem, con permisos para ver el proceso de cada puerto
python3 -m satec_red --json       # diagnóstico completo en JSON (para integración)
python3 -m unittest discover -s tests -v   # pruebas automáticas
```

## Menú
| Opción | Función |
|---|---|
| 1 | **Agregar IP o rango de IP a analizar** (IP única, `a.b.c.d-e` o CIDR; ping + hasta 5 puertos TCP) |
| 2 | Interfaces, IPv4 y máscaras |
| 3 | Puerta de enlace predeterminada |
| 4 | Puertos TCP en escucha y proceso asociado |
| 5 | Conectividad (ping) con un equipo autorizado |
| 6 | Diagnóstico completo (2 + 3 + 4) |
| 7 | Ver equipos autorizados |

## Uso en Windows
Abra PowerShell o CMD, entre a la carpeta `modulo_red` y ejecute `py -m satec_red`
(o `python -m satec_red`). Para ver todos los procesos, abra la terminal **como administrador**.
Las pruebas oficiales del proyecto se documentan en Ubuntu.

## Configuración y autorización de equipos
El programa **deniega por defecto**: solo se prueba lo que figure en
`config/equipos_autorizados.txt`; cualquier otra dirección es rechazada. De fábrica solo está
autorizado `127.0.0.1`. Reglas estrictas al leer el archivo (si una línea las incumple, se informa
el número de línea y **no se prueba nada**):
- **Una IPv4 por línea, equipos individuales.** No se admiten redes ni rangos (`192.168.56.0/24`,
  `10.0.0.0/8`, `0.0.0.0/0`...): cada equipo se autoriza por separado.
- Solo IP privadas de laboratorio (`10.x`, `172.16-31.x`, `192.168.x`) o bucle local. Nunca
  públicas, link-local, de red (`.0`) ni de difusión (`.255`).
- Máximo 32 equipos. Los duplicados se ignoran.

Ejemplo: para autorizar una máquina virtual, agregue la línea `192.168.56.101`.

**Opción 1 (IP o rango).** Es lo primero que muestra el menú. Acepta una IP (`192.168.56.102`),
un rango (`192.168.56.100-110` o `192.168.56.100-192.168.56.110`) o una red CIDR pequeña
(`192.168.56.96/27`). Reglas: solo IP privadas de laboratorio, máximo 32 equipos por análisis, y se
exige reescribir exactamente lo ingresado para confirmar que hay autorización. Cada equipo del rango
se guarda individualmente en `config/equipos_autorizados.txt` (el archivo sigue sin aceptar rangos),
se registra la autorización y se hace ping a todos; los puertos TCP elegidos se comprueban solo en
los equipos que respondieron.

## Integración con los otros módulos
```python
from satec_red.diagnostico import ejecutar_diagnostico
datos = ejecutar_diagnostico(guardar_log=False)
# datos["interfaces"|"puerta_enlace"|"puertos_escucha"] -> {"estado","mensaje","fecha","datos"}
# datos["log_guardado"] -> True/False si se intentó registrar; None si guardar_log=False
# estado: "ok" | "no_disponible" | "error"  (equivale a conforme / no evaluable en el Módulo 4)
```
Los resultados se registran con fecha y hora en `logs/diagnostico_red.jsonl`. Si no se puede
escribir el registro, el menú lo avisa. Al ejecutar con `sudo`, el archivo queda a nombre del
usuario que invocó sudo.

## Estructura
```
satec_red/  util.py · interfaces.py · puertos.py · conectividad.py · registro.py
            diagnostico.py (integración) · cli.py (menú) · __main__.py
config/     equipos_autorizados.txt
logs/       diagnostico_red.jsonl (se crea al ejecutar)
tests/      test_red.py
docs/       PRUEBAS_MODULO_1.md (plantilla de pruebas obligatorias 1, 2, 3, 11 y 12)
.gitignore  excluye logs y archivos temporales del repositorio
```

## Control de versiones (Git)
```bash
git init
git add .
git commit -m "Módulo 1: diagnóstico de red y servicios"
```
El `.gitignore` evita subir `logs/*.jsonl`, que contiene IP y nombres de procesos del equipo.

## Cambios de la versión 1.2.0
- La opción «Agregar IP o rango de IP a analizar» pasa a ser la **primera** del menú (pedido del docente) y acepta IP única, rango o CIDR (máx. 32 equipos, solo redes privadas).
- Se retira la variable `SATEC_PERMITIR_AGREGAR`: la autorización se confirma reescribiendo la IP o rango.
- El resto de opciones se renumeran (2 a 7).

## Cambios de la versión 1.1.2 (incluye los de 1.1.0 y 1.1.1)
- Política estricta: lista blanca de equipos individuales (sin redes ni rangos), máximo 32, de fábrica solo `127.0.0.1`; una línea inválida anula toda la lista.
- La opción 6 pide reescribir la IP para confirmar.

- La lista de autorizados se valida al leerla (solo IP privadas individuales).
- La opción 6 requiere habilitación del administrador (`SATEC_PERMITIR_AGREGAR=1`).
- `ejecutar()` distingue «programa inexistente» de «tiempo agotado»; el ping informa cada caso.
- Las IPv4 mapeadas en IPv6 (`::ffff:127.0.0.1`) se clasifican correctamente como locales.
- El registro avisa si falla y respeta el propietario al usar `sudo`.
- Respaldo para interfaces/IPv4/máscara cuando no existe el comando `ip`.
- Pruebas nuevas (ver `tests/`).
