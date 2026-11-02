# Documentación de pruebas · Módulo 1: Diagnóstico de red y servicios

Proyecto SATEC · Practicante 1. Pruebas obligatorias del documento de asignación (sección IX)
que corresponden a este módulo: **1, 2, 3, 11 y 12**. Las pruebas 4 a 10 pertenecen a los
Módulos 2 a 5.

**Cómo usar este documento:** ejecute cada procedimiento en su máquina virtual, copie lo que
muestre el programa en «Resultado obtenido» y adjunte la captura indicada en «Evidencia».
Las columnas «Resultado esperado» ya están completas; no las cambie para que coincidan con lo
obtenido. Si algo no coincide, anótelo en la sección «Problemas encontrados y soluciones» del
informe final.

| Dato | Valor |
|---|---|
| Fecha de ejecución | |
| Ejecutado por | |
| Sistema operativo (ejecute `lsb_release -d`) | |
| Versión de Python (`python3 --version`) | |
| Versión del módulo (`satec_red/__init__.py`) | 1.1.2 |

Todos los comandos se ejecutan desde la carpeta `modulo_red`.

---

## Prueba 1 · Mostrar las interfaces y direcciones IP del equipo
**Requisitos cubiertos:** Módulo 1, req. 1 y 2.

**Objetivo:** comprobar que el programa identifica las interfaces de red y muestra su IPv4 y máscara.

**Procedimiento**
1. Ejecutar `python3 -m satec_red` y elegir la opción **1**.
2. En otra terminal, ejecutar `ip -4 addr show` y comparar nombre, IPv4 y prefijo de cada interfaz.

**Resultado esperado:** el programa lista todas las interfaces con su estado (UP/DOWN/UNKNOWN),
IPv4 y máscara, y los datos coinciden con los de `ip -4 addr show`. Una interfaz sin IPv4 aparece
sin dirección, sin error.

| Resultado obtenido | |
|---|---|
| **Evidencia** | Captura de la opción 1 junto a la salida de `ip -4 addr show` |
| **¿Cumple?** | ☐ Sí  ☐ No |

---

## Prueba 2 · Identificar al menos un servicio local en escucha
**Requisitos cubiertos:** Módulo 1, req. 4 y 5.

**Objetivo:** comprobar que se enumeran los puertos TCP en escucha y su proceso asociado.

**Procedimiento**
1. En una terminal, iniciar un servicio de prueba: `python3 -m http.server 8765`
2. En otra, ejecutar `python3 -m satec_red`, opción **3**. Repetir con `sudo python3 -m satec_red`.
3. Contrastar con `ss -tlnp` y confirmar que ambos muestran el puerto 8765.
4. Detener el servicio con Ctrl+C y repetir la opción 3.

**Resultado esperado:** con el servicio activo aparece el puerto **8765**, exposición `red`
(escucha en `0.0.0.0`) y proceso `python3`. Sin `sudo`, los procesos de otros usuarios se muestran
como «no disponible», sin error. Tras detener el servicio, el puerto 8765 ya no aparece.

| Resultado obtenido (sin sudo) | |
|---|---|
| **Resultado obtenido (con sudo)** | |
| **Evidencia** | Capturas de la opción 3 con y sin servicio, y de `ss -tlnp` |
| **¿Cumple?** | ☐ Sí  ☐ No |

---

## Prueba 3 · Comprobar conectividad con un equipo virtual autorizado
**Requisitos cubiertos:** Módulo 1, req. 6; alcance (solo equipos autorizados).

**Objetivo:** comprobar que solo se prueba conectividad con equipos autorizados y que los demás se rechazan.

**Procedimiento**
1. Encender la segunda máquina virtual del laboratorio y anotar su IP (`ip -4 addr` en esa VM).
2. Autorizarla: agregar su IP exacta, una por línea y sin rangos, en `config/equipos_autorizados.txt`.
3. Ejecutar `python3 -m satec_red`, opción **4**, e ingresar esa IP.
4. Apagar la VM y repetir.
5. Ingresar una IP **no autorizada** (por ejemplo `192.168.56.200`) y una pública (`8.8.8.8`).
6. *(Opcional, evidencia fuerte)* En otra terminal, `sudo tcpdump -i any icmp` durante el paso 5
   para demostrar que no salió ningún paquete.

**Resultado esperado:** con la VM encendida, el equipo figura como alcanzable. Con la VM apagada,
se informa que no hay respuesta, sin error del programa. Las IP no autorizadas y las públicas se
rechazan con «no figura en la lista de equipos autorizados del laboratorio» y no generan tráfico.
Cada intento queda registrado con fecha y hora en `logs/diagnostico_red.jsonl`.

