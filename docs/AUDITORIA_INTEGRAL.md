# Auditoría integral del sistema: código, base de datos, UX/UI, datos maestros y operación logística

**Fecha:** 13/10/2026 · **Base auditada:** rama `claude/focused-cerf-5qb8tf`, commit `1be922a` · **Fase:** solo diagnóstico.

En esta fase no se modificó código, no se eliminaron archivos, no se alteraron datos reales y no se ejecutaron migraciones sobre ninguna base del repositorio. Todas las pruebas corrieron sobre bases SQLite temporales fuera del repositorio:

- `demo.db`: la demostración creada por el propio sistema con `SEED_DEMO=1`.
- `perf.db`: una copia consistente de `demo.db`, hecha con la API de respaldo de SQLite.

El único archivo nuevo es este informe.

Complementa, sin repetir, a [`AUDITORIA_KPIS.md`](AUDITORIA_KPIS.md) (indicadores, 87 cifras), [`INFORME.md`](INFORME.md) (59 hallazgos anteriores) y [`DIAGNOSTICO.md`](DIAGNOSTICO.md). Cuando un hallazgo ya está documentado allí, se cita y se indica si se reverificó.

## Cómo leer este informe

**Prioridad:**

| | Significado |
|---|---|
| **P0** | Crítico: pérdida o corrupción de datos, cálculo financiero incorrecto, acceso indebido o bloqueo grave. |
| **P1** | Alto: error importante de operación, relación incorrecta, flujo roto o integridad significativa. |
| **P2** | Medio: usabilidad, duplicación, rendimiento mejorable o estructura difícil de mantener. |
| **P3** | Bajo: limpieza, mejoras menores. |

**Naturaleza de cada hallazgo:**

| Marca | Significado |
|---|---|
| **[C] Confirmado** | Reproducido con datos o demostrado en el código. |
| **[R] Riesgo potencial** | El código lo permite, pero no se observó un daño en los datos. |
| **[D] Diseño** | Recomendación de estructura. |
| **[V] Validar** | Depende de una decisión del negocio que debe tomar el usuario. |

**Cada hallazgo indica:**

- **Ubicación:** `archivo:línea`.
- **Evidencia.**
- **Impacto.**
- **Solución propuesta.**
- **Verificación:** cómo comprobar que la corrección funciona.

---

## 1. Resumen del estado general del sistema

**Veredicto:** el sistema está bien construido en su núcleo técnico. Gestiona con fiabilidad el tramo OC → factura → packing list → embarque → arribo. **No está todavía preparado para cerrar la operación logística de principio a fin.**

**Puntos débiles:**

- **Recepción.** Es el eslabón más débil:
  - Se puede dar por recibida la mercancía sin contarla y sin el permiso de recepción.
  - Los conteos se sobrescriben.
  - Se aceptan cantidades imposibles.
- **Costos logísticos:**
  - No existen en el modelo.
  - Las cuentas por pagar en moneda extranjera guardan siempre tipo de cambio 1.
- **No hay inventario ni bodega de llegada.** El usuario los pidió como requisito.

**Lo que está bien y se debe conservar (verificado, no supuesto):**

- **Pruebas y verificaciones estáticas:**
  - 584 pruebas pasan (3 omitidas).
  - `ruff`, `alembic check`, `eslint` y `vite build` sin errores.
  - `PRAGMA foreign_key_check` vacío, `integrity_check` correcto.
- **12 invariantes de negocio se cumplen** en la demostración, antes y después de los escenarios de prueba (Anexo A):
  - Sin sobrefacturación ni sobreempaque.
  - Totales de documentos iguales a la suma de sus líneas.
  - Sin pagos por encima del documento.
- **Máquinas de estado centralizadas.**
  - Ubicación: `backend/app/core/estados.py`, con espejo en `frontend/src/nucleo/estados.js`.
  - El servidor rechaza las transiciones imposibles: arribo antes de la salida, salida sin carga, eventos con fecha futura, cancelar una OC con facturas activas (escenario S6).
- **Aislamiento por organización en tres capas:**
  - Columna `organizacion_id`.
  - Filtro global del ORM.
  - RLS en PostgreSQL.
- **Aislamiento entre proveedores verificado (S5):**
  - Vans no ve facturas de TNF (404).
  - Vans no ve documentos, pagos, terceros ni embarques (403).
- **Seguridad HTTP:**
  - Cabeceras: CSP, `X-Frame-Options: DENY`, `nosniff`.
  - Cookie de sesión `HttpOnly` + `SameSite=strict`.
  - Exigencia de `X-Requested-With` en la API.
  - Límite de intentos de inicio de sesión: 20 por IP cada 5 minutos, con 429 al alcanzarlo (comprobado).
  - Demostración solo con `SEED_DEMO`.
- **Recorrido de humo en navegador sin errores.** Cuatro usuarios × escritorio y celular × 44 a 47 pantallas: sin errores de JavaScript ni respuestas 4xx/5xx. El único error de consola es la fuente externa de Google (ver S-6).

**Hallazgos de esta auditoría:**

| Prioridad | Cantidad | Más relevantes |
|---|---:|---|
| P0 | 0 | No se encontraron. Los P0 de indicadores se corrigieron en `1be922a` y se reverificaron. |
| P1 | 7 | Recepción sin permiso (L-01); cantidades imposibles en recepción (L-02); conteos sobrescritos (L-03); tipo de cambio 1 en CxP (L-08); acciones ofrecidas que siempre fallan (U-01); inventario y bodega de llegada [V] (L-05); recepción por contenedor [V] (L-06). |
| P2 | 33 | Rendimiento por petición, acoplamiento entre dominios, lead time con fechas de captura, alertas duplicadas, modales largos, códigos SAP en el filtro, componentes de más de 1 000 líneas, etc. |
| P3 | 22 | Código muerto confirmado (16 elementos, contados como un hallazgo), documentación desfasada, accesibilidad menor, etc. |

**Respuesta a la pregunta central:** ¿puede gestionar sus operaciones de principio a fin?

| Tramo | Estado |
|---|---|
| Compras, facturación del proveedor, empaque y transporte hasta el arribo | **Sí.** |
| Recepción | **No con integridad suficiente.** |
| Costos | **No existen.** |
| Moneda de las cuentas por pagar | **No es fiable** fuera de USD. |

Ninguno de estos puntos exige reescribir módulos: son correcciones localizadas, salvo costos e inventario, que son funciones nuevas y deben decidirse con el usuario.

---

## 2. Inventario de módulos, pantallas, servicios, tablas y flujos

### 2.1 Totales

| Elemento | Cantidad | Cómo se contó |
|---|---:|---|
| Dominios de backend (`backend/app/modulos/*`) | 15 | Directorios. |
| Servicios Python (sin `api.py` ni `__init__`) | 97 | Archivos. |
| Rutas HTTP | 336 | `app.openapi()["paths"]`. `app.routes` no sirve con FastAPI 0.141. |
| Tablas | 126 | `Base.metadata.tables`. |
| Migraciones Alembic | 68 | `backend/alembic/versions`, de 0001 a 0068. |
| Archivos de prueba | 58 | `backend/tests/test_*.py`. |
| Vistas Vue (pantallas) | 30 | `modulos/*/vistas`. |
| Rutas del frontend | 40 | `frontend/src/router.js`. |
| Componentes Vue | 85 | `componentes/` más `modulos/*/componentes`. |

### 2.2 Dominios de backend

| Dominio | Responsabilidad | Endpoints | Tablas principales |
|---|---|---:|---|
| `acceso` | Sesión, dos pasos, usuarios, roles, permisos, visibilidad por proveedor, preferencias | 21 | `usuarios`, `roles`, `sesiones`, `desafios_dos_pasos` |
| `plataforma`, `empresa` | Organizaciones (multiempresa), campos propios, estados con etiqueta propia, adjuntos | 4 + 3 | `organizaciones`, `definiciones_campo`, `estados_documento`, `adjuntos` |
| `maestros` | Catálogos: proveedores, sociedades, centros, almacenes, países, puertos, marcas, tallas, monedas, unidades, incoterms… | 21 | 28 tablas en `modelos/maestros.py` |
| `productos` | Producto (ficha técnica y clasificación aprobada), versiones, fotos | 30 | `productos`, `clasificaciones_producto`, `partidas_pais`, `producto_versiones` |
| `clasificacion` | Árbol arancelario oficial, motor de clasificación, atributos, reglas, impuestos de importación, conocimiento | 90 | 26 tablas en `modelos/clasificacion.py` |
| `compras` | OC: creación, importación, aprobación, liberaciones, avance | 15 | `ordenes_compra`, `posiciones_oc`, `aprobaciones_oc`, `importaciones_oc` |
| `facturacion` | Factura comercial del proveedor contra OC | 17 | `facturas`, `factura_lineas`, `archivos` |
| `empaque` | Packing lists, cajas, plantillas, **recepción** | 23 | `packing_lists`, `pl_lineas`, `grupos_cajas`, `recepciones` |
| `transporte` | Embarques, unidades de carga, eventos, lead times configurables | 16 | `embarques`, `unidades_carga`, `eventos_embarque`, `reglas_leadtime` |
| `comercial` | Documentos económicos (ventas y cuentas por pagar), pagos, terceros, impuestos | 25 | `documentos`, `documento_lineas`, `pagos`, `aplicaciones`, `terceros` |
| `seguimiento` | Inicio, seguimiento, alertas, indicadores, lead times por OC | 20 | `alertas` (lee de todos) |
| `reportes` | Reportes configurables y guardados | 9 | `reportes` |
| `documentos` | PDF y Excel de factura y packing list | 0 | Se usan desde `facturacion` y `empaque`. |
| `comun` | Edición exclusiva, historial, tablas, normalización | 6 | `historial`, `ediciones`, `idempotencia` |

### 2.3 Pantallas

| Área | Rutas |
|---|---|
| Operación | `/`, `/ordenes`, `/ordenes/nueva`, `/ordenes/:id`, `/ordenes/:id/editar`, `/facturas`, `/facturas/:id`, `/packing-lists/:id`, `/transporte`, `/transporte/embarques/:id`, `/importar`, `/plantillas` |
| Productos y clasificación | `/productos`, `/productos/:id`, `/aranceles`, `/familias` |
| Comercial | `/comercial/documentos`, `/comercial/documentos/nuevo`, `/comercial/documentos/:id`, `/comercial/pagos`, `/comercial/terceros` |
| Análisis | `/seguimiento` (4 vistas), `/tableros/:modulo`, `/reportes`, `/leadtimes` |
| Configuración | `/mantenimiento` (catálogos), `/admin` (usuarios, roles, proveedores, flujo, bitácora), `/empresa`, `/plataforma`, `/perfil`, `/bienvenida`, `/login` |

### 2.4 Flujos

**Soportados**, verificados en código y con datos:

| Flujo | Recorrido |
|---|---|
| F1 · Orden de compra | Captura manual (asistente) o importación → aprobación (reglas) → liberación comercial y logística → disponible para facturar → cierre o cancelación. |
| F2 · Factura del proveedor | Se crea desde posiciones de OC con saldo → líneas con precio, motivo de cambio, partida y origen → finalizar. Al finalizar se crea un documento de cuentas por pagar. |
| F3 · Packing list | Contenido (filas de factura) → cajas (plantillas, cajas mixtas) → dimensiones y pesos → finalizar. |
| F4 · Embarque | Crear → unidades de carga → asignar PL finalizados → eventos en orden: recolección, salida (con datos obligatorios), tránsito, arribo, entrega, recepción. |
| F5 · Recepción | Por PL y por línea (cantidad recibida y dañada), o «sin novedad» con el evento RECEPCION del embarque. Ver §8.E. |
| F6 · Cuentas por pagar y pagos | Documento `FACTURA_PROVEEDOR` emitido → vencimientos → pagos con aplicación parcial → estado de cuenta del tercero. |
| F7 · Documentos comerciales de venta | Factura, notas de crédito y débito, cobros, documentos recurrentes. |
| F8 · Clasificación arancelaria | Ficha técnica → motor → aprobación → partida de 6 dígitos en OC y factura; incisos nacionales por país. |
| F9 · Seguimiento, lead times, indicadores y reportes | Sobre F1–F6. |

