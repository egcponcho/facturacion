# Reestructuración · Informe final

**Fecha:** 22/10/2026 · **Rama:** `claude/bold-lovelace-iwx2wa`. Va desde `bcd7ee3` (fase 1) hasta el commit de este informe, sobre la base `535abcb`.

Este informe sigue los trece puntos pedidos. Los códigos (`G-01`, `D-01`…) remiten a [`01-diagnostico.md`](01-diagnostico.md) y las decisiones de diseño, a [`02-arquitectura.md`](02-arquitectura.md).

**Estado de cada punto:**

- **Hecho:** se implementó y se probó como dice el apartado 10.
- **Pendiente:** no se hizo, y el apartado 12 explica por qué.
- **Decisión tuya:** necesita que elijas una alternativa antes de tocar datos.

---

## 1. Diagnóstico

El inventario completo y los 26 hallazgos están en [`01-diagnostico.md`](01-diagnostico.md).

**Resumen.** El sistema ya tenía bien resuelto:

- la autorización en el servidor;
- la multiempresa con RLS;
- la integridad por llaves compuestas;
- casi todos los catálogos como datos.

Los problemas reales eran cuatro:

1. **Supuestos de un rubro y de un ERP en el código.** Filtros de estilo, color y talla; códigos de SAP 300/301/304 y C/P; SAC, DAI y NIT/RUC fijos en los documentos.
2. **Ninguna capa de integración** con sistemas externos.
3. **Módulos sin portada propia.** Los tableros vivían en Análisis y Configuración no tenía portada.
4. **Interfaz sin escala tipográfica,** con código sin uso.

## 2. Arquitectura

Está detallada en [`02-arquitectura.md`](02-arquitectura.md). Tiene tres capas:

| Capa | Qué guarda |
|---|---|
| **Núcleo** | Conceptos estables y tipados: OC, factura, lista de empaque, embarque, producto y variante, etiqueta. |
| **Configuración de la empresa** | Catálogos, atributos, reglas, nombres aduaneros y módulos. Son datos por `organizacion_id`. |
| **Integración** | El módulo `modulos/integraciones`. El núcleo no lo importa; la integración llama a los servicios del núcleo. |

## 3. Módulos

| Módulo | Abre en | Operación | Configuración propia |
|---|---|---|---|
| Compras | **Resumen** (`/compras/resumen`) **(nuevo)** | Órdenes de compra, carga de OCs | Proveedores y sociedades |
| Facturación | **Resumen** (`/facturacion/resumen`) **(nuevo)** | Facturas y listas de empaque, recetas, plantillas | Tipos de empaque y numeración |
| Logística | **Resumen** (`/logistica/resumen`) **(nuevo)** | Embarques, existencias, seguimiento, lead times | Lugares y transportistas |
| Productos | Resumen (ya existía) | Catálogo; ficha con las pestañas nuevas **Uso** y **Empaque** | Configuración de productos |
| Etiquetas | Imprimir | Diseños | Configuración de etiquetas |
| Análisis | Indicadores generales | Reportes | — |
| Configuración | **Portada (nueva)** | Empresa, usuarios y accesos, integraciones **(nuevo)**, países, organizaciones | La portada enlaza también la configuración de cada módulo |

Los resúmenes de módulo reutilizan el tablero de indicadores que ya existía (`seguimiento/indicadores.py`), con sus periodos, metas y selección por rol. No se creó un tablero paralelo. Análisis ya no repite los tableros que ahora están en su módulo, y los enlaces antiguos `/tableros/<módulo>` redirigen al resumen.

## 4. Cambios en la base de datos

