# Reestructuración · Fase 2: arquitectura objetivo

Define hacia dónde va el sistema y qué reglas siguen las fases 3 a 10. Los códigos (`G-01`, `D-01`…) remiten a [`01-diagnostico.md`](01-diagnostico.md).

## 1. Tres capas: núcleo, configuración e integración

| Capa | Qué contiene | Regla |
|---|---|---|
| **Núcleo** | Conceptos con significado estable en cualquier empresa: orden de compra y sus posiciones, factura y sus líneas, lista de empaque, embarque, unidad de carga, recepción, producto y variante, receta de empaque, etiqueta. Sus estados y transiciones (`core/estados.py`) son reglas del sistema. | Tablas y columnas tipadas, con llaves foráneas. Nada de JSON para lo que tiene estructura. |
| **Configuración de la empresa** | Catálogos (sociedades, centros, almacenes, monedas, unidades, tipos de empaque…), atributos de variante, familias, campos propios, etiquetas de estado, series, roles, módulos activos, tableros, reglas de empaque y de lead time, nomenclatura aduanera por país. | Datos por `organizacion_id`, editables desde la interfaz y validados en el servidor. El código no conoce valores concretos. |
| **Integración** | Cómo se traducen esos conceptos a un sistema externo: mapeos de campos y códigos, adaptadores de formato, referencias externas, bitácora de ejecuciones. | Módulo aparte (`modulos/integraciones`). El núcleo no importa nada de él; la integración llama a los servicios del núcleo, que aplican las mismas validaciones y permisos que la interfaz. |

**Criterio para decidir dónde va algo:**

- **Núcleo:** la regla vale en cualquier empresa. Por ejemplo, no se factura más de lo pedido.
- **Configuración:** depende de la empresa. Por ejemplo, qué códigos de liberación manda su ERP.
- **Adaptador:** depende del sistema externo. Por ejemplo, cómo se llama la columna del número de OC en su archivo.

No todo se vuelve configuración. Un concepto con significado estable queda tipado (§1, núcleo).

## 2. Módulos y responsabilidades

Una entrada de menú por módulo (`frontend/src/nucleo/modulos.js`). Cada módulo abre en su **Resumen** (tablero con indicadores reales), sigue con la operación y termina en su configuración. Análisis queda para cruces entre módulos y reportes.

| Módulo | Propósito | Entidades | Resumen | Configuración propia |
|---|---|---|---|---|
| Compras | Recibir y gestionar las OCs | OC, posición, liberación, aprobación, importación | Tablero de compras (`/tableros/compras`, en el módulo) | Proveedores, sociedades, contactos, perfiles de importación |
| Facturación | Facturar lo pedido y empacarlo | Factura, línea, lista de empaque, receta de empaque | Tablero de facturación | Tipos de empaque, series, plantillas de caja |
| Logística | Mover, recibir y medir tiempos | Embarque, unidad de carga, evento, recepción, existencias, lead time | Tablero de logística | Centros, almacenes, puertos, transportistas, tipos de unidad, liberaciones, lead times |
| Productos | Definir qué se compra | Producto, variante (artículo), pack o kit, ficha técnica, clasificación | Portada de productos | Familias, atributos, escalas, marcas, grupos, listas, acuerdos, dominios |
| Etiquetas | Diseñar e imprimir etiquetas | Tipo, diseño, uso, trabajo, generación | Portada de etiquetas | Tipos, campos, reglas |
| Análisis | Cruces y reportes | Indicadores, reportes guardados | Tablero general | Metas |
| Configuración | Lo de toda la organización | Empresa, usuarios, roles, módulos, campos propios, integraciones | Portada de configuración | — |

Cada acción se ejecuta en **un solo servicio** del servidor. Si la interfaz la ofrece en dos lugares (la ficha y la lista, por ejemplo), ambos llaman a la misma ruta.

## 3. Niveles de configuración

| Nivel | Dónde | Ejemplos | Quién lo cambia |
|---|---|---|---|
| Técnico (instalación) | Variables de entorno (`core/config.py`) | `DATABASE_URL`, `SECRET_KEY`, `ANTHROPIC_API_KEY`, `COOKIE_SEGURA` | Quien despliega |
| Global (plataforma) | Tablas compartidas sin `organizacion_id` | Países, nomenclatura oficial del arancel | Administrador de la plataforma |
| Empresa | Tablas con `organizacion_id` y `organizaciones.preferencias` | Catálogos, reglas, módulos, campos propios, integraciones | Administrador de la empresa (permisos `empresa.*`, `catalogos.*`) |
| Usuario | `usuarios.preferencias`, borradores, vistas guardadas | Idioma, tema, columnas, filtros | El propio usuario |