**No soportados**, sin código que los implemente:

- Inventario y existencias.
- Costos logísticos, landed cost y prorrateo.
- Trámite aduanero: DUCA, liberación con integración.
- Facturación electrónica: hay un campo de configuración sin integración.
- Devoluciones o reclamos al proveedor como documento.
- Recepción por bodega o ubicación física.

---

## 3. Archivos y componentes: conservar, corregir, refactorizar, consolidar, eliminar o verificar

**Método:** antes de marcar un elemento como prescindible se buscó en todas estas fuentes:

- Imports directos e indirectos.
- `router.js` (rutas dinámicas con `import()`).
- Registros globales en `main.js`.
- `backend/scripts`, `backend/tests` y `backend/alembic`.
- Decoradores (`@event.listens_for`, `@router`).
- Usos por `getattr` o `importlib`.

### 3.1 Migraciones históricas: **conservar todas**

| Elemento | Clasificación | Evidencia |
|---|---|---|
| `backend/alembic/versions/0001…0068` (68 archivos) | **Conservar** | `app/instalacion/migraciones.py:48-57` (`actualizar`) ejecuta `command.upgrade(cfg, "head")` en **cada arranque**, en la demostración y en producción. Una base anterior a Alembic se marca en `0001` y sube desde ahí. Eliminar cualquier migración rompe la actualización de instalaciones existentes y la cadena `down_revision`. `alembic check` confirma que los modelos y la cabeza coinciden. |
| `app/instalacion/esquema.py` (`rls`, `sin_violaciones`) | **Conservar** | Sin referencias desde `app/`, pero las importan las migraciones 0052, 0053, 0061 y 0062. Eliminarlo rompe esas migraciones. |
| `app/modulos/clasificacion/version_config.py` (`_confirmada`, `_deshecha`) | **Conservar** | Sin llamadas directas: son escuchas `@event.listens_for` de la sesión, que invalidan la caché del motor. |

### 3.2 Eliminar con seguridad (P3, código muerto confirmado)

En todos los casos la consecuencia de eliminar es ninguna funcional. Se pierde código no usado; la verificación es que `npm run lint`, `npm run build`, `pytest` y `npm run e2e` sigan pasando.

**Frontend:**

| Elemento | Evidencia |
|---|---|
| `frontend/src/componentes/ThOrden.vue` | Ningún import ni registro global. `TablaDatos` (44 usos) lo reemplazó. |
| `frontend/src/componentes/SelectorColumnas.vue` | Solo aparece en un comentario de `styles.css:555`. `TablaDatos` trae su propio selector. |
| `frontend/src/composables/useTabla.js` | Ningún import. |
| `frontend/src/composables/useColumnas.js` | Solo lo importa `SelectorColumnas.vue`, que también es código muerto. |

**Funciones de backend sin ninguna referencia**, buscadas en `app`, `scripts`, `tests` y `alembic`:

| Función | Nota |
|---|---|
| `modulos/clasificacion/atributos.py:389` `config_motor` | — |
| `modulos/clasificacion/oficial.py:456` `exigir_trazable` | — |
| `modulos/documentos/letras.py:90` `numero_en_letras` | **Antes de eliminarla, verificar** (ver P-04). Los documentos comerciales no tienen impresión y esta función podría servir para el monto en letras. |
| `modulos/maestros/acuerdos.py:24` `acuerdos_para` | — |
| `modulos/productos/ficha.py:183` `Catalogo.desde_json` | — |
| `modulos/productos/productos.py:68` `digitos_pais` | — |
| `modulos/productos/productos.py:554` `_inciso_ctx` | — |
| `modulos/seguimiento/dashboard.py:30` `_meses` | — |
| `modulos/seguimiento/dashboard.py:95` `_fecha_factura` | — |
| `modulos/seguimiento/metricas.py:113` `oc_poca_holgura` | — |
| `modulos/transporte/leadtimes.py:188` `dias_post_arribo` | — |
| `modulos/transporte/leadtimes.py:279` `estado_tiempo` | Duplica la lógica de `transporte.py:168` (`_riesgo`). Las 7 coincidencias del nombre son claves de diccionario, no llamadas. |

### 3.3 Corregir, refactorizar o consolidar

| Elemento | Acción | Prioridad | Motivo (detalle en las secciones indicadas) |
|---|---|---|---|
| `frontend/src/modulos/seguimiento/vistas/SeguimientoView.vue:174-179` | Corregir | P2 | Códigos SAP fijos (C/P, 300/301/304) en un filtro. El backend ya los hace configurables (G-01). |
| `backend/app/modelos/maestros.py:83,106,378` | Corregir | P3 | Docstrings que hablan de «SAP» en una plataforma genérica. |
| `docs/clasificacion/arquitectura.md:24-36` | Corregir | P3 | Cita archivos que ya no existen: `data/incisos_base.json`, `sac_base.json`, `motor_atributos.json`, `motor_reglas.json`, `motor_tecnico.json`. |
| `backend/scripts/sieca/LEEME.md` | Corregir | P3 | Menciona la «base ADOC» (empresa concreta). |
| `backend/requirements.txt` | Corregir | P2 | Todas las versiones con `>=`: compilaciones no reproducibles. Todas las dependencias se usan. |
| `modulos/comercial/documentos.py:89-92` | Corregir | P3 | Import a mitad del archivo con `# noqa: E402`. |
| `PackingList.asignacion` (`modelos/empaque.py:51`) | Consolidar / verificar | P3 | El comentario dice `TENTATIVA \| CONFIRMADA`, pero el código solo asigna `CONFIRMADA` o `None`, junto con `unidad_carga_id` (`transporte.py:767,786`). Es redundante con `unidad_carga_id IS NOT NULL`. **Antes de retirarla**, ejecutar `SELECT DISTINCT asignacion FROM packing_lists` en producción. |
| `ProductoView.vue` (1 118 líneas), `PackingListView.vue` (1 107), `MantenimientoView.vue` (817), `FacturaView.vue` (796), `ArancelesView.vue` (766), `EmbarqueView.vue` (706) | Refactorizar | P2 | Ver A-04. |
| `maestros/catalogos.py` (1 669), `productos/productos.py` (1 303), `empaque/packing.py` (1 286), `clasificacion/motor_clasificacion.py` (1 268), `compras/ordenes.py` (1 145), `facturacion/facturas.py` (1 037) | Refactorizar | P2 | Ver A-04. |
| `frontend/e2e/recorrido.mjs` | Conservar | — | Es la única prueba de navegador, y útil. Falta en CI (S-05). |

### 3.4 Pendiente de verificación: funciones a medio implementar

Decidir con el usuario si se completan o se retiran. Retirar una tabla exige una migración nueva, nunca borrar migraciones.

| Elemento | Evidencia | Prioridad |
|---|---|---|
| Catálogo `tipos_cambio` (`TipoCambio`) | Se edita en Mantenimiento, pero ningún servicio lo lee (ver L-08). | P1 por su efecto en CxP |
| `documento_envios` (`EnvioDocumento`) | Ningún servicio lo escribe ni lo lee. | P3 [V] |
| `plantillas_documento` (`PlantillaDocumento`) | Catálogo editable sin efecto en ninguna impresión. | P3 [V] |
| `configuracion_fiscal.proveedor_electronico` | Campo sin ninguna integración de facturación electrónica. | P3 [V] |
| Impresión de documentos comerciales | No existe ningún endpoint PDF para `documentos`, a diferencia de factura y PL. | P2 [V] |
| `reglas_impuesto` (DAI, IVA de importación por inciso) | Se guarda y se audita (`clasificacion/nacional.py:260`, `integridad.py:189`), pero no se usa en ningún cálculo de costo. Ver §8.G. | P3 [D] |

---

## 4. Arquitectura y calidad del código

**Lo que está bien:**

- Capas claras: `core/` (configuración, base de datos, dinero, estados, organización), `modelos/`, `esquemas/` y `modulos/<dominio>/` con `api.py` delgado y servicios.
- Las reglas importantes se aplican en el servidor y no dependen de la interfaz. Se comprobó llamando a la API directamente: S1, S4, S5 y S6.
- Las máquinas de estado no se repiten: `core/estados.py` y su espejo `nucleo/estados.js`.

**A-01 · P2 [C] · Dependencias circulares entre dominios**

- **Evidencia:** grafo de imports de `app/modulos/*`.
  - Hay 19 pares bidireccionales, entre ellos: acceso↔productos, acceso↔comun, comun↔{empaque, facturacion, maestros, productos, transporte}, documentos↔{empaque, facturacion, maestros, productos}, empaque↔facturacion, empaque↔transporte, facturacion↔productos, facturacion↔seguimiento, maestros↔productos, clasificacion↔productos, compras↔maestros y acceso↔empresa.
  - Hay 243 imports dentro de funciones, usados para esquivar los ciclos. Ejemplos: `transporte.py:490` importa `empaque.packing.recibir_sin_novedad`, y `packing.py:1063` importa `transporte.completar_recepcion`.
  - Casos especialmente inadecuados:
    - `acceso/permisos.py:182` importa `productos.flujo.captura_permitida`: el dominio de permisos conoce reglas de productos.
    - `modelos/maestros.py:249` importa desde `modulos`: la capa de modelos depende de servicios.
- **Impacto:** cambios en un dominio rompen otro sin aviso. Los ciclos solo se resuelven en tiempo de ejecución.
- **Solución:** no reescribir. Mover a `core/` o a un `comun/` sin dependencias hacia arriba lo que ambos lados necesitan:
  - Recepción y estado de embarque, a un servicio `recepcion` único (ver §12).
  - Visibilidad y permisos, sin conocer productos: `productos` registra su regla en `acceso`, y no al revés.
- **Verificación:** prueba de arquitectura en `tests/` que construya el grafo y falle si aparece un par bidireccional nuevo. Lista permitida decreciente.

**A-02 · P2 [C] · Funciones privadas importadas entre módulos**

- **Evidencia:**
  - `empaque/packing.py:1128` usa `_info_transporte`.
  - `clasificacion/impacto.py:15` usa `_producto`.
  - `maestros/catalogos.py:1613` usa `_norm` y `_texto`.
  - `reportes/fuentes.py:28` usa `_emb`, `_fact`, `_oc` y `_prod`.
  - `comun/edicion.py:107,110` usa `_embarque` y `_producto`.
  - `plataforma/organizaciones.py:97` usa `_hash`.
  - `seguimiento/dashboard.py:21` usa `_lista_para_transporte`.
  - `seguimiento/seguimiento.py:24,413` usa `_riesgo` y `_tipo`.
- **Impacto:** el contrato entre módulos es implícito, y un renombre interno rompe otros dominios.
- **Solución:** publicar esas funciones (sin `_`) en el módulo dueño o moverlas a `comun`.
- **Verificación:** regla de ruff o prueba que prohíba `from app.modulos.x import _y` fuera del dominio `x`.

**A-03 · P2 [C] · Lógica de negocio duplicada con criterios distintos para el mismo nombre**

- **Evidencia:**
  - `compras/ordenes.py:80-90`: el «importe facturado» de la lista de OC usa `cantidad × precio de la OC` e **incluye facturas en borrador y en corrección**.
  - `seguimiento/indicadores.py:198` (`importe_facturado`): usa `cantidad × precio de la factura`, solo facturas **FINALIZADAS**.
  - `facturacion/cantidades.facturado_por_posicion` y `seguimiento/metricas._facturado_por_posicion` usan el mismo criterio (`estado != CANCELADA`) duplicado.
- **Impacto:** dos cifras con el mismo nombre que no coinciden cuando hay borradores o cambios de precio.
- **Solución:**
  - Renombrar la de la OC a «comprometido en facturas (a precio OC)», o alinearla al criterio del indicador.
  - Dejar una sola función de cantidades facturadas en `facturacion/cantidades.py` y que `metricas` la use.
- **Verificación:** con una OC que tenga una factura en borrador con precio cambiado, la lista de OC y el tablero deben mostrar la misma cifra con el mismo nombre, o nombres distintos.

**A-04 · P2 [C] · Componentes y servicios demasiado grandes**

