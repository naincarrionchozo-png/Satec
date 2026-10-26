# SATEC · Módulo 1: Diagnóstico de red y servicios

Parte del proyecto SATEC (SENATI). Herramienta **solo de lectura**: no modifica la
configuración del sistema ni escanea equipos no autorizados.

## Requisitos
- Ubuntu o Debian (probado en máquina virtual), Python 3.8+
- Solo biblioteca estándar de Python (sin `pip install`)
- Paquetes del sistema: `iproute2` (comando `ip`) e `iputils-ping` (viene por defecto)

## Ejecución
```bash
cd modulo_red
python3 -m satec_red              # menú interactivo
sudo python3 -m satec_red         # idem, con permisos para ver el proceso de cada puerto
python3 -m satec_red --json       # diagnóstico completo en JSON (para integración)
python3 -m unittest discover -s tests -v   # pruebas automáticas
```

## Configuración
Edite `config/equipos_autorizados.txt` (una IP o red CIDR por línea). La conectividad
solo se prueba contra esas direcciones; cualquier otra es rechazada.

## Integración con los otros módulos
```python
from satec_red.diagnostico import ejecutar_diagnostico
datos = ejecutar_diagnostico(guardar_log=False)
# datos["interfaces"|"puerta_enlace"|"puertos_escucha"] -> {"estado","mensaje","fecha","datos"}
# estado: "ok" | "no_disponible" | "error"  (equivale a conforme / no evaluable en el Módulo 4)
```
Los resultados se registran con fecha y hora en `logs/diagnostico_red.jsonl`.

## Estructura
```
satec_red/  util.py · interfaces.py · puertos.py · conectividad.py · registro.py
            diagnostico.py (integración) · cli.py (menú) · __main__.py
config/     equipos_autorizados.txt
tests/      test_red.py
```