| Migración | Qué hace | Datos existentes | Vuelta atrás |
|---|---|---|---|
| `0088_nombres_aduaneros_por_pais` | Agrega `paises_arancel.nomenclatura` y `nombre_derecho`, y `paises.nombre_id_fiscal`. | Rellena SAC y DAI en los países que ya los mostraban fijos. Rellena el nombre fiscal de GT y SV (NIT), HN (RTN), NI y PA (RUC) y CR (Cédula jurídica). | Borra las columnas. |
| `0089_llaves_de_unidades` | Crea llaves foráneas `(organizacion_id, codigo)` para `unidades_medida.base` y `atributos_variante.unidad` (D-03). | Los códigos huérfanos quedan en nulo y la migración informa cuántos eran. **No borra filas.** | Quita las llaves. Probada la subida, la bajada a 0087 y otra subida. |
| `0090_integraciones_con_sistemas_externos` | Crea las tablas `integraciones`, `integracion_mapeos`, `referencias_externas` e `integracion_ejecuciones`, con RLS, llaves de coherencia `_org` y restricciones con nombre. | Agrega los permisos `integraciones.ver`, `.configurar` y `.ejecutar` a los roles de administrador de fábrica. Así lo hicieron 0070 y 0072. | Quita los permisos y las tablas. |

**No se eliminó** ninguna tabla ni columna con datos. Las columnas fijas `estilo`, `color` y `talla` siguen como compatibilidad de escritura (G-07 y D-02). La lectura ahora pasa por `maestros/variantes.py`.

## 5. Eliminado, con justificación

Para cada elemento se buscó su nombre en el servidor, las pruebas, los scripts, las migraciones y el frontend. También se revisaron los usos por decorador (rutas, eventos y validadores) y por `getattr`.

| Eliminado | Por qué |
|---|---|
| `frontend/src/componentes/ThOrden.vue` | Nadie lo importaba. `TablaDatos` lo reemplazó. |
| `frontend/src/componentes/SelectorColumnas.vue` | Nadie lo importaba. `TablaDatos` trae su propio selector. |
| `frontend/src/composables/useTabla.js` | Nadie lo importaba. |
| `frontend/src/composables/useColumnas.js` | Solo lo importaba `SelectorColumnas.vue`. |
| `config_motor`, `exigir_trazable`, `acuerdos_para`, `Catalogo.desde_json`, `digitos_pais`, `_inciso_ctx`, `_meses`, `_fecha_factura`, `oc_poca_holgura`, `dias_post_arribo` | Ninguna referencia. |
| `etiquetado/trabajos._soltar` | Ninguna referencia. Los estados finales del trabajo ya liberan el arriendo en la misma actualización, así que no se perdió ninguna liberación. |
| Opciones fijas 300/301/304 y C/P del filtro de liberación | Ahora vienen de `estados_liberacion` de la empresa (G-02). |
| Columna «Código de talla» del catálogo | Suponía un código de artículo de 11 dígitos de una empresa concreta. |

**Se conserva** `documentos/letras.numero_en_letras`: no tiene llamadas, pero sirve para el monto en letras, según la auditoría anterior.

## 6. Consolidaciones

- **Variante.** Hay una sola lectura de la variante de una línea, `variantes.de_linea`, que usan seguimiento y documentos. Hay un solo texto corto de variantes, `variantes.resumen` y `variantes.rango`; `productos.rango_tallas` queda como alias.
- **Aduana.** Los nombres de la nomenclatura, del derecho y de la identificación fiscal salen de un solo módulo, `documentos/aduana.py`, que usan la factura, la ficha, los exportes y el reporte de productos.
- **Integración.** La entrada de OCs reutiliza la clasificación y la aplicación del importador del núcleo (`ordenes._clasificar` y `aplicar_importacion`). No hay un segundo camino de escritura.
- **Tableros.** Un solo tablero (`TableroView`, prop `incrustado`) sirve para Análisis y para el resumen de cada módulo.
- **Portadas de configuración.** Las tarjetas salen a `componentes/PortadaConfig.vue`, que comparten Configuración y la configuración de productos.
- **Visibilidad.** La regla para mostrar un apartado (`visible` en `nucleo/modulos.js`) es la misma para el menú y para la portada.

## 7. Configuraciones nuevas