- **Evidencia:**
  - Seis vistas superan 700 líneas y seis servicios superan 1 000 (§3.3).
  - En `PackingListView.vue` conviven en una sola vista el contenido, las cajas, las dimensiones, la recepción, 10 modales y la exportación.
- **Impacto:** cambios lentos y riesgo de regresión.
- **Solución:** dividir por pestaña o sección en subcomponentes, en el mismo directorio y sin cambiar el comportamiento. Ejemplos: `PLContenido.vue`, `PLCajas.vue`, `PLRecepcion.vue`. En el backend, separar `packing.py` en `packing.py` (documento), `cajas.py` y `recepcion.py`.
- **Verificación:** las mismas pruebas y `npm run e2e` pasan sin cambios; ningún archivo supera unas 600 líneas.

**A-05 · P2 [C] · Estilos y tablas fuera del sistema visual**

- **Evidencia:**
  - 67 atributos `style=""` en línea.
  - 21 `<table>` hechas a mano en 13 archivos, frente al componente `TablaDatos`.
- **Impacto:** inconsistencias visuales y en el móvil (U-06).
- **Solución:** migrar las tablas de captura a las cuadrículas comunes y las de consulta a `TablaDatos`; los estilos, a clases del sistema.
- **Verificación:** `grep -c 'style="'` tiende a cero; el recorrido e2e sigue sin errores.

**A-06 · P2 [C] · Valores fijos de un ERP concreto en el frontend**

- **Evidencia:**
  - `SeguimientoView.vue:174-179`: `<option value="C">`, `"P"`, `"300"`, `"301"`, `"304"`.
  - El backend los lee del catálogo `EstadoLiberacion` (`compras/liberaciones.py`).
- **Impacto:** otra empresa configura códigos distintos y el filtro no los ofrece, o filtra por códigos inexistentes.
- **Solución:** cargar las opciones desde el catálogo de liberaciones.
- **Verificación:** al cambiar un código en Mantenimiento → Liberaciones, la opción cambia en el filtro de Seguimiento.

**A-07 · P3 [C] · Advertencia del ORM en cada consulta filtrada fuera de las pruebas**

- **Evidencia:**
  - `core/organizacion.py:114` emite `SAWarning: Unmanaged access of declarative attribute organizacion_id from non-mapped class DeOrganizacion`.
  - Apareció al llamar servicios con la base de demostración.
- **Impacto:** ruido en los registros. Una futura versión de SQLAlchemy podría convertirlo en error.
- **Solución:** en el criterio, usar el atributo de la clase mapeada (`lambda cls: cls.organizacion_id == org` registrado por cada subclase) o `include_aliases` con `propagate_to_loaders` según la documentación de `with_loader_criteria`.
- **Verificación:** `python -W error::sqlalchemy.exc.SAWarning -m pytest` pasa.

---

## 5. Deficiencias de UX/UI por pantalla y propuesta unificada

**Método:**

- Playwright con Chromium sobre la demostración, en 3 anchos (1440 escritorio, 820 tableta, 390 celular) y 33 rutas con 3 roles (interno, administrador, proveedor). 99 capturas en total.
- En cada pantalla se midió automáticamente:
  - Desborde horizontal.
  - Elementos fuera de pantalla.
  - Objetivos táctiles menores de 32 px.
  - Fuente mínima.
  - Botones sin nombre accesible.
  - Campos sin etiqueta.
  - Altura total.
  - Errores de API.
- Además, revisión visual de las capturas clave y del código de las vistas.

**Resultado medido:**

- **Positivo:**
  - Ninguna pantalla tiene desborde horizontal ni elementos fuera de pantalla en los 3 anchos.
  - No hay botones sin nombre ni campos sin etiqueta.
  - No hay errores de API.
  - Tiempo de carga entre 1,4 y 2,4 s en la demostración.
- **Por corregir:** ver U-06.

**U-01 · P1 [C] · Acciones visibles que el servidor siempre rechaza**

- **Ubicación:**
  - Backend: `empaque/packing.py:1278-1279` y `facturacion/facturas.py:974-975`.
  - Frontend: `PackingListView.vue:551-552`.
- **Evidencia:**
  - `puede.reabrir` y `puede.cancelar` solo miran el estado del documento y el permiso.
  - El servidor, en cambio, rechaza:
    - **Reabrir un PL** que viaja: `packing.py:1011`.
    - **Cancelar un PL** en una unidad: `packing.py:1033`.
    - **Reabrir una factura** con PL viajando o con pagos: `facturas.reabrir` y `proveedores.py:62`.
    - **Cancelar una factura** con PL confirmados: `facturas.py:663-668`.
  - En la captura `interno_1440_packing-lists_1.png`, el PL-001 de EMB-0001 (ya **Recibido**) ofrece «Reabrir para corregir» y «Cancelar PL», que el servidor rechaza por las guardas citadas.
  - En S4, las mismas acciones sobre su factura, ofrecidas igual por `puede.*`, respondieron 409 (`embarque_cerrado`, `pl_en_transporte`).
- **Impacto:** el usuario intenta, escribe un motivo y recibe un error. Erosiona la confianza en los estados y genera consultas al equipo interno.
- **Solución:** calcular `puede.*` con las **mismas** funciones de guarda que la acción, por ejemplo `motivo_no_reabrir(pl) -> str | None`. Devolver también el motivo, para mostrar el botón deshabilitado con explicación («Viaja en EMB-0001: quítelo de la unidad primero»).
- **Verificación:** prueba de API que, para un PL en un embarque no planificado, compruebe `puede.reabrir == False`, que lleve motivo y que la acción responda 409. Repetir para una factura con pagos.

**U-02 · P2 [C] · «Necesita su atención» no muestra las diferencias de recepción, y las muestra con un título equivocado**

- **Ubicación:** `frontend/src/modulos/inicio/vistas/DashboardView.vue:210-211`.
- **Evidencia:**
  - Captura `interno_1440_inicio.png`: «Nada necesita su atención».
  - Al mismo tiempo hay 4 alertas `recepcion_diferencia`. Aparecen al pie, bajo «Alertas de importación — Conflictos encontrados al cargar órdenes de compra».
- **Impacto:** faltantes y daños, que exigen reclamar al proveedor, quedan escondidos y mal rotulados.
- **Solución:**
  - Las diferencias de recepción abiertas deben entrar en «Necesita su atención», con acceso al PL.
  - El panel de alertas se debe titular por tipo de alerta.
- **Verificación:** con una recepción con faltante, «Necesita su atención» muestra el elemento y no aparece «Nada necesita su atención».

**U-03 · P2 [C] · Procesos largos dentro de modales**

- **Evidencia:** conteo de campos por modal. Hay 70 `<Modal>` en 28 archivos.

  | Modal | Ubicación | Contenido |
  |---|---|---|
  | Edición de catálogo | `MantenimientoView.vue:620` | Campos dinámicos: 15 en la plantilla, más los definidos por la empresa; 2 tablas; 107 líneas. |
  | Genérico de artículo | `GenericoModal.vue:146` | 15 campos y 1 tabla de tallas. |
  | Tercero | `TercerosView.vue:156` | 12 campos. |
  | Registrar pago con aplicación a varios documentos | `PagosView.vue:179` | Tabla de documentos. |
  | Nueva regulación, regla de impuesto, categoría | `PanelRegulaciones.vue:112`, `PanelImpuestos.vue:111`, `PanelDominios.vue:166` | 10 a 13 campos. |

- **Impacto:**
  - En el celular, el modal ocupa toda la pantalla sin navegación.
  - Perder el foco o tocar fuera descarta el trabajo.
  - No se puede consultar otra pantalla mientras se captura.
- **Solución (patrón, ver §5.2):**
  - Artículo, genérico y tercero: **pantalla de detalle con secciones** o **panel lateral** de ancho completo en el móvil.
  - Pago con aplicaciones: **dos pasos** (datos del pago → aplicar a documentos → revisar → confirmar).
  - Modales solo para confirmar, motivo, un dato o una acción corta.
- **Verificación:** ningún modal tiene más de 6 campos ni una tabla editable. En el móvil, el borrador sobrevive a una navegación accidental (guardado local de borrador).

**U-04 · P2 [C] · Objetivos táctiles pequeños en celular y tableta**

- **Evidencia:** controles menores de 32 px a 390 px de ancho:
  - Inicio: 14 de 51.
  - Órdenes: 49 de 74.
  - Seguimiento: 52 de 78.
  - Aranceles: 46 de 149.
  - Empresa: 83 de 130.
  - En la tabla de OC del móvil hay casillas, flechas de expandir, «+» y «Factura» en una misma fila (captura `interno_390_ordenes.png`).
- **Impacto:** toques equivocados, por ejemplo marcar una OC en lugar de expandirla. WCAG 2.2 AA (2.5.8) pide al menos 24 × 24 px; la práctica táctil, 44 px.
- **Solución:** en `@media (pointer: coarse)`, alto mínimo de 40 px para botones, casillas y enlaces de acción, y área de toque ampliada con `padding` o `::after`. En las filas de tabla del móvil, una sola acción principal por fila y las demás en un menú.
- **Verificación:** la medición automática (script en el Anexo B) devuelve 0 controles menores de 24 px y menos del 10 % menores de 40 px a 390 px.

**U-05 · P2 [C] · Lead times: encabezados numéricos sin significado**

- **Ubicación:** `TableroLeadTimes.vue` (captura `interno_1440_seguimiento_vista_leadtimes.png`).
- **Evidencia:** las columnas de etapas se titulan «1», «2», «3», «4».
- **Impacto:** hay que deducir qué etapa es cada número.
- **Solución:** nombre corto de la etapa (Liberación, Despacho, Tránsito, Puerto…) y número como apoyo.
- **Verificación:** visual; los encabezados se leen sin abrir la leyenda.

**U-06 · P3 [C] · Accesibilidad y formato**

- Fuente mínima de 9 a 10 px en todas las pantallas (etiquetas de KPI y subtítulos). Se recomiendan al menos 12 px.
- Las páginas de detalle (`/facturas/:id`, `/packing-lists/:id`, `/transporte/embarques/:id`, `/productos/:id`, `/ordenes/:id`, `/comercial/documentos/:id`) **no tienen `<h1>`**. El lector de pantalla no anuncia el documento.
- El formato de fecha por omisión es `MM/DD/YYYY` (`stores/preferencias.js:8`), aunque la interfaz esté en español y la empresa esté en Centroamérica. Es una preferencia del usuario: el valor por omisión debería salir del idioma o de la organización.
- **Verificación:** medición automática; `document.querySelector('h1')` presente en todas las rutas.

**U-07 · P3 [C] · Datos de la demostración en inglés en una interfaz en español**

- **Evidencia:** «San Salvador bonded warehouse», «Accounts payable», «El Salvador distribution center».
- **Impacto:** solo en la demostración, pero confunde al evaluar la interfaz.
- **Solución:** sembrar la demostración en el idioma de la organización.

### 5.1 Revisión por pantalla

| Pantalla | Qué está bien | Qué mejorar |
|---|---|---|
| Inicio `/` | Indicadores con contexto, «Siguientes pasos» accionables | U-02 (recepción fuera de «Necesita atención»). En el celular, 3 320 px de alto: priorizar «Necesita atención» y plegar paneles. |
| Órdenes `/ordenes` | Paso 1 de 3 de facturación explícito, filtros en panel, carrito | U-04 (fila con 4 controles en el celular). El total del carrito suma importes de monedas distintas (`OrdenesView.vue:304`, C-02). |
| Asistente de OC `/ordenes/nueva` | Pasos guiados | — |
| Factura `/facturas/:id` | Progreso por pasos (líneas → datos → empaque → finalizar → embarque), requisitos visibles | U-01 (reabrir y cancelar ofrecidos con PL viajando). |
| Packing list `/packing-lists/:id` | Progreso, partes (facturar a, notificar, destino) completas | U-01; A-04 (vista de 1 107 líneas). La recepción es una pestaña del PL, pero no se puede recibir por contenedor (L-06). |
| Embarque `/transporte/embarques/:id` | Línea de hitos clara, bloqueo explicado («Carga cerrada»), llenado por volumen y peso | El evento «Recepción» se ofrece a quien solo gestiona transporte (L-01). |
| Seguimiento | 4 vistas, periodo, origen y proveedor | U-05; A-06 (códigos SAP en el filtro de OC). |
| Productos y ficha | Bandeja por estado, ficha por secciones | Ficha de 4 651 px en el celular: índice de secciones fijo. |
| Mantenimiento | Un catálogo por vez | U-03 (edición en modal con campos dinámicos). |
| Comercial (documentos y pagos) | Estados de documento y cobro separados | U-03 (pago con aplicaciones en modal). Sin impresión de documento (§3.4). |
| Empresa `/empresa` | Toda la configuración en un lugar | 7 180 px en el celular y 83 controles pequeños: dividir en secciones con navegación lateral o en pestañas. |
| Aranceles | Árbol completo | 149 controles por pantalla: cargar el árbol bajo demanda por capítulo. |

