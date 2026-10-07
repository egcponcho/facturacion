# Clasificación arancelaria: tres capas

Regla principal: **la empresa describe sus productos y puede aportar historial,
pero solo fuentes oficiales determinan qué códigos, descripciones oficiales,
DAI, impuestos, regulaciones, notas legales y vigencias existen.**

| Capa | Qué es | Quién escribe | Puede crear códigos |
|---|---|---|---|
| **A. OFFICIAL TARIFF DATA** | Lo publicado por una autoridad (SIECA, SAT, DGA, ATENA, ANA…) con fuente, versión, vigencia, país y texto original | Solo cargas oficiales con fuente y versión (staging → diff → publicar) | Sí, solo ella |
| **B. CLASSIFICATION ENGINE** | Cómo se interpreta un producto: dominios, categorías, atributos, opciones, ámbitos, dependencias, reglas, guía del clasificador, casos de prueba | Configuración del motor (Aranceles → Motor) | No: solo elige entre códigos oficiales existentes |
| **C. COMPANY KNOWLEDGE** | Lo aprendido por la empresa: clasificaciones aprobadas, decisiones y correcciones, preferencias de línea nacional, palabras clave, sinónimos | La empresa, al clasificar y aprobar | No: solo ordena candidatos (`historical_confidence`) |

Flujo: ficha → hechos → reglas del motor → candidatos → árbol oficial vigente →
HS6 → línea SAC → código nacional por país → impuestos y regulaciones.
El historial empresarial solo reordena candidatos ya permitidos.

## Auditoría de datos incluidos (antes de este refactor)

| Archivo / dato | Contenido | Clasificación | Destino |
|---|---|---|---|
| `data/sac_oficial.json` | 6 607 capítulos, partidas y subpartidas, texto del ACI (SIECA, VII Enmienda, v6, ago-2025), extraído por `scripts/sieca` | **1. Oficial** | Árbol `NodoArancel`, versión SAC-2025-V6, fuente SRC-SIECA-ACI |
| `data/aci_incisos.json` → `codigo, descripcion, dai` | 8 242 filas = 7 517 líneas de 10 dígitos con DAI del ACI; 519 líneas remitidas a la Parte II vienen repetidas con tasas de la Parte II sin su país | **1. Oficial** | Árbol (una línea por código) + líneas nacionales de los países que aplican el SAC regional a 10 dígitos, con fuente y versión regional; el DAI de la Parte II queda vacío (por país) |
| `data/aci_incisos.json` → `cond` | 20 condiciones (género…) deducidas por nuestro script del texto oficial | **2. Motor** (interpretación) | Reglas `NATIONAL_SELECT` de capa sistema (guía del clasificador), nunca en el dato oficial |
| `data/incisos_base.json` | 563 códigos por país con condiciones (`puntera`, `edadNac`, `estiloCalz`…) y conteo de artículos, construidos desde artículos de una empresa | **3. Empresa** | `HistorialClasificacion` (tabla `historial_clasificacion`) (preferencias por país); ya no crea `IncisoNacional` |
| NI, CR, PA "códigos nacionales" | Venían solo de `incisos_base.json` (fuente `base`) | **3. Empresa / 6. Sin fuente oficial** | Se retiran del catálogo oficial: el país queda *Official national tariff data not available* hasta cargar su arancel |
| `data/sac_notas.json` | 518 notas: RGI, notas de sección, capítulo, subpartida y complementarias centroamericanas del ACI | **1. Oficial** | `NotaSAC` tipo `OFFICIAL_LEGAL` con fuente y versión |
| `data/sac_explicativas.json` | 31 resúmenes propios de Notas Explicativas | **5. Resumen interno** | `NotaSAC` tipo `CLASSIFIER_GUIDANCE`; la UI la muestra como guía, no como texto legal |
| `data/sac_base.json` | 418 descripciones propias de subpartidas (p. ej. "incluye carbonato de magnesio para escalar") | **3. Empresa / sin uso** | Se elimina |
| `productos.DESTINOS` | Países, dígitos, MCCA, "VAT 12%"…, base legal escritos en Python | **4. Demostración / 6. Sin fuente** | Se elimina; los países salen del paquete oficial 01 (`Countries`) y de la configuración |
| `nacional.impuestos_generales()` | Impuestos generados del texto "VAT 12%" con base legal "Verify against…" | **4. Demostración** | Se elimina del flujo; sin impuestos oficiales cargados el país lo dice |
| `data/oficial/01_*.xlsx` | Fuentes, versiones, países, control de capítulos, mapa dominio-capítulo, estado de datos oficiales | 1. Oficial (fuentes, versiones, países) + 2. Motor (control de capítulos, dominios) | Se cargan a su capa; los dominios son configuración del motor |
| `data/oficial/02_*.xlsx` | Dominios, atributos, opciones, ámbitos, reglas del sistema | **2. Motor** | Configuración del motor |
| `data/oficial/03_*.xlsx` | Plantillas vacías de códigos nacionales, regulaciones e impuestos | **1. Oficial** (sin filas) | Se mantiene como plantilla de carga oficial |
| `data/motor_atributos.json` | Categorías, atributos, opciones, derivaciones y textos de aduana | **2. Motor** (patrones con nombres de modelos de una marca → **3. Empresa**) | Motor; los nombres de modelos (old skool, sk8, vectiv…) salieron de los patrones y son palabras clave de la empresa de ejemplo (`data/demo/palabras_empresa_demo.json`) |
| `data/motor_reglas.json` | Reglas por categoría y casos esperados | **2. Motor** | Motor |
| `GENERICAS` en `categorias.py` | Categorías químico, materia prima, otro en Python | **2. Motor** escrito en código | Eliminado: `data/motor_tecnico.json` trae 20 categorías técnicas de químicos y 30 de materias primas, con sus atributos, opciones, ámbitos y dependencias como datos |
| `PalabraClave`, `SinonimoMaterial` | Aprendidos por la empresa | **3. Empresa** | Solo señales de interpretación |
| `IncisoNacional` fuente `aprendido`/`manual`/`archivo` | Códigos creados desde la ficha o desde un Excel sin fuente | **3. Empresa / 6. Sin fuente** | Ya no se crean como código; las preferencias van al historial y las cargas de líneas exigen fuente y versión oficial |
| `OverrideArancel` | Textos propios de la empresa sobre un dato oficial | **3. Empresa** | Se mantiene separado; nunca cambia el oficial |
| Productos, artículos, marcas del seed | Datos de la empresa de demostración | **3. Empresa (demo)** | Se mantienen como demo; ninguna partida sale de ellos |