| Configuración | Dónde | Nivel |
|---|---|---|
| Nombre de la nomenclatura y del derecho arancelario | *Productos → Clasificación → Arancel → país* | Plataforma |
| Nombre de la identificación fiscal | Catálogo de países | Plataforma |
| Integraciones: adaptador y parámetros, mapeos versionados por entidad y dirección, códigos, valores por defecto y formato de fecha | *Configuración → Integraciones* | Empresa |
| Filtros de seguimiento por atributo de variante | Salen del catálogo de atributos, sin configuración extra | Empresa |
| Escala tipográfica (`--t-2xs` … `--t-3xl`) | `frontend/src/styles.css` | Instalación (diseño) |

**Revisado sin cambios (G-05).**

- La unidad `CJ` es el valor de fábrica solo cuando la empresa no marca otra unidad de compuesto.
- `USD` es la preferencia inicial de moneda de la organización y es editable.

Los dos quedan documentados como valores por defecto del núcleo.

## 8. ERP: previsto e implementado

| Pieza | Prevista | Implementada y probada |
|---|---|---|
| Modelo (integraciones, mapeos versionados, referencias externas, bitácora) | Sí | **Sí.** Migración 0090 y `tests/test_integraciones.py`. |
| Adaptador de hoja de cálculo (CSV y Excel) | Sí | **Sí** |
| Adaptador JSON | Sí | **Sí** |
| Entrada de órdenes de compra, con vista previa, aplicación y sin duplicados por huella | Sí | **Sí** |
| Salida de facturas finalizadas, con «solo lo no enviado» | Sí | **Sí** |
| Pantalla de configuración, carga, generación y bitácora | Sí | **Sí** (revisada en el navegador) |
| Adaptadores propios de SAP, Oracle, Dynamics u Odoo | No | **No.** No se declara compatibilidad con ningún ERP concreto. |
| Conexión directa por API o servicio web | No | **No.** Requiere un adaptador nuevo con el contrato de `adaptadores.py`. |
| Otras entidades: recepciones, maestros, embarques | No | **No.** Están descritas como trabajo futuro en `docs/INTEGRACIONES.md`. |

Cualquier ERP que exporte o importe CSV, Excel o JSON se conecta configurando un mapeo, sin código nuevo.

## 9. Interfaz y experiencia de uso

- **Escala tipográfica (U-01).** Nueve pasos con nombre. Se reemplazaron 509 tamaños escritos a mano en las vistas y en `styles.css`.
- **Colores fuera de los tokens (U-02).** Pasan a tokens semánticos en LeadTime, Producto y Perfil, y se ven bien en el tema oscuro.
- **Cada módulo abre en su resumen** (M-01 y M-02).
- **Configuración abre en una portada** (M-04). Agrupa en el orden en que conviene configurar: *Tu empresa*, *Referencias y conexiones*, *Configuración de cada módulo* y *Plataforma*. Cada tarjeta muestra cuántos registros hay y aparece solo con el permiso de su pantalla.
- **Datos maestros** muestra el nombre de la pestaña del módulo (por ejemplo, «Lugares y transportistas») en lugar de «Datos maestros» (U-05).
- **Ficha del producto.** Tiene las pestañas **Uso** (OCs, facturas y embarques, según el alcance del usuario) y **Empaque** (reglas candidatas en orden de precedencia y recetas en uso) (M-03).
- **Seguimiento.** Los filtros se generan por atributo de variante. Un producto químico filtra por concentración o envase, no por talla.

Se revisó en el navegador en escritorio (1400 px) y en celular (390 px), con usuario administrador y usuario interno: portada de Configuración, datos maestros, configuración de productos, Inicio, Facturas, Productos y Órdenes.

## 10. Pruebas y resultados