### 5.2 Propuesta de experiencia unificada

La coherencia debe estar en el comportamiento, no en forzar el mismo formulario en todos los módulos.

| Patrón | Regla | Ya existe en |
|---|---|---|
| **Listado** | `TablaDatos`: búsqueda arriba; filtros en un panel; columnas configurables; paginación en el servidor; en el móvil, tarjeta con una acción principal y el resto en un menú «⋯». | Órdenes, Facturas, Embarques |
| **Detalle de documento** | Encabezado con número (`<h1>`), estado, acción principal y menú de acciones secundarias. Debajo, la **línea de progreso** del documento y secciones o pestañas. Acciones no disponibles **visibles pero deshabilitadas con motivo** (U-01). | Factura, PL, Embarque |
| **Proceso de varios pasos** | Pasos numerados con estado (pendiente, completo, con error), guardado por paso, revisión final antes de confirmar. Nunca en un modal. | Asistente de OC, factura |
| **Formulario de maestro** | Pantalla o panel lateral con secciones (Identificación, Comercial, Logística, Fiscal). Campos obligatorios marcados; calculados y de solo lectura con otro estilo; errores junto al campo con la corrección sugerida. | Parcial en Productos |
| **Modal** | Solo para confirmar, pedir un motivo, un dato o una elección corta. Como máximo 6 campos, sin tablas editables. | Confirmación, motivo de cancelación |
| **Estados** | Una sola fuente: `core/estados.py` → API → `nucleo/estados.js`. Las etiquetas propias de la empresa salen de `estados_documento`. | Sí |
| **Indicadores** | Cifra, unidad, universo («de 12 OC liberadas») y enlace al listado filtrado que la compone. | Sí (tras `1be922a`) |

---

## 6. Datos maestros y estructura de la base de datos

**Lo que está bien:**

- Códigos únicos por organización (`uq_*_org_codigo`) en todos los catálogos de empresa.
- Llaves foráneas de código por organización: `modelos/referencias.py`, `REFERENCIAS` y `COHERENCIA`.
- `CheckConstraint` en importes y cantidades de los documentos comerciales (`documento_lineas`: cantidad > 0, precio ≥ 0, descuento entre 0 y 100).
- Cantidades decimales normalizadas con `cant()`.
- Los documentos guardan **instantáneas** de lo que puede cambiar en el maestro:
  - La factura guarda partida, origen, descripción comercial y precio.
  - El embarque guarda el nombre del transportista.
  - Por eso un cambio en el maestro no reescribe el pasado.
- **Integridad física comprobada:** `PRAGMA foreign_key_check` vacío e `integrity_check` correcto.

**D-01 · P2 [D][V] · `Producto` y `Articulo` repiten atributos sin una frontera clara**

- **Ubicación:** `modelos/productos.py` (`productos`) y `modelos/maestros.py` (`articulos`).
- **Evidencia:**
  - `Producto` exige `proveedor_id` y es único por `(proveedor_id, estilo, color)`; marca y grupo son opcionales.
  - `Articulo` exige `marca_id` y `grupo_id`; el proveedor es opcional.
  - Ambos llevan estilo, color, marca, grupo, proveedor y unidad.
  - El mismo estilo comprado a dos proveedores genera **dos productos y dos clasificaciones**. Talla y color son columnas de `Articulo`; los demás atributos de variante van en `atributos_variante`.
  - Ya figura en `INFORME.md` como abierto: se reverificó y sigue igual.
- **Impacto:**
  - Clasificación arancelaria duplicada y posiblemente contradictoria para la misma mercancía.
  - Al cambiar marca o grupo en un lado, el otro no se entera.
- **Estructura recomendada** (genérica, sin depender de un ERP):
  - **Producto** (o «genérico»): la unidad de clasificación y de ficha técnica. Lleva estilo, color base, materiales, partida aprobada y marca. Es **independiente del proveedor**.
  - **Variante o artículo**: el SKU vendible (talla, color, otros atributos de variante); apunta a su producto.
  - **Producto-proveedor**: código del proveedor, unidad de compra, empaque (casepack/inner), país de origen y precio de referencia.
- **Validar con el usuario** si una misma mercancía de dos proveedores debe compartir clasificación. Si hay casos en que difiere por composición, entonces ya son productos distintos.
- **Verificación:** ningún `(estilo, color)` con más de una clasificación aprobada; el artículo hereda marca y grupo del producto.

**D-02 · P2 [C] · Dos catálogos de países**

- **Evidencia:**
  - `paises`: ISO, región de lead time.
  - `paises_arancel`: países del arancel, dígitos.
- **Impacto:** el mismo país se administra dos veces, con riesgo de incoherencia (activo en uno e inactivo en el otro).
- **Solución:** `paises` como fuente única y `paises_arancel` como extensión 1:1 (dígitos, nomenclatura) con llave foránea a `paises.codigo`.
- **Verificación:** prueba de integridad: todo `paises_arancel.codigo` existe en `paises`.

**D-03 · P2 [C] · Un almacén que no es un lugar físico, y una recepción sin destino**

- **Evidencia:**
  - `Almacen` (`modelos/maestros.py:156-167`) es, según su docstring, una «separación lógica del inventario (virtual, detalle, mayoreo); no es un lugar físico» y se elige en cada posición de OC.
  - El lugar físico de llegada es el `centro` del embarque.
  - `RecepcionLinea` (`modelos/empaque.py:205-215`) no tiene almacén, ubicación, unidad de carga ni centro.
- **Impacto:** no hay forma de registrar «llegó a la bodega fiscal X», que el usuario pidió (L-05).
- **Solución:** ver §12. Agregar a la recepción `centro_id` (bodega o recinto), `unidad_carga_id` y la ubicación opcional.

**D-04 · P2 [C] · Recepción sin restricciones en la base de datos**

- **Evidencia:** `recepciones` no tiene `CheckConstraint`. Se guardó `cantidad_danada = 5` con `cantidad_recibida = 1` (S2; Anexo A, consulta adicional).
- **Solución:** `CHECK (cantidad_recibida >= 0 AND cantidad_danada >= 0 AND cantidad_danada <= cantidad_recibida)`, en una migración nueva con limpieza previa de los datos que la violen.
- **Verificación:** la migración falla en una base con datos inválidos si no se limpian antes. Es intencional: listar y corregir primero.

**D-05 · P3 [C] · Tablas puente sin organización**

- **Evidencia:** `acuerdo_origenes` y otras `Table(...)` de `modelos/*.py` no tienen `organizacion_id`. Ya figuraba en `INFORME.md`; se reverificó.
- **Impacto:** el aislamiento se apoya en la fila padre. Con RLS, las políticas no cubren esas tablas.
- **Solución:** documentar que su aislamiento se hereda del padre, o agregar la columna y la política.

### Global, de organización y de operación

| Nivel | Debe vivir aquí | Estado actual |
|---|---|---|
| **Global de la plataforma** | Países ISO, monedas ISO, unidades de medida estándar, árbol arancelario oficial (SA y SAC) y sus versiones, incoterms | `paises` y `paises_arancel` sin `organizacion_id`: correcto. `monedas`, `unidades_medida` e `incoterms` son **por organización**: aceptable (cada empresa activa las suyas), pero sin una lista global de referencia. |
| **De la organización** | Sociedades, centros, almacenes, proveedores, terceros, marcas, productos, artículos, transportistas, puertos usados, reglas de lead time, liberaciones, estados con etiqueta propia, incisos nacionales elegidos | Correcto, con `DeOrganizacion`. |
| **De la operación** (instantánea en el documento) | Precio, partida, origen, descripción aduanera, tipo de cambio, nombre del transportista, fechas reales | Correcto, **salvo el tipo de cambio** (L-08). |

---

## 7. Mapa de relaciones entre documentos y módulos

```
Proveedor ──< Producto (ficha, clasificación aprobada) ──< Artículo (SKU, talla)
    │                                                         │
    └──< Orden de compra ──< Posición OC ─────────────────────┘
              │ (aprobación, liberación comercial y logística)
              │
              └─ Posición OC ──< Línea de factura >── Factura del proveedor ── 1:1 ──> Documento CxP (FACTURA_PROVEEDOR)
                                     │                     │                                  │
                                     │                     └──< Packing list                  └──< Aplicación >── Pago
                                     └──< Línea PL >───────────┘   │
                                            │                       └──> Unidad de carga >── Embarque ──< Eventos
                                            └── 1:1 ── Recepción (cantidad recibida y dañada)       (RECOLECCIÓN…RECEPCIÓN)

Alertas ← recepción con diferencias, importación de OC
Historial ← toda acción (registrar), por entidad y factura
Lead times ← fechas de OC (creación, liberaciones), factura, PL (recolección) y eventos del embarque (salida, arribo, entrega, recepción)
```

**Fuente de verdad de cada dato:**

| Dato | Fuente | Copias | Sincronización |
|---|---|---|---|
| Cantidad pedida y precio OC | `posiciones_oc` | Línea de factura (`precio_oc`) | Copia al facturar. Si la OC baja de cantidad, la factura lo detecta al finalizar (`facturas.py:582-584`). |
| Cantidad y precio facturados | `factura_lineas` | `documento_lineas` (CxP) | `proveedores.registrar` al finalizar; `reabrir` y `anular` al reabrir o cancelar. **Unidireccional y correcta.** |
| Partida arancelaria | Producto aprobado (`partida_para`, 6 dígitos) | Línea de factura | Copia al finalizar. Las aprobaciones posteriores completan solo las líneas vacías (`facturas.py:241-251`). |
| Cantidad empacada | `pl_lineas` | — | Se valida contra la línea de factura. |
| Cantidad recibida | `recepciones` (una fila por línea de PL) | Avance de la OC (`flujo_oc.avances`) | Se calcula al consultar. |
| Estado del embarque | `embarques.estado` | Eventos | El evento cambia el estado (`ESTADO_POR_EVENTO`). |
| Fecha de ingreso (lead time) | Evento RECEPCION | — | Ver LT-01: hoy es la hora de captura. |

---

## 8. Evaluación de los procesos logísticos

### A. Órdenes de compra

**Funciona (verificado):**

- Creación manual con asistente y por importación, con la misma validación.
- Aprobación por reglas (`reglas_aprobacion_oc`).
- Liberación comercial y logística con estados configurables.
- Solo una OC **APROBADA** con saldo es facturable (`ordenes.py:130`).
- El casepack y el inner pack solo cambian sin nada facturado (`ordenes.py:388-397`).
- No se puede cancelar una OC con facturas activas (S6: 409 `facturada`).
- Cerrar y reabrir se rigen por la máquina de estados (S6: 200).
- El avance (`flujo_oc.avances`) pondera por valor y limita cada línea a su cantidad.

**Hallazgos:**

**OC-01 · P2 [C] · El avance «EN_TRANSITO» incluye mercancía que ya llegó pero no se ha recibido, y no aclara si lo dañado cuenta como recibido**

- **Ubicación:** `compras/flujo_oc.py`, avance alrededor de la línea 541.
- **Impacto:** una OC arribada y entregada sigue «En tránsito» hasta que alguien registra la recepción. Lo dañado podría contarse como recibido útil.
- **Solución:**
  - Agregar el código `ARRIBADA`.
  - Definir «recibido útil = recibido − dañado» para el avance, o mostrar ambos [V].