## Código por capa

- **Oficial**: `models` `FuenteOficial`, `VersionDataset`, `NodoArancel`, `IncisoNacional`, `NotaSAC` (tipos OFFICIAL_*), `ReglaImpuesto`, `Regulacion`, `PaisArancel`; servicios `arbol.py`, `oficial.py` (fuentes, versiones, cargas por etapas), `nacional.py` (impuestos, regulaciones), `aranceles.py` (consulta de líneas y notas), `integridad.py` (auditor).
- **Motor**: `DominioClasificacion`, `CategoriaProducto`, `DominioCapitulo`, `ControlCapitulo` (qué capítulos usa el motor), `AtributoDef/Opcion/Ambito`, `ReglaClasificacion/CondicionRegla`; servicios `motor_clasificacion.py`, `ficha.py`, `composicion.py`, `descripciones.py`, `reglas.py`, `atributos.py`, `categorias.py`.
- **Empresa**: `Producto`, `PartidaPais` (decisiones), `HistorialClasificacion` (tabla `historial_clasificacion`), `PalabraClave`, `SinonimoMaterial`, `OverrideArancel`; servicios `productos.py`, `conocimiento.py`.

Las fichas SDS/TDS/COA son **evidencia técnica del producto** (capa empresa,
adjuntas al producto): alimentan hechos, nunca códigos.

## Auditor de integridad

`services/integridad.py` (`GET /aranceles/oficial/integridad`, pantalla
*Tariff schedule → Tariff data integrity*) revisa sin corregir nada:

| Nivel | Qué detecta |
|---|---|
| `SOURCE_MISSING` | Línea, versión, nota oficial, impuesto o regulación sin fuente oficial / base legal; país activo sin fuente (*Pending official source verification*) |
| `CONTAMINATION` | Línea con `fuente` distinta de oficial, línea que solo existe en la base de artículos de la empresa, resumen interno marcado como texto legal, regla del motor o de la empresa presentada como legal |
| `ERROR` | Línea sin país, que no cuelga de su subpartida, fuera de la nomenclatura base (SAC regional) de un país SAC10, largo inválido, versión de otro país, duplicada; impuesto sin tasa o base de cálculo |
| `VERSION_EXPIRED` | Línea, impuesto o regulación activa con vigencia vencida; ámbito sin versión vigente |
| `WARNING` | Versión publicada modificada a mano; versiones publicadas del mismo ámbito con vigencias traslapadas |

Las versiones publicadas no cambian: a mano o desde Excel solo se escriben
líneas de versiones en borrador o dinámicas; lo publicado llega por la carga
oficial por etapas (previa → diferencias → publicar).

El auditor encontró que el ACI incluido repetía 519 líneas remitidas a la
Parte II (DAI no armonizado) con tasas de la Parte II sin su país. Ahora se
carga una línea por código y su DAI queda vacío con la nota *DAI in Part II of
the ACI (country-specific)* (migración 0018).

## Químicos y materias primas (configuración del motor)

`data/motor_tecnico.json` (cargado por `atributos.cargar_tecnico` y
`categorias.sembrar`) define las categorías técnicas (ácido, sal, solvente,
adhesivo, pigmento…; hilado, tejido plano, de punto, recubierto, resina,
película, caucho, cuero, papel, metales…), sus atributos (CAS, fórmula,
composición, pureza, concentración, polímero, forma primaria, fibra, %,
gramaje, acabado, espesor, celular…) y en qué categoría se pregunta cada uno,
con dependencias (p. ej. *textured* solo si el hilado es de filamento). Las
categorías **no tienen códigos ni capítulos**: solo deciden qué preguntar; sus
`terminos` (y los de las opciones) son palabras del texto oficial que ordenan
candidatos del árbol. Todo se edita en *Aranceles → Motor* sin programar.

Un solo motor: `POST /clasificacion/sesion` (texto, dominio, categoría, ficha,
respuestas, países, versión) clasifica calzado, químicos o materias primas. La
ruta `/clasificacion/generico` se eliminó.

**SDS / TDS / COA**: `ProductoDocumento` (pestaña *Technical documents*). Sus
datos técnicos completan hechos vacíos de la ficha; rechazan cualquier campo
arancelario (`no_es_fuente_arancelaria`).

## Rutas y pantalla por capa

| Capa | API | Pantalla (*Tariff schedule*) |
|---|---|---|
| Oficial | `/aranceles/oficial/…` (fuentes, versiones, paquetes, integridad), `/aranceles/arbol`, `/aranceles/codigos`, `/aranceles/notas`, `/aranceles/impuestos`, `/aranceles/regulaciones` | **Official data** |
| Motor | `/clasificacion/configuracion/…` (dominios, categorías, atributos, reglas); edición en `/aranceles/categorias`, `/aranceles/atributos`, `/aranceles/reglas` | **Classification engine** |
| Empresa | `/conocimiento/…` (historial, decisiones, palabras clave, sinónimos) | **Company knowledge** |

El motor (`POST /clasificacion/sesion`) devuelve `legal_confidence` (solo reglas
y texto oficial) y `historical_confidence` (solo historial). Por país, cuando
varias líneas oficiales siguen posibles, el estado `historial` indica que el
historial eligió una de ellas, con su propia `historical_confidence`.

## Carga por capa y endurecimientos

**Archivos** (`app/datos.py`):

| Carpeta | Capa | Contenido |
|---|---|---|
| `data/oficial` | Oficial | Paquetes 01 y 03, árbol del ACI (`sac_oficial.json`, `aci_incisos.json` sin interpretaciones), notas legales |
| `data/motor` | Motor | Paquete 02, atributos, reglas, categorías técnicas, guía del clasificador, `interpretacion_aci.json` (lo que el clasificador lee del texto oficial) |
| `data/demo` | Demostración | Historial y palabras clave de la empresa de ejemplo, acuerdos comerciales de referencia (sin fuente oficial) |

**Arranque** (`app/cargas.py`): `cargar_base` carga el motor y, solo en una base
sin datos oficiales, lo oficial incluido; `cargar_demo` (solo `SEED_DEMO=1`)
configura los países de ejemplo (GT/SV/HN como SAC10), sus líneas regionales,
el historial, las palabras clave y los acuerdos. Con datos reales no entra nada
de la demostración y ningún país se declara SAC10 por su cuenta.