| Prueba | Comando | Resultado |
|---|---|---|
| Lint del servidor | `ruff check app tests` | Sin errores |
| Lint de la interfaz | `npx eslint src` | Sin errores |
| Compilación | `npx vite build` | Correcta |
| Idiomas | `pytest tests/test_i18n.py` y la extracción de claves | Pasa |
| Suite completa del servidor (SQLite) | `pytest -q`. Las pruebas arrancan la aplicación, que aplica todas las migraciones hasta 0090; `test_integridad_bd` comprueba restricciones y llaves. | **Primera corrida:** 728 pasan, 1 falla, 4 omitidas. Falló `test_api_docs`: faltaba la etiqueta «Integraciones». **Tras corregirla:** 729 pasan, 0 fallan, 4 omitidas. **Corrida final, con la corrección del conteo de familias (`1256a93`):** 729 pasan, 0 fallan, 4 omitidas. |
| Migraciones 0088, 0089 y 0090 | Subida, bajada y otra subida sobre la base de demostración | Correctas (pasos R3 a R5) |
| Recorrido del navegador | `node e2e/recorrido.mjs`: 4 usuarios × 2 anchos (1440 y 390 px), 59 a 63 pantallas cada uno | **Primera corrida:** 8 problemas, todos el mismo 403 de `/logistica/resumen` para los proveedores (apartado 11). **Tras corregirlo:** las 8 combinaciones sin problemas. |
| Etiquetado en el navegador | `node e2e/etiquetado.mjs` | **Sobre la base demo usada antes:** 3 fallas, por una familia `E2EWIZ` que dejó una corrida anterior. **Sobre una base demo nueva:** 42 de 43 bien. Falló «al terminar se crea la familia con lo elegido» por el conteo de productos (apartado 11). **Tras corregirlo:** 43 de 43, sin fallas. |

**PostgreSQL.** No se ejecutó en esta etapa porque no hay un servidor PostgreSQL en el entorno. Las políticas RLS de 0090 se escribieron con el mismo helper (`instalacion.esquema.rls`) que ya cubren las pruebas de aislamiento de las migraciones anteriores, pero **no se probaron sobre PostgreSQL**.

## 11. Errores corregidos

| Error | Causa | Corrección |
|---|---|---|
| La familia de etiquetado mostraba **0 productos** aunque tuviera productos asignados, o 1 en una familia cualquiera. Error previo a esta etapa: era la falla del asistente de familias reportada en la sesión anterior. | `Producto.familia_etiquetado_id` es una subconsulta, porque sale del grupo de producto. El conteo no tenía `FROM productos` y contaba una sola fila. | Se agregó `select_from(Producto)` en `etiquetado/familias._conteos`. Hay una prueba de regresión en `test_etiquetado_familias.py`: falla sin la corrección y pasa con ella. |
| El proveedor podía abrir `/logistica/resumen` por su dirección y recibía un 403 de la API. El recorrido lo detectó 8 veces: tnf y vans, en dos anchos. | Las rutas de resumen de R6 no tenían permiso de ruta. | Las rutas `/<módulo>/resumen` llevan el mismo permiso que su pestaña. |
| La prueba `test_ficha_aprobacion_y_documentos` fallaba. | En R3 la hoja «Sizes» del Excel de la ficha pasó a llamarse «Variants», y la prueba no se actualizó. | Se actualizó la prueba. Al probar R3 solo se corrieron las pruebas de documentos; por eso no se vio antes. |
| Se subió un commit con la prueba de idiomas fallando. | La traducción de «packs» era igual a la clave, y `tail` ocultaba el código de salida. | Se corrigió en `99e3b83`. Desde entonces, cada commit pasa por una verificación estricta (`set -euo pipefail`). |
| El orden de imports en el resumen de productos no pasaba ruff. | — | Se corrigió en `1cb8080`. |
| El administrador recibía 403 en Integraciones. | Los roles ya guardados no reciben los permisos nuevos solos. | La migración 0090 los agrega a los roles de administrador de fábrica. |
| El tablero incrustado mostraba «Sin indicadores» mientras cargaba. | La condición del estado vacío estaba mal. | Se corrigió la condición. |

## 12. Pendientes y riesgos

**Decisión tuya.** Estos tres puntos exigen migrar datos. Las alternativas están en `02-arquitectura.md` §6.