- **Verificación:** una OC con su embarque ARRIBADO muestra «Arribada». Una OC con 10 recibidas y 2 dañadas muestra 80 % de avance útil, si el usuario elige ese criterio.

**OC-02 · P3 [V] · Diferencias entre lo pedido y lo recibido sin cierre formal**

- No existe un cierre de saldo por faltante definitivo. La OC se puede **cerrar**, pero el faltante no queda registrado como reclamo.
- Decidir con el usuario si hace falta un documento de reclamo o nota.

### B. Facturas: dos modelos

**Responsabilidades: la separación está justificada; no fusionar.**

| | `facturas` (facturación) | `documentos` tipo `FACTURA_PROVEEDOR` (comercial) |
|---|---|---|
| Qué es | Factura comercial **logística** contra la OC: líneas por posición, partida, origen, empaque, PL, transporte | **Cuenta por pagar**: vencimientos, pagos, saldo, estado de cuenta |
| Quién la captura | Proveedor o equipo interno | Nadie: la genera `comercial/proveedores.registrar` al finalizar la factura |
| Fuente de verdad de | Cantidades, precios, datos aduaneros | Vencimientos, pagos aplicados, saldo |
| Sincronización | Finalizar → crea y emite. Reabrir → borrador (bloqueado con pagos: verificado, `con_pagos`). Cancelar → anula (bloqueado con pagos: `documentos.py:594`). La factura reabierta y luego finalizada actualiza el mismo documento. | No se edita directamente (`documentos.py:592-593`, `no_editable`). |

**Funciona (verificado):**

- Las 6 facturas finalizadas de la demostración tienen su documento emitido, y los totales coinciden con las líneas (invariantes).
- Precio distinto al de la OC solo con motivo (`facturas.py:566-567`).
- Partida obligatoria según la regla `REQUERIR_DATOS_ADUANA` (`facturas.py:570-580`).
- No se factura por encima de la OC.

**Hallazgos:**

**L-08 · P1 [C] · El documento de cuentas por pagar siempre guarda tipo de cambio 1**

- **Ubicación:** `comercial/proveedores.py:39`, con `d.fecha, d.moneda, d.tipo_cambio = f.fecha, f.moneda, 1`.
- **Evidencia:**
  - El catálogo `tipos_cambio` existe y es editable, pero **ningún servicio lo lee**: `grep tipo_cambio` en `modulos/` solo muestra asignaciones y lectura para mostrar.
  - El comentario de la columna dice «a la moneda de la sociedad».
- **Impacto:**
  - Para una sociedad en USD con facturas en USD (la demostración), es correcto.
  - Para una sociedad en GTQ, CRC, HNL o NIO, o una factura en EUR o CNY, el documento queda con un tipo de cambio falso. Cualquier suma en moneda local (estado de cuenta, antigüedad de saldos o un futuro costo de importación) sería incorrecta.
  - Hoy las cifras se muestran por moneda sin convertir, por eso no llega a P0. Pero el dato guardado es incorrecto, y cualquier uso futuro lo hereda.
- **Solución:**
  - Al registrar, tomar el tipo de cambio vigente de `tipos_cambio` (moneda de la factura → moneda de la sociedad, a la fecha de la factura).
  - Si no existe, dejar el documento **pendiente de tipo de cambio** en lugar de usar 1.
  - Lo mismo en `documentos.py:430` (`campos[k] or 1`) y en los pagos.
- **Verificación:**
  - Prueba: sociedad en GTQ, factura en USD, tipo de cambio 7,75 → el documento guarda 7,75.
  - Sin tipo de cambio cargado, la finalización avisa y no guarda 1.

**F-01 · P2 [V] · Impuestos de la factura del proveedor**

- El documento CxP se crea sin impuestos (`proveedores.py:44-50`, sin `linea_impuestos`). En una importación es lo normal, porque el IVA se paga en aduana. Pero la configuración no permite indicarlo por tipo de proveedor (local con IVA frente a extranjero).
- Validar si habrá proveedores locales.

### C. Packing lists

**Funciona (verificado):**

- Solo se empaca lo facturado (sin sobreempaque, invariante).
- Cajas por plantilla o manuales y cajas mixtas.
- Dimensiones y pesos exigidos para finalizar.
- PL reabrible solo si su embarque está **PLANIFICADO** (`packing.py:1011`).
- La cancelación exige sacarlo de la unidad (`packing.py:1033`).
- PDF y Excel con partes completas.

**Hallazgos:**

- U-01: acciones ofrecidas que el servidor rechaza.
- PL-01 · P3 [C]: `asignacion` es redundante (§3.3).
- La interfaz coincide con el backend en el resto de estados (estados en `core/estados.py`).

### D. Embarques y transporte

**Funciona (verificado en S6):**

- El orden de eventos se respeta: un arribo en PLANIFICADO devuelve 409 `orden_eventos`.
- La salida exige carga (409 `sin_carga`) y datos de transporte (422 `datos_transporte`).
- No se aceptan fechas futuras (422) ni fechas anteriores al último evento.
- La cancelación solo antes de la salida libera la carga.
- Mercancía no duplicada: un PL está en una sola unidad (`pl.unidad_carga_id`).
- Varios PL y facturas por embarque, y varios embarques por OC, soportados.

**Hallazgos:**

**L-07 · P2 [D][V] · La liberación aduanera no es obligatoria antes de la entrega**

- **Evidencia:** `core/listas.py:161-170`. El evento `LIBERACION` existe (estado requerido ARRIBADO), pero `ENTREGA` no lo exige.
- **Impacto:** se puede registrar la entrega en bodega sin haber registrado la liberación.
- **Solución:** regla configurable «exigir liberación antes de la entrega», con valor de fábrica según el usuario.

**L-06 · P1 [V] · La unidad de carga no tiene estado propio**

- **Evidencia:** `UnidadCarga` solo tiene tipo, etiqueta, número, sello y capacidades. No tiene estado, fecha de arribo, liberación ni recepción por unidad.
- **Impacto:**
  - En un embarque con varios contenedores, no se puede representar que uno llegó o fue liberado y otro no.
  - El usuario indicó que algunas recepciones son por contenedor.
- **Solución:** ver §12, eventos por unidad opcionales. El estado del embarque se deriva del conjunto de sus unidades.

### E. Recepción de mercancías: el área con más deficiencias

**L-01 · P1 [C] · El evento RECEPCION da por recibido todo, sin contar y sin el permiso de recepción**

- **Ubicación:**
  - `transporte/transporte.py:487-494` (`registrar_evento`, rama RECEPCION).
  - `empaque/packing.py:1054-1059` (`recibir_sin_novedad`).
  - Permiso: `transporte.py:49` `_embarque` exige solo `transporte.gestionar`.
- **Evidencia (S1):**
  - Se creó el rol «Solo transporte» con `transporte.gestionar`.
  - `POST /packing-lists/{id}/recepcion` respondió **403** (correcto).
  - `POST /embarques/{id}/eventos {"tipo":"RECEPCION"}` respondió **200**. Marcó EMB-0002 como RECIBIDO, y cada línea quedó con `cantidad_recibida = cantidad enviada` (72), `danada = 0` y la observación «Received without differences».
- **Impacto:**
  - Quien no tiene permiso de recepción puede declarar recibida toda la carga.
  - No queda constancia de que nadie contó.
  - Faltantes y daños reales desaparecen: no hay alerta ni reclamo.
  - El avance de la OC queda en «Recibida», y el lead time «ingreso» se cierra.
  - La prueba `tests/test_recepcion.py:54-62` cubre el evento solo con el usuario interno, que sí tiene el permiso de recepción. Por eso no detecta la omisión del permiso, y fija el contrato de «recibir sin novedad» con el evento.
- **Solución:**
  - Exigir `recepcion.registrar` para el evento RECEPCION.
  - Convertir «recibir sin novedad» en una acción **explícita** de la pantalla de recepción («Confirmar todo lo pendiente como recibido completo»), con confirmación y registro de quién lo hizo.
  - Lo ideal es que el evento RECEPCION solo lo genere `completar_recepcion` cuando todas las líneas tienen conteo.
  - Ajustar `test_hito_de_recepcion_recibe_sin_novedad` al nuevo contrato y agregar el caso del rol solo de transporte.
- **Verificación:**
  - Rol solo de transporte → 403 en el evento RECEPCION.
  - Con `recepcion.registrar` → 200 y la observación indica «confirmado sin conteo por <usuario>».

**L-02 · P1 [C] · Se aceptan cantidades imposibles y sobrantes sin distinguirlos**

- **Ubicación:**
  - `empaque/packing.py:1075-1080`: solo valida decimales con `error_cantidad`.
  - `esquemas/empaque.py:119-123` (`CantidadCero`).
  - `modelos/empaque.py:205-215`: sin restricciones.
- **Evidencia (S2):**
  - Recibido 1 con dañado 5: aceptado (200), y quedó guardado (consulta: `(7, 1, 5)`).
  - Recibido 122 de 72 enviados: aceptado, con alerta genérica igual que un faltante.
- **Impacto:**
  - Datos imposibles en la base.
  - El sobrante, que puede ser real, no se distingue del faltante ni exige justificación.
- **Solución:**
  - Validar `0 ≤ dañado ≤ recibido`.
  - Clasificar cada diferencia como **faltante**, **sobrante** o **daño**.
  - Exigir observación para sobrante y daño.
  - Agregar la restricción en la base (D-04).
- **Verificación:** pruebas de API: dañado mayor que recibido → 422; sobrante sin observación → 422; sobrante con observación → 200 y alerta de tipo «sobrante».

**L-03 · P1 [C] · Cada registro sobrescribe el anterior: no hay recepciones parciales ni historial de conteos**

- **Ubicación:** `empaque/packing.py:1078-1082`, más `RecepcionLinea.pl_linea_id` **UNIQUE** (`modelos/empaque.py:208`).
- **Evidencia (S2):**
  - Dos registros seguidos de 70 sobre 72: el segundo reemplazó al primero.
  - Después, 122 reemplazó a 70, y luego 1/5 reemplazó a 122.
  - Solo queda el último valor. La bitácora (`historial`) guarda las diferencias, pero no el valor anterior de la recepción.
- **Impacto:**
  - El usuario confirmó que **sí hay recepciones parciales**, también por contenedor. Hoy, recibir 40 hoy y 32 mañana obliga a escribir 72 manualmente.
  - Si alguien escribe 32, borra los 40.
  - No hay trazabilidad del conteo.
- **Solución:** la recepción como **movimientos**: tabla de conteos con fecha operativa, usuario, unidad de carga, bodega, cantidad y dañado. La línea muestra la suma, y una corrección es un movimiento de ajuste con motivo. Ver §12.
- **Verificación:** dos conteos de 40 y 32 dan 72 recibidos con dos movimientos. Una corrección de −2 deja 70 y queda trazada.

**L-04 · P2 [C] · Alertas duplicadas por cada nuevo registro**

- **Ubicación:** `empaque/packing.py:1087-1091` (siempre `db.add(Alerta(...))`).
- **Evidencia (S2):** las alertas `recepcion_diferencia` pasaron de 0 a 2 con dos registros idénticos. Al final del escenario había 4 alertas abiertas para el mismo PL 5, dos de ellas con los mismos valores.
- **Impacto:** ruido; el equipo no sabe cuál vale.
- **Solución:** una alerta abierta por PL y tipo, que se actualiza; se resuelve sola si las diferencias desaparecen.
- **Verificación:** tres registros con diferencias dejan una alerta abierta con el último detalle.

**L-05 · P1 [V] · Sin inventario ni bodega de llegada**

- **Evidencia:** no existe ninguna tabla de existencias ni de movimientos. La recepción no indica almacén ni bodega fiscal (D-03).
- **Impacto:** el sistema no puede responder «qué hay en la bodega fiscal X» ni «qué falta por nacionalizar». El usuario lo pidió explícitamente.
- **Solución:** ver §12.
  - Fase 1: bodega de llegada en la recepción.
  - Fase 2: existencias por bodega, solo si el usuario lo confirma, porque es una función nueva.

### F. Clasificación arancelaria y documentación de importación

**Funciona (verificado):**

