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
| `data/incisos_base.json` | 563 códigos por país con condiciones (`puntera`, `edadNac`, `estiloCalz`…) y conteo de artículos, construidos desde artículos de una empresa | **3. Empresa** | `CompanyClassificationHistory` (preferencias por país); ya no crea `IncisoNacional` |
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
- **Empresa**: `Producto`, `PartidaPais` (decisiones), `CompanyClassificationHistory`, `PalabraClave`, `SinonimoMaterial`, `OverrideArancel`; servicios `productos.py`, `conocimiento.py`.

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