**Endurecimientos**

- Un lote oficial con errores no se publica, ni en parte (`lote_con_errores`);
  un paquete incluido con errores detiene la carga.
- Trazabilidad: una fuente respalda datos oficiales solo si nombra su documento
  o dataset, tiene enlace o referencia y fue verificada (fecha y quién); una
  versión publicada exige vigencia; toda línea, impuesto o regulación lleva su
  vigencia (propia o de su versión), nunca supuesta.
- El historial solo refuerza candidatos que ya salieron del árbol oficial y de
  las reglas; no crea candidatos ni quita la revisión.
- Incertidumbre = pendiente: el lote no aprueba casos con revisión o confianza
  legal baja; una línea nacional que solo prefiere el historial se confirma; un
  dato decisivo que se llenó por defecto deja el caso en revisión.
- Sin fallbacks: un país sin línea nacional oficial no recibe el código SAC
  regional en la OC o la factura; la base legal de un país no se arma con el
  nombre de su fuente.

## Código en la OC y la factura

El país destino de una OC es solo una proyección de a dónde irá la mercancía,
no el destino real. Por eso la OC y la factura llevan siempre la subpartida de
6 dígitos (SA) aprobada del producto, nunca la línea nacional de un país ni el
SAC regional. Las líneas nacionales por país siguen en la ficha del producto
como referencia. La migración 0023 deja en 6 dígitos las líneas de factura que
ya tenían un código más largo.

## Un solo vocabulario de atributos (G1)

- Cada dato del producto tiene un único atributo. Si un paquete trae un
  atributo que ya existe con otro código, lo declara en la columna «Same as»
  de la hoja Attributes: queda como alias (`AtributoDef.alias`) y sus
  opciones, ámbitos y las condiciones de reglas que lo nombran se resuelven al
  atributo de la ficha. Una ficha, una SDS o una carga que traiga el alias
  llega al mismo atributo.
- La carga rechaza (y el lote no se publica): un «Same as» a un atributo que
  no existe o de otro tipo de dato, una condición sobre un campo que no es
  atributo ni campo del producto (`categoria`, `dominio`, `origen`,
  `product_name`), un ámbito a una categoría o dominio inexistente, o un
  capítulo/partida/subpartida con dígitos incorrectos. Los códigos de categoría
  se guardan como existen (no se pasan a mayúsculas).
- La hoja Attribute_Scope_Conditions da condiciones a un ámbito (mismas
  columnas que Rule_Conditions).
- Producto sin categoría configurada: ficha genérica (descripción técnica y
  composición). Con categoría: solo su ficha propia.
- El país destino no es un dato del producto: cada país activo se resuelve por
  separado.

## La ficha sin casos escritos para una familia (G2)

El motor (`motor_clasificacion.py`), la ficha (`ficha.py`) y las descripciones
(`descripciones.py`) no nombran categorías, atributos ni opciones; una prueba
(`test_engine_code_names_no_family`) lo vigila.

- Detección: una palabra clave completa lo que implican sus respuestas y quita
  lo detectado cuyo ámbito ya no aplica; lo que el uso dice con evidencia manda
  sobre un valor puesto por defecto; un atributo cuya detección depende de otras
  respuestas se vuelve a deducir al final. Un patrón puede leer cualquier parte
  de la composición (`en: comp.<parte>`).
- Composición: cómo se lee una parte sale de los atributos que se derivan de
  ella (material o fibra); los modos de lectura son «superficie» y «contacto».
  Una parte que solo describe se marca `informativo` (no se exige reconocible).
- Descripción aduanera: «PARA HOMBRE / NIÑA / UNISEX…» son frases de las
  opciones (`texto_aduana` puede ser una lista de alternativas con condición);
  las palabras de las clases de material son datos (`vocabulario_aduana`) que
  cada categoría puede cambiar en su plantilla («como»).
- Cada categoría trae su dominio en los datos; la ficha genérica (descripción
  técnica y composición) es para productos fuera de una familia (sin dominio).

## Configuración completa desde el sistema (G3)

Todo lo que define una familia se configura en Aranceles → Motor de
clasificación, o en un paquete Excel, y se valida antes de guardarse
(`services/validacion_config.py`): una referencia a un atributo, opción,
parte de la composición, categoría o dominio que no existe, un patrón que no
compila o un dato de otro tipo se rechaza con un mensaje que dice qué y dónde.