Los parámetros críticos (series, estados de liberación, módulos, integraciones) exigen permiso de administración. Al guardarse se validan para que el sistema no quede inconsistente: un catálogo en uso no se borra, se desactiva.

## 4. Integración con cualquier ERP

### 4.1 Modelo

| Tabla | Para qué |
|---|---|
| `integraciones` | Un sistema externo de la empresa. Guarda: <ul><li>código y nombre;</li><li>adaptador (`archivo_tabular`, `json`);</li><li>parámetros validados;</li><li>si está activo.</li></ul> No guarda credenciales en claro. |
| `integracion_mapeos` | Por integración, entidad y dirección (entrada o salida). Guarda: <ul><li>campo interno → campo externo;</li><li>valores por defecto;</li><li>traducción de códigos (p. ej., estado externo `300` → liberada);</li><li>versión (cada cambio crea una nueva y la anterior se conserva).</li></ul> |
| `referencias_externas` | `(integracion, entidad, codigo_externo) → id interno`, única. Sirve para relacionar, actualizar en lugar de duplicar y saber el origen de un registro. |
| `integracion_ejecuciones` | Bitácora de cada ejecución: <ul><li>quién la lanzó y cuándo;</li><li>entidad y dirección;</li><li>huella del contenido;</li><li>estado (`PREVIA`, `APLICADA`, `CON_ERRORES`, `FALLIDA`);</li><li>conteos (creados, actualizados, sin cambio, rechazados) y errores por fila.</li></ul> La misma huella ya aplicada no se vuelve a aplicar. |

### 4.2 Contrato del adaptador

```python
class Adaptador(Protocol):
    codigo: str
    def leer(self, contenido: bytes, parametros: dict) -> list[dict]: ...        # filas con nombres externos
    def escribir(self, filas: list[dict], parametros: dict) -> tuple[bytes, str]: ...  # contenido y tipo MIME
```

**El mapeo traduce entre los nombres externos y los internos.** Las entidades (`ordenes_compra`, `facturas`…) declaran sus campos internos, cuáles son obligatorios y su tipo, y llaman a los servicios del núcleo. Un ERP nuevo se agrega con un adaptador o con un mapeo, sin tocar el núcleo.

**Alcance implementado en esta reestructuración:**

- **Adaptadores:** archivo tabular (CSV y Excel) y JSON, ambos genéricos y probados.
- **Entrada:** órdenes de compra, sobre el importador existente, que ya valida y deduplica.
- **Salida:** facturas finalizadas.

No se implementan adaptadores para un ERP concreto (SAP, Oracle, Dynamics, Odoo). Se conecta cualquiera que pueda exportar o importar un archivo tabular o JSON, configurando su mapeo. Una conexión directa por API a un ERP concreto queda como trabajo futuro sobre el mismo contrato.

## 5. Modelo de datos: decisiones

| Hallazgo | Decisión | Migración |
|---|---|---|
| D-02 y G-07 (variante en dos lugares) | Toda lectura y filtro pasa por los valores de variante (`variante` en las líneas, `articulo_atributos` en el artículo) mediante `maestros/variantes.py`. Las columnas `estilo/color/talla` quedan solo como compatibilidad de escritura. | Ninguna ahora. Retirarlas es una fase posterior, cuando nada las lea. |
| D-03 (códigos sin llave) | `unidades_medida.base` y `atributos_variante.unidad` entran en `REFERENCIAS`. | Nueva: deja en nulo los códigos huérfanos y crea las llaves. |
| G-04 (aduana por país) | El país del arancel guarda el nombre de su nomenclatura, de su derecho arancelario y de su identificación fiscal. Los documentos los toman del país destino o del país del proveedor. | Nueva: columnas opcionales en `paises_arancel` (o equivalente) con los valores actuales como dato inicial de los países que ya los usan. |
| I-01 a I-04 | Tablas de §4.1. | Nueva. |
| **D-01** (familias) | **Requiere tu decisión** (§6). | — |
| **D-04** (terceros) | **Requiere tu decisión** (§6). | — |