- **D-01.** Seis taxonomías para agrupar productos. Se recomienda la alternativa A.
- **D-04.** Terceros a medias.
- **Lengua de origen de los textos.** Hoy las claves están en inglés y la interfaz se muestra en español. Se recomienda mantenerlo.

Hasta que decidas, no se construye nada encima de esas estructuras. Las tablas de etiquetado anteriores (D-05) siguen y se retiran junto con D-01.

**Pendiente, sin depender de una decisión:**

- **U-03.** Ventanas emergentes largas en la lista de empaque (11), la factura (7), administración (7) y el embarque (6). El plan es pasarlas a paneles laterales por etapas, empezando por la lista de empaque.
- **U-04.** Vistas de más de 850 líneas: `PackingListView`, `ProductoView`, `TrabajoEtiquetasView` y `MantenimientoView`. Hay que dividirlas en componentes.
- **G-07 y D-02.** Retirar las columnas fijas `estilo`, `color` y `talla`. Hay que hacerlo en otra migración, cuando ninguna lectura las use. Antes hay que revisar las importaciones de OC y los reportes guardados.
- **Integración.** Faltan más entidades (recepciones, maestros, embarques), una conexión directa por API y una ejecución programada.
- **Infraestructura.** Las dependencias no tienen versión fija (`requirements.txt` usa `>=`), no hay integración continua y faltan las pruebas sobre PostgreSQL de esta etapa.
- **Pruebas de navegador.** Comparten la base demo y dependen de su estado. Una corrida que se corta a la mitad deja datos (la familia `E2EWIZ`) que hacen fallar la siguiente. Conviene que cada corrida empiece desde una base nueva.

**Riesgos:**

- Las instalaciones con países propios deben completar el nombre de su nomenclatura y de su identificación fiscal. Mientras no lo hagan, los documentos usan el rótulo genérico («HS code», «Tax ID»).
- Una integración aplica OCs con los mismos permisos que la carga manual. Un mapeo mal hecho puede cargar datos erróneos. La vista previa obligatoria y la bitácora lo mitigan, pero no lo impiden.

## 13. Despliegue en una empresa nueva

1. **Instalación.** Seguir `docs/PRODUCCION.md`:
   - definir `DATABASE_URL` (PostgreSQL), `SECRET_KEY`, `SEED_DEMO=0`, `CORS_ORIGINS`;
   - configurar el SMS de los dos pasos;
   - definir el primer administrador (`EMPRESA_NOMBRE`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TELEFONO`).

   Las migraciones corren solas al arrancar.
2. **Configuración → portada → Tu empresa:**
   - **Empresa:** nombre, marca, moneda, idioma, documentos, módulos en uso, campos propios, estados, terminología, aprobaciones y reglas.
   - **Usuarios y accesos:** roles (revisar qué datos oculta cada uno) y usuarios.
3. **Referencias:**
   - **Países:** confirmar el nombre de la identificación fiscal de cada país.
   - **Productos → Clasificación → Arancel:** cargar el arancel de los países destino, con su nomenclatura y su derecho.
4. **Configuración de cada módulo**, en el orden de la portada:
   1. Productos: familias, atributos de variante, escalas, marcas.
   2. Proveedores y sociedades.
   3. Lugares y transportistas, con los **estados de liberación con los códigos que manda el ERP**.
   4. Lead times.
   5. Tipos de empaque y numeración.
   6. Recetas de empaque.
   7. Etiquetas.
5. **Integraciones** (si hay ERP):
   1. Crear la integración con su formato.
   2. Mapear los campos y códigos de órdenes de compra y facturas.
   3. Hacer una carga de prueba **solo con vista previa**.
   4. Aplicar.
   5. Revisar la bitácora.

   Ver `docs/INTEGRACIONES.md`.
6. **Datos iniciales.** Cargar los catálogos por Excel desde cada pantalla de datos maestros, y luego productos y OCs.
7. **Verificación.** Cada módulo debe abrir en su resumen con indicadores, y la portada de Configuración no debe mostrar tarjetas «Sin registros» en lo que la empresa usa.