- Atributos: sección de la ficha, alias, respuesta por defecto, «solo
  descriptivo», derivación, patrones de detección (y los que dicen «no»),
  bloqueos y texto aduanero (botón «Comportamiento»).
- Opciones: patrones, implicaciones, texto aduanero y bloqueos.
- Ámbitos: categoría/dominio existentes, dígitos correctos y condiciones válidas.
- Categorías: nombre aduanero, capítulos, alias, cómo se reconocen en el nombre
  y plantilla de la descripción aduanera; una categoría sin dominio usa la
  ficha genérica.
- Clases de material (`ClaseMaterial`): una familia agrega su clase (p. ej.
  cerámica) con sus palabras y su palabra aduanera; la composición la reconoce
  y una derivación «clase» la lleva a las opciones de un atributo.
- Reglas: campos de condiciones, atributos que pregunta y el campo de un mapa
  de códigos deben existir.
- Paquete: hoja Categories y columnas JSON de comportamiento en Attributes y
  Attribute_Options; cada fila inválida se reporta y el lote no se publica.
- «Género» y «Para quién es» pasan a ámbitos por dominio (ropa y calzado),
  opcionales en accesorios personales (migración 0026).
- El auditor de integridad revisa toda la configuración guardada
  (CONFIG_INVALID).

## Búsqueda en el texto oficial (G4)

- Cada término se compara por su raíz (taladro → taladros, taladradoras).
- Vocabulario de búsqueda (`SinonimoBusqueda`, Aranceles → Vocabulario de
  búsqueda): una palabra en inglés o un término comercial y las palabras del
  texto oficial a las que equivale (drill → taladro). Trae una base editable.
- Un candidato que solo sale del texto nunca pasa de confianza baja: siempre
  queda para revisión. Media o alta solo con reglas.
- Si el texto coincide igual o mejor en un capítulo que no se clasifica solo
  (manual o no habilitado), el motor lo dice y deja el caso en revisión.

## Integración con artículos, aprobación y documentos (G5)

- Aprobar un producto exige su subpartida (la que va en la OC y la factura),
  no la línea nacional de cada país. Una línea que falta elegir o que solo el
  historial prefiere queda pendiente y una persona la confirma después, país
  por país (`GET/POST /productos/{id}/partidas/{país}`); solo lo confirmado se
  guarda como decisión de la empresa.
- Unidades de medida en un solo módulo (`services/unidades.py` y
  `frontend/src/unidades.js`, verificados por una prueba): pares, unidades,
  docenas, juegos, kg, g, L, ml, m, m², m³ y rollos, con sus alias.
- La ficha en PDF y Excel y el reporte de productos usan las etiquetas del
  catálogo (atributos, opciones, partes, categorías) y el orden de países
  configurado.
- La carga masiva de artículos arma sus columnas de la ficha con el catálogo
  (también género y «para quién es», como cualquier atributo) y reconoce sus
  alias.

## Reglas para químicos y materias primas, y familias nuevas (G6)

- `data/motor/motor_reglas_tecnicas.json`: 90 reglas de las categorías
  técnicas (químicos de los capítulos 28, 29, 32, 34, 35 y 38; plásticos,
  caucho, cuero, textiles, papel y metales), según las notas de capítulo y las
  partidas del SA. Son configuración del motor (editables; una regla editada no
  se pisa). La carga de la base solo retira reglas suyas (R-MJS-, R-TEC-),
  nunca las de un paquete o de la empresa.
- Una regla que apunta a un capítulo que se clasifica a mano (o no está
  habilitado) lo dice y deja el caso en revisión.
- Una partida con una sola subpartida se escribe como esa subpartida (3910 →
  3910.00) al guardar una regla.
- Paquete del motor, para traer una familia completa: Domains,
  Material_Classes, Categories, Attributes (con columnas de comportamiento),
  Attribute_Options, Attribute_Scope (y _Conditions), Classification_Rules con
  su acción (Action, Codes, By attribute, Code map JSON, Ask attributes,
  Message) y Rule_Conditions. `tests/test_familias_genericas.py` arma una
  familia nueva (vajilla) solo con un paquete y la clasifica.