## 6. Decisiones pendientes del usuario

Según tu regla, cuando un cambio exige migrar datos existentes, primero van las alternativas y sus consecuencias. Hasta decidirse, no se construye nada nuevo encima de estas estructuras.

### 6.1 D-01: una sola forma de agrupar productos

- **A (recomendada). `grupos_producto` como única taxonomía.**
  - El grupo de artículo queda como agrupación comercial, con su regla de días extra.
  - La categoría de artículo pasa a ser un nivel `CATEGORIA` del árbol.
  - Las familias de clasificación se cuelgan de la familia de producto mediante una referencia `grupos_producto.categoria_clasificacion_id`.
  - Las tablas de etiquetado anteriores se retiran.
  - *Consecuencias:* una migración que copia y enlaza, una versión de rollback y la actualización de reglas de empaque, etiquetas y reportes. Los datos se conservan. Es el cambio de mayor alcance.
- **B. Mantener las taxonomías y solo enlazarlas.**
  - La familia de producto sugiere la categoría de clasificación y el grupo de artículo apunta a la familia.
  - Se retiran solo las tablas de etiquetado anteriores.
  - *Consecuencias:* menos riesgo; siguen existiendo «grupo» y «categoría de artículo» como conceptos aparte.
- **C. No tocar nada.** Solo se retiran los textos que confunden. La duplicidad sigue.

### 6.2 D-04: terceros

- **A. Completar `terceros`.** Proveedor, transportista y la parte «facturar a» y «notificar a» apuntan a un tercero obligatorio. Una migración crea el tercero de cada proveedor y transportista que no lo tenga.
- **B. Retirar `terceros`.** Cada catálogo conserva sus datos de contacto. Una migración copia direcciones y contactos de vuelta.
- **C. Dejarlo como está** (opcional), documentado.

### 6.3 Lengua de origen de los textos

- **A (actual, recomendada).** Claves en inglés y español desde `es.json`. Lo que ve el usuario está en español; el código, los comentarios y la documentación están en español. Excepción técnica documentada.
- **B. Español como lengua de origen.** Se reescriben unas 6 700 claves y los cinco catálogos se regeneran. Hay riesgo de perder traducciones existentes al chino, hindi y árabe si no se remapean una a una.

## 7. Sistema de diseño

Se conserva la base del ERP aplicada en `ca63bb7`: paleta azul petróleo y marino, Plus Jakarta Sans y tokens en `styles.css`. Se completa con:

- **Escala tipográfica:** nueve pasos sobre la base de 14 px, de `--t-2xs` (≈10 px, insignias) a `--t-3xl` (≈29 px, cifra principal), que extienden los seis tokens `--t-*` que ya existían. Se reemplazan los tamaños escritos a mano (U-01).
- **Colores fuera de tokens** pasan a tokens semánticos (U-02).
- **Patrón de módulo:** barra de módulo con su acción principal, luego Resumen, luego lista con filtros, luego ficha con pestañas y acciones en contexto. La ficha del producto agrega «Uso» (dónde se usa) y «Empaque» (M-03).
- **Paneles laterales** en lugar de ventanas emergentes largas en los documentos (U-03), por etapas y empezando por la lista de empaque.

## 8. Orden de ejecución (un commit por paso)

1. Seguimiento genérico: filtros por atributos de variante y liberaciones desde el catálogo (G-01, G-02).
2. Variante genérica en tablero de embarques y ficha (G-03).
3. Aduana e identificación fiscal por país; valores fijos de unidad y moneda; textos neutrales (G-04 a G-06, G-08).
4. Llaves foráneas de unidades (D-03).
5. Capa de integración: modelo, adaptadores, entrada de OCs, salida de facturas, pantalla y pruebas (I-01 a I-04).
6. Resumen por módulo en Compras, Facturación y Logística; Análisis solo con cruces (M-01, M-02).
7. Ficha del producto: «Uso» y «Empaque» (M-03).
8. Escala tipográfica y colores en tokens (U-01, U-02).
9. Portada de Configuración (M-04, U-05).
10. Limpieza del código sin uso verificado (§3.6 del diagnóstico).
11. Pruebas completas (servidor, migraciones, lint, build y navegador) e informe final.

Los pasos que dependen de §6 se hacen después de tu decisión.
