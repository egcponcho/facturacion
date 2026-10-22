# Integraciones con ERP y otros sistemas

**Dónde:** *Configuración → Integraciones*. Permisos:

- `integraciones.ver`: ver la configuración y la bitácora.
- `integraciones.configurar`: crear integraciones y mapeos.
- `integraciones.ejecutar`: intercambiar datos. Además pide el permiso de la entidad: `oc.importar` para OCs y `factura.ver` para facturas.

La capa de integración está separada del núcleo (`backend/app/modulos/integraciones`):

- El núcleo no conoce ningún ERP.
- Todo lo que entra pasa por los mismos servicios, validaciones y permisos que una carga hecha a mano.

## Qué hay implementado y probado

| Pieza | Estado |
|---|---|
| **Adaptador «Archivo de hoja de cálculo»** (CSV o Excel) | Implementado y probado (`tests/test_integraciones.py`). Parámetros: <ul><li>fila de encabezados;</li><li>separador del CSV;</li><li>formato de salida (CSV o XLSX).</li></ul> |
| **Adaptador JSON** | Implementado y probado. Lee una lista de objetos o un objeto con la lista en `filas`, `items`, `data` o la clave que se configure. |
| **Entrada de órdenes de compra** | Implementada y probada. Reutiliza la clasificación y la aplicación del importador de OCs: deduplicación por OC, liberaciones, recetas de empaque e historial. |
| **Salida de facturas finalizadas** | Implementada y probada. Una fila por línea de factura. |
| Adaptadores propios de un ERP (SAP, Oracle, Dynamics, Odoo…) y conexión directa por API | **No implementados.** Cualquier ERP que exporte o importe CSV, Excel o JSON se conecta configurando un mapeo. Una conexión directa necesita un adaptador nuevo con el contrato de `adaptadores.py`. |

## Cómo conectar un ERP nuevo

1. **Crear la integración.** Elegir un código, un nombre, el sistema (solo descriptivo) y el formato de archivo, con sus parámetros.
2. **Mapear los campos** de cada entidad (*Mapear campos*). Por cada campo del sistema se indica:
   - **Nombre del campo externo:** la columna o clave en el sistema externo. Si se deja vacío, se busca el nombre interno.
   - **Valor por defecto**, solo en entrada: para lo que el archivo no trae. No se permite en los campos que identifican la línea (proveedor, OC, posición, artículo y cantidad).
   - **Códigos:** pares `EXTERNO=SISTEMA` separados por comas, para traducir valores. Por ejemplo, `APPROVED=C` en la liberación comercial. En salida se aplican al revés.
   - **Formato de fecha** del archivo, en entrada.

   Cada vez que se guarda, se crea una **versión nueva** y la anterior queda como histórica. Si nada cambió, no se crea versión.
3. **Entrada (Cargar archivo).**
   1. El contenido se lee con el adaptador.
   2. Se traduce con el mapeo vigente.
   3. Se muestra una **vista previa** con las filas nuevas, cambiadas, sin cambio, en conflicto y con error, más las filas rechazadas por faltar datos obligatorios.
   4. Nada se aplica hasta pulsar *Aplicar*.
4. **Salida (Generar archivo).** Arma el archivo con las facturas finalizadas, con los nombres y códigos externos. Con *Solo lo no enviado*, no repite las que ya salieron por esa integración.

## Garantías

- **Sin duplicados.**
  - Se guarda la huella (sha256) de cada contenido: el mismo archivo no se aplica dos veces y la segunda carga responde 409 con la ejecución anterior.
  - Aplicar dos veces la misma ejecución devuelve el resultado de la primera.
  - Las rutas de escritura aceptan `Idempotency-Key`.
- **Trazabilidad.** Cada intercambio queda en `integracion_ejecuciones` con quién lo hizo, cuándo, el archivo, la versión del mapeo, el resumen y los errores por fila. También queda en el historial de la integración.
- **Referencias externas.** `referencias_externas` guarda el identificador de cada registro en el sistema externo: «proveedor/OC» para las OCs y el número para las facturas. Es único en los dos sentidos por integración y entidad.
- **Aislamiento.** Todas las tablas son de la organización, con RLS en PostgreSQL y llaves de coherencia de organización. Ver la migración `0090`.

## Agregar una entidad o un adaptador

- **Entidad:** declarar en `entidades.py` sus campos internos, sus direcciones, el permiso del núcleo y su función de previa y aplicación (entrada) o de armado de filas (salida). Siempre se llama a un servicio del núcleo; nunca se escribe directo en las tablas.
- **Adaptador:** una clase con `codigo`, `nombre`, `parametros`, `leer()` y `escribir()`, registrada en `REGISTRO`. Necesita sus propias pruebas antes de anunciar compatibilidad.