- La clasificación pertenece al **producto** (ficha técnica, motor y aprobación con versiones en `producto_versiones`).
- La factura recibe una **instantánea** de 6 dígitos (`partida_para`, `productos.py:230-238`) al finalizar. Un cambio posterior del producto no reescribe facturas finalizadas.
- Incisos nacionales por país en `partidas_pais`.
- Árbol oficial versionado con trazabilidad de fuente.

**Hallazgos:**

**CL-01 · P2 [D][V] · La factura y el PL solo llevan la subpartida de 6 dígitos**

- **Evidencia:** `partida_para` decide así porque «el país destino de la OC es solo una proyección». El inciso nacional de 10 dígitos que exige la declaración aduanera centroamericana no queda en ningún documento de la operación.
- **Impacto:** el agente aduanal lo busca fuera del sistema.
- **Solución:** cuando el embarque fija el centro, y con él el país real, resolver el inciso nacional desde `partidas_pais` y guardarlo como instantánea por línea de PL o de embarque.
- **Validar con el usuario** si se requiere.

**CL-02 · P3 [C] · No hay integración aduanera**

- No existe ningún código de DUCA ni de envío a aduanas. No se supone que exista.
- El evento `LIBERACION` es un registro manual (L-07).

### G. Costos logísticos

**Estado: no implementado.**

- No hay tablas de flete, seguro, gastos de agente, almacenaje ni costo de importación.
- No hay prorrateo por producto, OC o embarque.
- `DocumentoLinea` admite conceptos libres («flete, servicio, cargo», `modelos/comercial.py:488`), pero sin vínculo con el embarque.
- Las `reglas_impuesto` (DAI, IVA de importación) se guardan pero no se aplican a ningún costo.

**Recomendación [D][V]:**

- **No** calcular costo unitario puesto en bodega ni rentabilidad hasta tener:
  - Gastos reales por embarque.
  - Tipo de cambio confiable (L-08).
  - Base de prorrateo acordada.
- Si el usuario lo prioriza, el modelo mínimo es:
  - `costos_embarque` (concepto, previsto o real, moneda, tipo de cambio, documento CxP de origen).
  - Prorrateo explícito (por valor FOB, peso o volumen) guardado como resultado, no recalculado en cada pantalla.
  - Regla: un documento CxP solo puede vincularse una vez a un costo, para no duplicar gastos.

---

## 9. Lead times, reglas de negocio, cálculos, KPIs e informes

### 9.1 Lead times

**Qué se mide hoy** (`transporte/leadtimes.py`):

- **Etapas** (`ETAPAS`): creada → liberación comercial → liberación logística → recolección → salida → arribo → entrega → ingreso.
- **Duraciones:**
  - Comercial: creación → liberación comercial.
  - Logística: → liberación logística.
  - Despacho: → recolección.
  - Salida.
  - Tránsito: salida real → arribo real.
  - Puerto: arribo → entrega.
  - Ingreso: entrega → recepción.
- Se calculan **solo con fechas reales**, en días naturales y con promedio.
- El total solo se calcula para OC completas: las abiertas aparecen como pendientes, **sin duración ficticia** (correcto).
- Distingue lo planificado (ETD, ETA, ETA comprometida) de lo real (salida y arribo reales). Correcto.

**Hallazgos:**

**LT-01 · P2 [C] · La recepción se fecha con la hora de captura, no con la del hecho**

- **Ubicación:**
  - `packing.py:1082` (`rec.fecha = ahora()`).
  - `transporte.py:526` (evento RECEPCION automático con `fecha=ahora()`).
  - El esquema de recepción no acepta fecha.
- **Impacto:** la etapa «ingreso» y el lead time total miden cuándo alguien escribió en el sistema. Un registro hecho tres días tarde suma tres días falsos.
- **Solución:** fecha operativa obligatoria (no futura) en el conteo de recepción. El evento automático usa la última fecha de conteo.
- **Verificación:** recibir con fecha de ayer: el lead time «ingreso» termina ayer.

**LT-02 · P2 [C] · Una OC dividida en varios embarques se da por ingresada al primer embarque**

- **Ubicación:** `leadtimes.py:215-246` (`_hitos_por_oc` usa `_min` para cada hito).
- **Impacto:** el lead time de una OC parcial se acorta. Si el segundo embarque llega con un mes de retraso, no se ve.
- **Solución:**
  - Medir «primer ingreso» y «último ingreso» (OC completa) por separado.
  - La OC cuenta como ingresada cuando su avance de recepción es del 100 %.
- **Verificación:** una OC con dos embarques recibidos los días 1 y 30 muestra primer ingreso el día 1 y total hasta el 30.

**LT-03 · P2 [C] · Duraciones negativas descartadas en silencio**

- **Evidencia:** el filtro `(real[b] - real[a]).days >= 0` (`leadtimes.py:343`) elimina etapas con fechas incoherentes, sin avisar.
- **Impacto:** un dato mal capturado desaparece del promedio en vez de corregirse.
- **Solución:** contar y mostrar «N OC con fechas incoherentes» con enlace.

**LT-04 · P3 [D] · Solo hay promedio**

- Con 14 OC, un caso extremo mueve todo el promedio.
- Se recomiendan **mediana** y percentil 80, además del promedio, y el número de OC de cada cifra (ya se muestra la cantidad por origen). Todo es sustentable con los datos actuales.
- Días naturales: correcto para tránsito; para etapas administrativas (liberación), considerar días hábiles [V].

**LT-05 · P2 [C] · Lead times calculados en memoria y paginados en Python**

- **Evidencia:** se carga toda OC del periodo y se pagina en la lista (`leadtimes.py:464`, `items[(page - 1) * size: page * size]`).
- **Impacto:** escala mal con miles de OC (49 consultas para 14 OC hoy).
- **Solución:** precalcular hitos por OC en una vista o tabla de hechos, actualizada por eventos.

### 9.2 Mapa de estados y transiciones

**Orden de compra:**

```
BORRADOR → EN_APROBACION → APROBADA → CERRADA
              │                ↘ CANCELADA (sin facturas activas)
              └→ RECHAZADA
CERRADA → APROBADA (reabrir)
```

**Factura:**

```
BORRADOR → FINALIZADA → EN_CORRECCION (reabrir) → FINALIZADA
              │
              └→ CANCELADA
```

- **Reabrir** se bloquea si hay PL viajando o pagos.
- **Cancelar** se bloquea si hay PL confirmados en una unidad o pagos.

**Packing list:**

```
BORRADOR → FINALIZADO → EN_CORRECCION → FINALIZADO
              │
              └→ CANCELADO
```

- **Reabrir** solo si el embarque está PLANIFICADO.
- **Cancelar** solo fuera de una unidad.
- **Recibir:** FINALIZADO y con su embarque en ARRIBADO, ENTREGADO o RECIBIDO.

**Embarque:**

```
PLANIFICADO → EN_TRANSITO → ARRIBADO → ENTREGADO → RECIBIDO
     │
     └→ CANCELADO (solo antes de la salida)
```

| Evento | Efecto |
|---|---|
| SALIDA | → EN_TRANSITO |
| ARRIBO | → ARRIBADO |
| ENTREGA | → ENTREGADO |
| RECEPCION | → RECIBIDO (**ver L-01**) |
| LIBERACION, DOCUMENTOS, OTRO | No cambian el estado. |

**Documento comercial:**

```
BORRADOR → EMITIDO → ANULADO
```

- **Anular** se bloquea con pagos.
- Un documento espejo de una factura solo cambia desde la factura.

**Pago:** `REGISTRADO → ANULADO`.

**Hallazgos sobre estados y transiciones:**

- **RN-01 · P2 [C]:** después de RECIBIDO, la recepción sigue abierta (`EMBARQUE.puede("recibir", "RECIBIDO")`). Con L-03 eso permite sobrescribir conteos de un embarque cerrado. Con el modelo de movimientos, las correcciones posteriores deben ser **ajustes con motivo**.
- **RN-02 · Transaccionalidad [C], correcta:**
  - Cada petición es una transacción; un `ErrorNegocio` revierte todo.
  - Se comprobó en S4: el intento fallido de cancelar la factura 1 no dejó PL cancelados, aunque `facturas.cancelar` los marca **antes** de llamar a `cxp.anular`.
  - Existe la tabla `idempotencia` para reintentos de creación (encabezado `Clave`).
- **RN-03 · P3 [R]:** en `facturas.cancelar` (`facturas.py:669-677`) las guardas de pagos se evalúan después de modificar los PL. Hoy es seguro por la reversión, pero frágil si alguien agrega un `commit` intermedio. Ordenar: primero todas las guardas, después los cambios.

### 9.3 Cálculos, KPIs e informes

**El inventario de las 87 cifras y su evaluación individual está en [`AUDITORIA_KPIS.md`](AUDITORIA_KPIS.md).**

- Los P0 de esa auditoría (mezcla de monedas, alcance por proveedor, facturas no finalizadas) se corrigieron en `1be922a` y se reverificaron:
  - Las cifras monetarias se separan por moneda.
  - `importe_facturado` usa solo facturas FINALIZADAS.
- Siguen abiertos los puntos 7 a 27 de su §4–5 (P1 y P2).

**Hallazgos nuevos o reverificados aquí:**

**C-01 · P2 [C] · Mismo nombre, dos criterios para «importe facturado»**

- Es A-03: la lista de OC usa el precio de la OC e incluye borradores; el tablero usa el precio de la factura y solo finalizadas.

**C-02 · P2 [C] · El total del carrito de facturación suma importes de distintas monedas**

- **Ubicación:** `OrdenesView.vue:304` (`importe += c * i.precio`).
- **Impacto:** con OC en USD y EUR seleccionadas, el total es un número sin sentido.
- **Solución:** agrupar por moneda, como ya hace el backend.
- **Verificación:** seleccionar dos OC de monedas distintas muestra dos totales.

**C-03 · Totales de documentos [C], correcto**

- `documento.total = Σ líneas`, con tolerancia de 0,01 (invariante).
- Pagos aplicados ≤ total (invariante).
- Saldos: el documento 7 tiene total 1 791,05, cobrado 1 000 y saldo 791,05 (API: correcto).

**C-04 · Redondeo [C], correcto**

- `core/dinero.py` redondea por decimales de la moneda.
- `dinero.importe_sql` aplica el mismo criterio en SQL que en Python.

**Pruebas reproducibles propuestas** (con datos conocidos, para agregar a `backend/tests` en la fase de corrección):

| # | Dato de entrada | Resultado esperado |
|---|---|---|
| T-1 | OC de 100 u × 10 USD; factura de 60 u × 11 USD (con motivo) en BORRADOR | Lista de OC: 60 u facturadas, con el nombre del criterio. Tablero `importe_facturado` = 0 (no finalizada). Tras finalizar = 660 USD. |
| T-2 | Factura de 1 000 USD de una sociedad en GTQ con tipo de cambio 7,75 el día de la factura | Documento CxP con `tipo_cambio = 7,75` (L-08). |
| T-3 | PL de 72 u; conteos de 40 y 32 | Recibido 72, dos movimientos, sin alerta (L-03). |
| T-4 | PL de 72 u; conteo de 70 + 2 dañadas, registrado dos veces | Una sola alerta abierta (L-04). |
| T-5 | Recibido 1, dañado 5 | 422 (L-02). |
| T-6 | OC en dos embarques recibidos el día 1 y el día 30 | Primer ingreso el día 1, ingreso completo el día 30 (LT-02). |
| T-7 | Rol solo `transporte.gestionar` registra el evento RECEPCION | 403 (L-01). |
| T-8 | Factura con pago aplicado: reabrir y cancelar | 409 `con_pagos` en ambos, y `puede.reabrir == False` con motivo (U-01; hoy la guarda funciona pero no tiene prueba). |

---

## 10. Seguridad, rendimiento, integridad y mantenimiento

### 10.1 Seguridad

**Verificado:**

- **Permisos en el servidor:** S5 (proveedor frente a módulos internos) y S1 (recepción por la vía directa: 403).
- **Aislamiento entre proveedores:** 404 para facturas de otro proveedor, sin filtrar su existencia.
- **Cabeceras HTTP:**
  - CSP restrictiva (`script-src 'self'`, `frame-ancestors 'none'`).
  - `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`.
