# Módulos

<!-- Archivo generado por backend/scripts/documentar_modulos.py desde el contrato de cada
     módulo (app/modulos/<clave>/modulo.py). No lo edite a mano: cambie el contrato y vuelva
     a generarlo. tests/test_documentacion.py falla si no está al día. -->

Cada carpeta de `backend/app/modulos/` es un módulo con su contrato `modulo.py`. Cómo
funciona el contrato y cómo se conectan los módulos sin conocerse está en
[ARQUITECTURA.md](ARQUITECTURA.md#módulos). La lista también se consulta en la API:
`GET /api/modulos`.

«Se puede apagar» indica que la empresa lo desactiva en Configuración → Empresa →
Módulos. «Usa» son los módulos de los que importa código: es deuda que se va
reduciendo (tests/test_dependencias.py), porque lo ideal es conectarse por registros.

| Módulo | Clave | Operaciones | Se puede apagar | Usa |
|---|---|---:|---|---|
| [Acceso](#acceso) | `acceso` | 24 | no | comex, comun, empresa |
| [Catálogo](#catalogo) | `catalogo` | 13 | no | acceso, comun, maestros, productos |
| [Clasificación arancelaria](#clasificacion) | `clasificacion` | 103 | sí | acceso, comun, documentos, productos |
| [Comercio exterior](#comex) | `comex` | 0 | no | acceso, catalogo, comun |
| [Órdenes de compra](#compras) | `compras` | 28 | no | acceso, catalogo, comex, comun, documentos, empaque, facturacion, maestros, transporte |
| [Común](#comun) | `comun` | 7 | no | acceso |
| [Documentos](#documentos) | `documentos` | 0 | no | acceso, catalogo, comex, empaque, empresa, facturacion, maestros |
| [Listas de empaque](#empaque) | `empaque` | 44 | no | acceso, catalogo, comun, documentos, facturacion, maestros, recepcion, transporte |
| [Empresa](#empresa) | `empresa` | 3 | no | acceso, catalogo, comun |
| [Etiquetado](#etiquetado) | `etiquetado` | 68 | sí | acceso, catalogo, comex, comun, empaque, empresa, maestros |
| [Facturas](#facturacion) | `facturacion` | 17 | no | acceso, catalogo, comex, comun, documentos, empaque, maestros |
| [Integraciones](#integraciones) | `integraciones` | 13 | no | acceso, catalogo, compras, comun, documentos |
| [Datos maestros](#maestros) | `maestros` | 24 | no | acceso, catalogo, clasificacion, comun, documentos, empresa, productos, transporte |
| [Plataforma](#plataforma) | `plataforma` | 4 | no | acceso, comun |
| [Productos](#productos) | `productos` | 36 | no | acceso, catalogo, clasificacion, comex, comun, documentos, empaque, etiquetado, facturacion, maestros |
| [Recepción e inventario](#recepcion) | `recepcion` | 6 | no | acceso, catalogo, comun, facturacion, maestros, transporte |
| [Reportes](#reportes) | `reportes` | 9 | no | acceso, catalogo, comex, comun, documentos, seguimiento |
| [Seguimiento e indicadores](#seguimiento) | `seguimiento` | 20 | sí | acceso, catalogo, comex, compras, comun, documentos, empaque, empresa, facturacion, transporte |
| [Transporte](#transporte) | `transporte` | 18 | sí | acceso, catalogo, comun, documentos, facturacion, recepcion |

<a id="acceso"></a>

## Acceso

Ingreso en dos pasos, sesión, perfil y preferencias, usuarios, roles y permisos.

- **Código:** `backend/app/modulos/acceso/` · **Pantallas:** `frontend/src/modulos/acceso/`
- **API:** 24 operaciones en `/api/auth`, `/api/perfil`, `/api/proveedores`, `/api/roles`, `/api/usuarios` (sección «Acceso» de `/docs`)
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Usa:** `comex`, `comun`, `empresa`
- **Lo usan:** `catalogo`, `clasificacion`, `comex`, `compras`, `comun`, `documentos`, `empaque`, `empresa`, `etiquetado`, `facturacion`, `integraciones`, `maestros`, `plataforma`, `productos`, `recepcion`, `reportes`, `seguimiento`, `transporte`

<a id="catalogo"></a>

## Catálogo

Árbol de familias y categorías del catálogo, con la sección que cada módulo guarda de ellas.

- **Código:** `backend/app/modulos/catalogo/`
- **API:** 13 operaciones en `/api/grupos-producto` (sección «Datos maestros» de `/docs`)
- **Usa:** `acceso`, `comun`, `maestros`, `productos`
- **Lo usan:** `comex`, `compras`, `documentos`, `empaque`, `empresa`, `etiquetado`, `facturacion`, `integraciones`, `maestros`, `productos`, `recepcion`, `reportes`, `seguimiento`, `transporte`

<a id="clasificacion"></a>

## Clasificación arancelaria

Arancel oficial, motor de clasificación (familias, atributos, reglas) y conocimiento de la empresa.

- **Código:** `backend/app/modulos/clasificacion/` · **Pantallas:** `frontend/src/modulos/clasificacion/`
- **API:** 103 operaciones en `/api/aranceles`, `/api/clasificacion`, `/api/conocimiento`, `/api/familias`, `/api/i18n` (sección «Clasificación arancelaria» de `/docs`)
- **Se puede apagar:** Foreign trade: customs technical sheet, tariff classification, tariff schedule and trade agreements
- **Usa:** `acceso`, `comun`, `documentos`, `productos`
- **Lo usan:** `maestros`, `productos`

<a id="comex"></a>

## Comercio exterior

Ficha aduanera del producto y categoría aduanera de cada familia.

- **Código:** `backend/app/modulos/comex/`
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Usa:** `acceso`, `catalogo`, `comun`
- **Lo usan:** `acceso`, `compras`, `documentos`, `etiquetado`, `facturacion`, `productos`, `reportes`, `seguimiento`

<a id="compras"></a>

## Órdenes de compra

Órdenes de compra: importación, asistente, aprobación, liberaciones y líneas disponibles para facturar.

- **Código:** `backend/app/modulos/compras/` · **Pantallas:** `frontend/src/modulos/compras/`
- **API:** 28 operaciones en `/api/ordenes` (sección «Órdenes de compra» de `/docs`)
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Usa:** `acceso`, `catalogo`, `comex`, `comun`, `documentos`, `empaque`, `facturacion`, `maestros`, `transporte`
- **Lo usan:** `integraciones`, `seguimiento`

<a id="comun"></a>

## Común

Edición exclusiva de un registro y bitácora de auditoría.

- **Código:** `backend/app/modulos/comun/`
- **API:** 7 operaciones en `/api/auditoria`, `/api/cambios`, `/api/edicion` (sección «Común» de `/docs`)
- **Usa:** `acceso`
- **Lo usan:** `acceso`, `catalogo`, `clasificacion`, `comex`, `compras`, `empaque`, `empresa`, `etiquetado`, `facturacion`, `integraciones`, `maestros`, `plataforma`, `productos`, `recepcion`, `reportes`, `seguimiento`, `transporte`

<a id="documentos"></a>

## Documentos

Generación de PDF y Excel de los documentos, sus plantillas e idioma.

- **Código:** `backend/app/modulos/documentos/`
- **Usa:** `acceso`, `catalogo`, `comex`, `empaque`, `empresa`, `facturacion`, `maestros`
- **Lo usan:** `clasificacion`, `compras`, `empaque`, `facturacion`, `integraciones`, `maestros`, `productos`, `reportes`, `seguimiento`, `transporte`

<a id="empaque"></a>

## Listas de empaque

Listas de empaque con su estructura de cajas, inner packs y prepacks, y plantillas de caja.

- **Código:** `backend/app/modulos/empaque/` · **Pantallas:** `frontend/src/modulos/empaque/`
- **API:** 44 operaciones en `/api/ordenes`, `/api/packing-lists`, `/api/plantillas`, `/api/recetas-empaque`, `/api/reglas-empaque`, `/api/tipos-empaque` (sección «Listas de empaque» de `/docs`)
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Usa:** `acceso`, `catalogo`, `comun`, `documentos`, `facturacion`, `maestros`, `recepcion`, `transporte`
- **Lo usan:** `compras`, `documentos`, `etiquetado`, `facturacion`, `productos`, `seguimiento`

<a id="empresa"></a>

## Empresa

Ficha, marca, documentos y reglas de la organización.

- **Código:** `backend/app/modulos/empresa/` · **Pantallas:** `frontend/src/modulos/empresa/`
- **API:** 3 operaciones en `/api/organizacion`, `/api/publico` (sección «Empresa» de `/docs`)
- **Usa:** `acceso`, `catalogo`, `comun`
- **Lo usan:** `acceso`, `documentos`, `etiquetado`, `maestros`, `seguimiento`

<a id="etiquetado"></a>

## Etiquetado

Tipos de etiqueta, familias, diseños con versiones y aprobación, qué diseño lleva cada cosa, trabajos desde OC, artículos y listas de empaque, descargas e historial.

- **Código:** `backend/app/modulos/etiquetado/` · **Pantallas:** `frontend/src/modulos/etiquetado/`
- **API:** 68 operaciones en `/api/etiquetas` (sección «Etiquetado» de `/docs`)
- **Tareas de fondo:** `_recuperar_trabajos`
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Se puede apagar:** Labels: label designs, versions and label generation
- **Usa:** `acceso`, `catalogo`, `comex`, `comun`, `empaque`, `empresa`, `maestros`
- **Lo usan:** `productos`

<a id="facturacion"></a>

## Facturas

Facturas comerciales armadas desde las líneas de las OCs, su revisión y sus documentos.

- **Código:** `backend/app/modulos/facturacion/` · **Pantallas:** `frontend/src/modulos/facturacion/`
- **API:** 17 operaciones en `/api/archivos`, `/api/facturas` (sección «Facturas» de `/docs`)
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Usa:** `acceso`, `catalogo`, `comex`, `comun`, `documentos`, `empaque`, `maestros`
- **Lo usan:** `compras`, `documentos`, `empaque`, `productos`, `recepcion`, `seguimiento`, `transporte`

<a id="integraciones"></a>

## Integraciones

Sistemas externos (ERP u otros): adaptadores de formato, mapeos versionados, entrada de OCs, salida de facturas, bitácora y referencias externas.

- **Código:** `backend/app/modulos/integraciones/` · **Pantallas:** `frontend/src/modulos/integraciones/`
- **API:** 13 operaciones en `/api/integraciones` (sección «Integraciones» de `/docs`)
- **Usa:** `acceso`, `catalogo`, `compras`, `comun`, `documentos`

<a id="maestros"></a>

## Datos maestros

Catálogos, listas de valores, genéricos y escalas, cargas masivas y su gobierno (responsables, obligatorios, historial).

- **Código:** `backend/app/modulos/maestros/` · **Pantallas:** `frontend/src/modulos/maestros/`
- **API:** 24 operaciones en `/api/catalogos`, `/api/listas` (sección «Datos maestros» de `/docs`)
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Usa:** `acceso`, `catalogo`, `clasificacion`, `comun`, `documentos`, `empresa`, `productos`, `transporte`
- **Lo usan:** `catalogo`, `compras`, `documentos`, `empaque`, `etiquetado`, `facturacion`, `productos`, `recepcion`

<a id="plataforma"></a>

## Plataforma

Organizaciones (empresas cliente) de la instalación; solo la administración de la plataforma.

- **Código:** `backend/app/modulos/plataforma/` · **Pantallas:** `frontend/src/modulos/plataforma/`
- **API:** 4 operaciones en `/api/plataforma` (sección «Plataforma» de `/docs`)
- **Usa:** `acceso`, `comun`

<a id="productos"></a>

## Productos

Fichas técnicas de producto, su flujo de revisión y aprobación y sus partidas por país.

- **Código:** `backend/app/modulos/productos/` · **Pantallas:** `frontend/src/modulos/productos/`
- **API:** 36 operaciones en `/api/clasificacion`, `/api/flujo-clasificacion`, `/api/productos` (sección «Productos» de `/docs`)
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Usa:** `acceso`, `catalogo`, `clasificacion`, `comex`, `comun`, `documentos`, `empaque`, `etiquetado`, `facturacion`, `maestros`
- **Lo usan:** `catalogo`, `clasificacion`, `maestros`

<a id="recepcion"></a>

## Recepción e inventario

Recepción en bodega por contenedor (conteos, ajustes, cierre) y existencias por bodega.

- **Código:** `backend/app/modulos/recepcion/`
- **API:** 6 operaciones en `/api/existencias`, `/api/unidades` (sección «Recepción e inventario» de `/docs`)
- **Usa:** `acceso`, `catalogo`, `comun`, `facturacion`, `maestros`, `transporte`
- **Lo usan:** `empaque`, `transporte`

<a id="reportes"></a>

## Reportes

Generador de reportes: fuentes permitidas, vista previa, exportación y reportes guardados.

- **Código:** `backend/app/modulos/reportes/`
- **API:** 9 operaciones en `/api/reportes` (sección «Reportes» de `/docs`)
- **Usa:** `acceso`, `catalogo`, `comex`, `comun`, `documentos`, `seguimiento`

<a id="seguimiento"></a>

## Seguimiento e indicadores

Inicio, búsqueda global, seguimiento, alertas, tableros e indicadores por módulo.

- **Código:** `backend/app/modulos/seguimiento/` · **Pantallas:** `frontend/src/modulos/seguimiento/`
- **API:** 20 operaciones en `/api/alertas`, `/api/buscar`, `/api/dashboard`, `/api/seguimiento`, `/api/tableros` (sección «Seguimiento e indicadores» de `/docs`)
- **Se puede apagar:** Tracking and lead times
- **Usa:** `acceso`, `catalogo`, `comex`, `compras`, `comun`, `documentos`, `empaque`, `empresa`, `facturacion`, `transporte`
- **Lo usan:** `reportes`

<a id="transporte"></a>

## Transporte

Embarques, unidades de carga, hitos, recolección, costos logísticos y lead times.

- **Código:** `backend/app/modulos/transporte/` · **Pantallas:** `frontend/src/modulos/transporte/`
- **API:** 18 operaciones en `/api/embarques`, `/api/leadtimes`, `/api/recoleccion`, `/api/sugerencia-unidades`, `/api/unidades` (sección «Transporte» de `/docs`)
- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)
- **Se puede apagar:** Shipments, warehouse receipts, stock and logistics costs
- **Usa:** `acceso`, `catalogo`, `comun`, `documentos`, `facturacion`, `recepcion`
- **Lo usan:** `compras`, `empaque`, `maestros`, `recepcion`, `seguimiento`