| Resultado obtenido (VM encendida) | |
|---|---|
| **Resultado obtenido (VM apagada)** | |
| **Resultado obtenido (IP no autorizada)** | |
| **Evidencia** | Capturas de los tres casos y de la línea correspondiente en el log |
| **¿Cumple?** | ☐ Sí  ☐ No |

---

## Prueba 11 · Entradas inválidas y errores de permisos
**Requisitos cubiertos:** Módulo 1, req. 8; requisito técnico de validaciones y mensajes comprensibles.

**Objetivo:** comprobar que el programa no falla ante datos incorrectos ni ante falta de permisos.

**Procedimiento A: entradas inválidas (opción 4)**
Ingresar cada valor en la opción 4 y anotar el mensaje:

| Entrada | Resultado esperado | Resultado obtenido |
|---|---|---|
| `abc` | «'abc' no es una dirección IPv4 válida.» | |
| `999.1.1.1` | «'999.1.1.1' no es una dirección IPv4 válida.» | |
| (vacío, solo Enter) | Mensaje de dirección inválida, sin cerrar el programa | |
| `8.8.8.8` | «8.8.8.8 no figura en la lista de equipos autorizados del laboratorio.» | |
| Opción 6 sin la variable de entorno | Explica que el administrador debe autorizar los equipos; no pide datos ni escribe | |

**Procedimiento B: lista blanca inválida**
1. Hacer una copia de `config/equipos_autorizados.txt`.
2. Agregar la línea `192.168.56.0/24` y ejecutar la opción 4 o 7.
3. **Restaurar la copia.**

*Esperado:* el programa indica el número de línea, explica que no se admiten redes ni rangos y no prueba nada.

**Procedimiento C: permisos**
1. Sin `sudo`, ejecutar la opción 3. *Esperado:* los procesos de otros usuarios aparecen como «no disponible».
2. Sin `sudo`, ejecutar `chmod 555 logs` y luego cualquier opción del menú.
   *Esperado:* el menú avisa una sola vez «No se pudo escribir el registro» y continúa.
3. **Restaurar:** `chmod 755 logs`.

| Resultado obtenido (A) | |
|---|---|
| **Resultado obtenido (B)** | |
| **Resultado obtenido (C)** | |
| **Evidencia** | Capturas de cada caso |
| **¿Cumple?** | ☐ Sí  ☐ No |

---

## Prueba 12 · Las funciones de evaluación no modifican las configuraciones del sistema
**Requisitos cubiertos:** alcance («no modificar automáticamente las configuraciones de seguridad»).

**Objetivo:** demostrar que el módulo es de solo lectura sobre el sistema.

**Procedimiento**
1. Guardar el estado inicial:
   ```bash
   sha256sum config/equipos_autorizados.txt > /tmp/antes.txt
   ip addr > /tmp/ip_antes.txt; ip route > /tmp/ruta_antes.txt
   ss -tln > /tmp/ss_antes.txt
   ```
2. Ejecutar el menú y usar las opciones **1, 2, 3, 4 y 5**.
3. Comparar:
   ```bash
   sha256sum -c /tmp/antes.txt
   ip addr | diff /tmp/ip_antes.txt -
   ip route | diff /tmp/ruta_antes.txt -
   ss -tln | diff /tmp/ss_antes.txt -
   ls -l logs/
   ```

**Resultado esperado:** `sha256sum -c` indica **OK**, y los tres `diff` no muestran diferencias
(interfaces, rutas y puertos idénticos). El único archivo que cambia es `logs/diagnostico_red.jsonl`.
La única función que escribe en `config/` es la opción 6, que es una decisión del administrador,
está deshabilitada por defecto y solo agrega una IP tras reescribirla para confirmar.

| Resultado obtenido | |
|---|---|
| **Evidencia** | Captura de `sha256sum -c`, los tres `diff` vacíos y `ls -l logs/` |
| **¿Cumple?** | ☐ Sí  ☐ No |

---

## Pruebas automáticas (apoyo)
```bash
python3 -m unittest discover -s tests -v
```
**Resultado esperado:** `Ran 50 tests ... OK`. Estas pruebas verifican, entre otras cosas, que una
IP no autorizada o pública se rechaza sin generar tráfico y que los analizadores de `ip`, `ss`,
`/proc/net/tcp`, `netstat` y PowerShell interpretan bien salidas de ejemplo. Adjunte la captura
como evidencia complementaria; **no reemplaza** las pruebas manuales de arriba.

| Resultado obtenido | |
|---|---|
| **Evidencia** | Captura del resultado final |