- **Cookie:** `HttpOnly; SameSite=strict`, y `Secure` configurable.
- **Límite de intentos:** 20 por IP cada 5 minutos (`acceso/limites.py`); se observó 429 al alcanzarlo.
- **Secretos:** `SECRET_KEY` obligatoria; la demostración, solo con `SEED_DEMO`.

**Hallazgos:**

| ID | Prioridad | Hallazgo | Ubicación y evidencia | Solución | Verificación |
|---|---|---|---|---|---|
| S-01 | **P1 [C]** | Recepción sin el permiso de recepción | Es L-01. | — | — |
| S-02 | P2 [C] | El límite de intentos vive en memoria por proceso | `acceso/limites.py` (diccionario `_registro`). Con varios procesos o réplicas, el límite se multiplica; un reinicio lo borra. Ya figuraba en `INFORME.md`. | Guardarlo en la base de datos (tabla con vencimiento) o en Redis si ya se usa. No agregar Redis solo para esto. | Dos procesos comparten el conteo. |
| S-03 | P3 [C] | El inicio de sesión no exige `X-Requested-With` | `curl` sin la cabecera devolvió 200. `SameSite=strict` mitiga el CSRF de inicio de sesión. | Exigir la cabecera también ahí, por coherencia. | `curl` sin la cabecera devuelve 403. |
| S-04 | P2 [R] | Las migraciones corren al arrancar sin bloqueo | `instalacion/migraciones.py:48-57`. No hay `pg_advisory_lock`. Con varios procesos arrancando a la vez en PostgreSQL, dos `upgrade` simultáneos pueden chocar. | `pg_advisory_lock` alrededor del `upgrade`, o migrar como paso de despliegue. **Validar** cómo se despliega. | Arrancar 4 procesos a la vez contra una base vacía: una sola ejecución de migraciones. |
| S-05 | P2 [C] | No hay integración continua | No existe `.github/workflows`. Las 584 pruebas, ruff, eslint y el recorrido e2e dependen de que alguien los ejecute. | Flujo de trabajo con `pytest`, `ruff`, `alembic check`, `npm run lint`, `npm run build` y, en un trabajo aparte, `npm run e2e`. | Una PR con una prueba rota queda en rojo. |
| S-06 | P3 [C] | Fuentes de Google en `index.html:6-8` | Dependencia externa en cada carga: privacidad, funcionamiento sin conexión y CSP más abierta. En el recorrido, fue el único error de consola en las 47 pantallas. | Servir la fuente Inter desde `frontend/public` y quitar los dominios de la CSP. | El recorrido e2e queda con 0 problemas. |
| S-07 | P3 [C] | Sin tokens de integración | No hay acceso por API para un ERP sin sesión de navegador. Ya figuraba en `INFORME.md`. | Tokens por organización con permisos limitados [V]. | — |

### 10.2 Rendimiento

**Medición:** número de consultas SQL y tiempo por petición sobre `perf.db` con `TestClient`.

| Ruta | Consultas | ms | Observación |
|---|---:|---:|---|
| `/api/tableros` | 15 | 18 | **Línea base de cualquier petición** |
| `/api/auth/me` | 22 | 47 | |
| `/api/dashboard` | 106 | 492 | La pantalla más pesada |
| `/api/embarques` (3 embarques) | 106 | 108 | Unas 30 consultas por embarque |
| `/api/seguimiento/embarques` | 75 | 52 | |
| `/api/embarques/1` | 77 | 95 | |
| `/api/packing-lists/1` | 68 | 124 | |
| `/api/facturas/1` | 60 | 90 | |
| `/api/seguimiento/leadtimes` | 49 | 56 | |

**P-01 · P2 [C] · Cada petición recarga 11 catálogos completos**

- **Evidencia:** en `/api/tableros`, 11 de las 15 consultas son lecturas completas de: `definiciones_campo`, `atributos_variante`, `valores_lista`, `unidades_medida`, `monedas`, `modos_transporte`, `incoterms`, `condiciones_pago`, `roles`, `meta` y `organizaciones` (dos veces).
- **Impacto:** unas 11 consultas de más en **cada** llamada a la API. Con 50 usuarios activos, la mayor parte del tráfico de la base es este.
- **Solución:** en lugar de agregar una capa nueva, usar el mecanismo de versión que ya existe (`version_config`, tabla `meta`): una sola consulta a `meta` por petición. Si la versión no cambió, reutilizar los catálogos del proceso.
- **Verificación:** `/api/tableros` hace como máximo 5 consultas; cambiar un catálogo se refleja en la siguiente petición.

**P-02 · P2 [C] · Consultas repetidas (N+1) en `/api/embarques` y en el Inicio**

- **Evidencia:** agrupación de sentencias en `/api/embarques`:
  - `tipos_unidad` 12 veces.
  - `paises` (tabla completa) 6 veces.
  - `puertos` 6 veces.
  - `factura_lineas`, `grupo_cajas_items` y `posiciones_oc` 7 veces cada una.
- **Impacto:** el costo crece linealmente: unos 30 por embarque, y unas 3 000 consultas para 100 embarques.
- **Solución:** `selectinload` de unidades → PL → líneas, y diccionarios de catálogos cargados una vez por petición.
- **Verificación:** prueba que cuente consultas: `/api/embarques` con 3 y con 30 embarques debe hacer el mismo número ±5.

**P-03 · P3 [C] · Listas sin paginar**

- **Evidencia:** `/api/embarques`, `/api/alertas`, `/api/usuarios` y `/api/roles` devuelven todo (listas planas, sin `size`).
- **Solución:** paginar `embarques` y `alertas`, que crecen con la operación. `usuarios` y `roles` pueden quedarse así.

### 10.3 Integridad y concurrencia

**Correcto:**

- Edición exclusiva (`ediciones`): uno edita y los demás leen.
- Versión optimista en factura y documento (`version`).
- `bloquear=True` (`SELECT … FOR UPDATE`) en las acciones de estado de factura y documento.
- Claves de idempotencia en las altas.

**Riesgo:**

- **I-01 · P2 [R]:** la recepción (`registrar_recepcion`) no bloquea el PL. Dos usuarios registrando la misma línea a la vez: gana el último, sin aviso. Con el modelo de movimientos (L-03), ambos conteos se conservan.

### 10.4 Mantenimiento

**Puntos a corregir:**

- A-01 a A-07.
- Dependencias sin versión fija (§3.3).
- Documentación desfasada (§3.3).

**Punto fuerte:** `docs/ARQUITECTURA.md` describe bien los mecanismos de configuración y es coherente con el código revisado.

---

## 11. Pruebas ejecutadas, resultados y áreas sin cobertura

| Prueba | Resultado |
|---|---|
| `pytest` completo (58 archivos) | **584 aprobadas, 3 omitidas, 0 fallidas** (`test_migraciones_al_dia_con_los_modelos` tarda unos 47 s) |
| `ruff check` | Sin errores |
| `alembic check` | Modelos y migraciones al día |
| `npm run lint` | Sin errores (requirió `npm ci`: el `node_modules` local estaba desactualizado) |
| `npm run build` | Correcto |
| `PRAGMA foreign_key_check` e `integrity_check` (demostración) | Vacío y correcto |
| Invariantes de negocio (Anexo A), antes y después de los escenarios | 12 de 12 correctas |
| Recorrido de navegador `frontend/e2e/recorrido.mjs` (4 usuarios × 1440 y 390 px × 44–47 pantallas) | 0 errores de JS y 0 respuestas 4xx/5xx. El único «problema» por pantalla es la fuente de Google (S-06). Los redireccionamientos por falta de permiso son los esperados para cada rol. |
| Métricas de UX (Anexo B: 33 rutas × 3 anchos × 3 roles) | 0 desbordes; controles pequeños y fuentes menores de 12 px (U-04, U-06) |
| Rendimiento (consultas por ruta) | §10.2 |

**Escenarios de extremo a extremo** (Anexo B; API real sobre la demostración):

| Escenario | Qué se probó | Resultado |
|---|---|---|
| S1 | Rol solo de transporte: recepción directa frente al evento RECEPCION | **Falla de permiso confirmada** (L-01) |
| S2 | Recepción repetida, sobrante, dañado mayor que recibido | **Sobrescritura, alertas duplicadas y datos imposibles** (L-02, L-03, L-04) |
| S3 | Lead time de 3 OC tras la recepción | Hitos y duraciones coherentes con los eventos registrados. «Ingreso» = 0 o 1 días porque los eventos del escenario se registraron con horas de diferencia (LT-01). |
| S4 | Factura con pago: reabrir y cancelar | Bloqueado con 409. La guarda `con_pagos` se comprobó llamándola directamente (con reversión), porque todas las facturas de la demostración tienen PL viajando y la guarda de transporte responde primero. El fallo no dejó cambios parciales. |
| S5 | Aislamiento de proveedores | Correcto (404 y 403) |
| S6 | Transiciones imposibles y guardas de OC | Correcto (409 y 422); cerrar y reabrir una OC, correcto |

**Áreas sin cobertura de pruebas automatizadas:**

- Guarda `con_pagos` al reabrir una factura: funciona, pero no tiene prueba.
- Permiso del evento RECEPCION: la prueba actual (`test_recepcion.py:54-62`) solo usa un usuario con permiso, así que no cubre la omisión.
- Recepción con sobrante, con dañado mayor que recibido, y repetida.
- Tipo de cambio de CxP en una sociedad con moneda distinta de USD.
- Lead time de OC en varios embarques.
- Concurrencia en recepción.
- Aislamiento entre **organizaciones** a través de la API. Existe `test_organizaciones.py`; la demostración tiene una sola organización, así que no se repitió aquí.
- Rendimiento: no hay una prueba que cuente consultas.
- Navegador: no se ejecuta en CI (S-05).

---

## 12. Propuesta de arquitectura y diseño mejorados (genérica y configurable)

No se propone reescribir. Se conservan las capas, los módulos de dominio, las máquinas de estado, el aislamiento por organización y los dos modelos de factura. Los cambios son localizados.

**1. Servicio de recepción único** (nuevo `modulos/recepcion/`, que absorbe `packing.registrar_recepcion`, `recibir_sin_novedad` y `transporte.completar_recepcion`):

- Rompe el ciclo empaque↔transporte (A-01).
- Tabla `recepcion_movimientos` con:
  - `pl_linea_id`, `unidad_carga_id`, `centro_id` (bodega o recinto de llegada).
  - `fecha_operativa`, `cantidad`, `danada`, `tipo` (CONTEO | AJUSTE | CONFIRMACION_SIN_CONTEO), `motivo` y `usuario_id`.
- `recepciones` pasa a ser una vista o suma por línea, o se conserva como acumulado mantenido por el servicio. La migración convierte cada fila actual en un movimiento CONTEO.
- Reglas en un solo lugar:
  - `0 ≤ dañada ≤ recibida`.
  - Sobrante con motivo.
  - Permiso `recepcion.registrar`.
  - Fecha no futura.
  - Una alerta abierta por PL.
- El estado RECIBIDO se deriva por unidad de carga y por embarque.

**2. Estado opcional por unidad de carga:** arribo, liberación y recepción por contenedor (L-06). El estado del embarque es el mínimo de sus unidades.

**3. Tipo de cambio con fuente única:** servicio `core/cambio.py` (moneda origen y destino, fecha) que lea `tipos_cambio`. Lo usan CxP, pagos y, si se aprueba, los costos (L-08).

**4. Acciones con motivo:** cada documento expone `acciones: {codigo: {permitida, motivo}}`, calculadas con las mismas guardas que el servidor aplica (U-01).

**5. Catálogos por versión:** una consulta a `meta` por petición y catálogos reutilizados mientras la versión no cambie (P-01).

**6. Producto independiente del proveedor** + tabla producto-proveedor (D-01) [V].

**7. Fase posterior, solo si el usuario lo aprueba:**

- Existencias por bodega alimentadas por `recepcion_movimientos`.
- Costos por embarque con prorrateo explícito (§8.G).

---

## 13. Plan de corrección ordenado por prioridad y dependencias

Cada paso es una PR independiente con sus pruebas (las de §9.3 y Anexo B). Ningún paso elimina migraciones. Los cambios de esquema van en migraciones nuevas, con limpieza previa de los datos que violen las restricciones nuevas.

| Paso | Prioridad | Contenido | Depende de | Verificación |
|---|---|---|---|---|
| 1 | P1 | **Permiso del evento RECEPCION** + «confirmar sin conteo» explícito; ajustar `test_recepcion.py:54-62` (L-01, S-01) | — | T-7; prueba nueva con el rol de recepción |
| 2 | P1 | **Validaciones de recepción** (dañado ≤ recibido, sobrante con motivo) + `CHECK` en la base (L-02, D-04) | — | T-5; migración sobre una copia de producción con la consulta del Anexo A |
| 3 | P1 | **Acciones con motivo** en factura y PL (U-01) | — | T-8; botones deshabilitados con explicación en el navegador |
| 4 | P1 | **Tipo de cambio** en CxP y pagos desde `tipos_cambio`; pendiente si falta (L-08) | — | T-2 |
| 5 | P1 [V] | **Decisión del usuario:** recepción por contenedor, bodega de llegada, inventario (L-05, L-06, D-03) | — | Acta de decisión |
| 6 | P1 | **Recepción como movimientos** (servicio `recepcion`, fecha operativa, unidad y bodega, alerta única) (L-03, L-04, LT-01, RN-01, I-01) | 1, 2, 5 | T-3, T-4; migración que convierte las recepciones actuales sin cambiar las sumas |
| 7 | P2 | **Estado por unidad de carga** (L-06) | 5, 6 | Embarque con 2 contenedores, uno recibido: embarque «recibido parcial» |
| 8 | P2 | **Lead time**: primer y último ingreso, avisos de fechas incoherentes, mediana y P80 (LT-02, LT-03, LT-04); avance «Arribada» (OC-01) | 6 | T-6 |
| 9 | P2 | **Rendimiento**: catálogos por versión, `selectinload` en embarques e Inicio, paginar embarques y alertas (P-01, P-02, P-03) | — | Prueba de conteo de consultas |
| 10 | P2 | **Integración continua** (S-05) y bloqueo de migraciones (S-04) | — | PR en rojo con una prueba rota |
| 11 | P2 | **Inicio**: diferencias de recepción en «Necesita su atención» (U-02); carrito por moneda (C-02); nombre o criterio del importe facturado en OC (A-03, C-01) | 6 | T-1; captura del Inicio |
| 12 | P2 | **Filtro de liberaciones** desde el catálogo (A-06) | — | Cambio en el catálogo visible en el filtro |
| 13 | P2 | **Modales largos → pantallas o paneles por secciones** (U-03); objetivos táctiles (U-04); encabezados de lead time (U-05) | 3 | Métrica del Anexo B |
| 14 | P2 | **Acoplamiento**: publicar las funciones privadas, servicio de recepción (ya en el paso 6), quitar el import de modelos→módulos y de acceso→productos (A-01, A-02); prueba de arquitectura | 6 | Prueba del grafo de imports |
| 15 | P2 | **Dividir componentes y servicios grandes** (A-04, A-05) | 13, 14 | Mismas pruebas y recorrido e2e sin cambios |
| 16 | P2 [V] | **Producto independiente del proveedor**; países unificados (D-01, D-02) | Decisión del usuario | Ningún `(estilo, color)` con dos clasificaciones aprobadas |
| 17 | P2 [V] | Inciso nacional en el embarque o PL (CL-01); liberación antes de la entrega (L-07); impuestos de proveedor local (F-01) | Decisión del usuario | Pruebas por regla |
| 18 | P2 | Límite de intentos compartido entre procesos (S-02); dependencias con versión fija | — | Dos procesos comparten el conteo |
| 19 | P3 | **Limpieza**: código muerto de §3.2 (16 elementos), documentación desfasada, docstrings «SAP», import a mitad de archivo, advertencia del ORM (A-07), fuente local (S-06), `<h1>` en los detalles y fuente mínima de 12 px (U-06), inicio de sesión con `X-Requested-With` (S-03), datos de la demostración en el idioma de la organización (U-07), `asignacion` redundante (PL-01, tras verificar los datos) | 15 (para no chocar con la división de archivos) | `lint`, `build`, `pytest`, `e2e` |
| 20 | P3 [V] | Decidir sobre `documento_envios`, `plantillas_documento`, `proveedor_electronico`, impresión de documentos comerciales (`numero_en_letras`), tokens de integración, costos logísticos (§3.4, §8.G, S-07) | Decisión del usuario | — |

---

## Anexo A · Invariantes de negocio (SQL reproducible)

Se ejecutan contra cualquier base SQLite o PostgreSQL. Ajustar `!=` y los booleanos si hace falta. Cada consulta debe devolver **0 filas**.

```sql
-- Posición sobrefacturada
SELECT p.id, p.cantidad, SUM(fl.cantidad) FROM posiciones_oc p
  JOIN factura_lineas fl ON fl.posicion_oc_id = p.id JOIN facturas f ON f.id = fl.factura_id
 WHERE f.estado <> 'CANCELADA' GROUP BY p.id, p.cantidad HAVING SUM(fl.cantidad) > p.cantidad;
-- Línea de factura sobreempacada
SELECT fl.id FROM factura_lineas fl JOIN pl_lineas l ON l.factura_linea_id = fl.id
  JOIN packing_lists p ON p.id = l.pl_id WHERE p.estado <> 'CANCELADO'
 GROUP BY fl.id, fl.cantidad HAVING SUM(l.cantidad) > fl.cantidad;
-- PL no finalizado dentro de una unidad
SELECT id FROM packing_lists WHERE unidad_carga_id IS NOT NULL AND estado <> 'FINALIZADO';
-- Embarque en tránsito o después sin salida real / arribado o después sin arribo real
SELECT id FROM embarques WHERE estado IN ('EN_TRANSITO','ARRIBADO','ENTREGADO','RECIBIDO') AND salida_real IS NULL;
SELECT id FROM embarques WHERE estado IN ('ARRIBADO','ENTREGADO','RECIBIDO') AND arribo_real IS NULL;
-- Embarque RECIBIDO con líneas sin recepción
SELECT DISTINCT e.codigo FROM embarques e JOIN unidades_carga u ON u.embarque_id = e.id
  JOIN packing_lists p ON p.unidad_carga_id = u.id JOIN pl_lineas l ON l.pl_id = p.id
  LEFT JOIN recepciones r ON r.pl_linea_id = l.id
 WHERE e.estado = 'RECIBIDO' AND p.estado <> 'CANCELADO' AND r.id IS NULL;
-- Recepción en embarque que no ha llegado
SELECT e.codigo FROM recepciones r JOIN pl_lineas l ON l.id = r.pl_linea_id JOIN packing_lists p ON p.id = l.pl_id
  JOIN unidades_carga u ON u.id = p.unidad_carga_id JOIN embarques e ON e.id = u.embarque_id
 WHERE e.estado IN ('PLANIFICADO','EN_TRANSITO');
-- Factura finalizada sin documento CxP emitido / cancelada con documento emitido
SELECT f.id FROM facturas f LEFT JOIN documentos d ON d.factura_id = f.id AND d.estado = 'EMITIDO'
 WHERE f.estado = 'FINALIZADA' AND d.id IS NULL;
SELECT f.id FROM facturas f JOIN documentos d ON d.factura_id = f.id WHERE f.estado = 'CANCELADA' AND d.estado = 'EMITIDO';
-- Documento con total distinto de sus líneas
SELECT d.id FROM documentos d JOIN documento_lineas l ON l.documento_id = d.id
 GROUP BY d.id, d.total HAVING ABS(d.total - SUM(l.total)) > 0.01;
-- OC cancelada con facturas activas
SELECT DISTINCT o.numero FROM ordenes_compra o JOIN posiciones_oc p ON p.oc_id = o.id
  JOIN factura_lineas fl ON fl.posicion_oc_id = p.id JOIN facturas f ON f.id = fl.factura_id
 WHERE o.estado = 'CANCELADA' AND f.estado <> 'CANCELADA';
-- Pagos aplicados por encima del documento
SELECT d.id FROM documentos d JOIN aplicaciones a ON a.documento_id = d.id
 GROUP BY d.id, d.total HAVING SUM(a.importe) > d.total + 0.01;
-- (Nuevas, por L-02) Recepción imposible y sobrante sin clasificar
SELECT pl_linea_id FROM recepciones WHERE cantidad_danada > cantidad_recibida;
SELECT r.pl_linea_id FROM recepciones r JOIN pl_lineas l ON l.id = r.pl_linea_id WHERE r.cantidad_recibida > l.cantidad;
```

**Resultado en la demostración tras los escenarios:**

- Las 12 primeras: 0 filas.
- `dañada > recibida`: 1 fila, `(7, 1, 5)`, creada por S2. Demuestra L-02.

## Anexo B · Escenarios de extremo a extremo y medición de UX (reproducibles)

**Entorno:**

```bash
cd backend
DATABASE_URL=sqlite:////tmp/auditoria/demo.db UPLOAD_DIR=/tmp/auditoria/archivos SEED_DEMO=1 DOS_PASOS=false COOKIE_SEGURA=0 \
  FRONTEND_DIST=../frontend/dist SECRET_KEY=<clave-larga> uvicorn app.main:app --port 8077
```

Las cuentas de la demostración son `interno@`, `admin@`, `tnf@` y `vans@demo.com`, con la contraseña de la demostración. Todas las peticiones llevan la cabecera `X-Requested-With: fetch`.

| Escenario | Pasos (API) | Resultado esperado tras la corrección | Resultado actual |
|---|---|---|---|
| S1 | `admin`: `POST /api/roles {nombre, permisos:["transporte.gestionar"]}` → `POST /api/usuarios` con ese rol. `interno`: eventos ARRIBO y ENTREGA en EMB-0002. Nuevo usuario: `POST /api/packing-lists/{pl}/recepcion` y `POST /api/embarques/{id}/eventos {tipo:"RECEPCION"}` | 403 y 403 | 403 y **200**; líneas recibidas completas «sin novedad» |
| S2 | `interno`: `POST /api/packing-lists/{pl}/recepcion` dos veces con `cantidad_recibida = enviado − 2`; luego `enviado + 50`; luego `recibida 1, dañada 5` | 1 alerta; sobrante exige motivo; 422 | 2 alertas nuevas idénticas; 200; **200** |
| S3 | `GET /api/seguimiento/leadtimes?size=100` | Hitos con fecha operativa | Hitos con la hora de captura |
| S4 | `POST /api/pagos` con aplicación a la CxP de la factura 1; `POST /api/facturas/1/reabrir` y `/cancelar` | 409 y `puede.reabrir = false` con motivo | 409 (correcto); `puede.reabrir = true` (U-01) |
| S5 | Como `vans`: `GET /api/facturas/{de TNF}`, `/api/documentos`, `/api/pagos`, `/api/embarques`, `/api/terceros` | 404 y 403 | 404 y 403 (correcto) |
| S6 | ARRIBO en EMB-0003 PLANIFICADO; SALIDA sin carga; evento con fecha +5 días; cancelar la OC 4400003701; cerrar y reabrir | 409, 409, 422, 409, 200, 200 | Igual (correcto) |

**Medición de UX:** con Playwright, por cada ruta y ancho (1440, 820 y 390 px), se evalúa en la página:

- Desborde: `document.documentElement.scrollWidth − innerWidth`.
- Elementos visibles cuyo borde derecho supera el ancho de la ventana sin un contenedor con desplazamiento.
- Controles (`button`, `a[href]`, `input`, `select`, `[role=button]`) con alto o ancho menor de 32 px (y de 24 px para WCAG 2.5.8).
- Tamaño mínimo de fuente del texto visible.
- Presencia de `<h1>`.
- Botones sin nombre accesible.
- Campos sin etiqueta.
- Respuestas 4xx o 5xx de la API durante la carga.

**Rendimiento:** escucha `before_cursor_execute` del motor de SQLAlchemy y `TestClient` autenticado; se cuentan las sentencias por ruta (§10.2).
