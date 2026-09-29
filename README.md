# Workspace de proveedor: OC → factura → packing list → cajas → transporte

Sistema para que cada proveedor (y el equipo interno) arme sus facturas desde las OCs, las distribuya en packing lists y cajas, y el equipo de importaciones las asigne a unidades de carga y dé seguimiento al embarque.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL (SQLite para desarrollo rápido).
- **Frontend:** Vue 3 + Vite, sin librerías de componentes ni de gráficas (íconos y gráficas en SVG propio).
- **Probado:** 18 pruebas del flujo completo en PostgreSQL (17 en SQLite) y un recorrido en navegador real de punta a punta, en escritorio y en móvil.

## Arrancar

### Opción rápida (SQLite, sin instalar base de datos)

```bash
# Terminal 1: API en http://localhost:8000 (documentación en /docs)
cd backend
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# Terminal 2: interfaz en http://localhost:5173
cd frontend
npm install
npm run dev
```

La primera vez se crean datos de prueba (TNF y Vans, OCs con tallas, plantillas y un embarque con un 40HC).

### Con Docker y PostgreSQL

```bash
docker compose up --build
```

Queda todo en http://localhost:8000 (la API sirve también el frontend compilado).

### En la nube (Render, gratis)

El repositorio incluye `render.yaml`, que crea la base PostgreSQL y el servicio web desde el `Dockerfile`.

1. Entra a https://dashboard.render.com/blueprints y pulsa **New Blueprint Instance**.
2. Conecta tu GitHub y elige este repositorio (rama `main`).
3. Pulsa **Apply**. En unos minutos queda en `https://facturacion-XXXX.onrender.com`.

`SECRET_KEY` se genera sola y los datos de prueba se cargan al primer arranque (`SEED_DEMO=1`; ponlo en `0` cuando uses datos reales).
Limitaciones del plan gratuito: el servicio se duerme tras 15 minutos sin uso (el primer acceso tarda ~1 minuto), la base gratuita expira a los 30 días y los adjuntos se guardan en disco temporal, así que se pierden al reiniciar.

La misma imagen funciona en Railway, Fly.io o Google Cloud Run: define `DATABASE_URL` (se aceptan `postgres://` y `postgresql://`) y `SECRET_KEY`; el puerto se toma de `PORT`.

### Usuarios de prueba (contraseña `demo123`)

| Correo | Rol |
|---|---|
| tnf@demo.com | Proveedor The North Face |
| vans@demo.com | Proveedor Vans |
| interno@demo.com | Equipo de importaciones |
| admin@demo.com | Administrador |

## Recorrido de 5 minutos

Los datos de prueba ya traen historia: facturas de meses anteriores, un contenedor recibido, otro en tránsito y una factura lista para embarcar, para que el tablero de inicio tenga contenido desde el primer día.

1. Entra como **tnf@demo.com** (en la pantalla de inicio de sesión basta un clic en “The North Face”). El **Inicio** muestra lo que falta facturar, empacar y finalizar, dónde está la mercancía y los envíos en camino.
2. En *Órdenes de compra*, en la OC 4400003845, pulsa **Facturar** (o ábrela y cambia “A facturar” para tomar solo una parte; se pueden juntar varias OCs). Revisa la selección y pulsa **Crear factura**.
3. En la factura, los pasos de arriba dicen qué falta. Pulsa **Empacar pendientes**: crea el packing list con todo y lo abre.
4. En *Por empacar*, pulsa **Empacar automático**. Los artículos con casepack se empacan con esa cantidad exacta por caja; los demás usan la plantilla sugerida (la que se usó antes con ese estilo). El sobrante que no llena una caja va a una caja parcial con peso estimado (o se queda sin caja, si lo prefieres).
5. En *Revisión*, **Confirmar estimados** y **Finalizar packing list**. Vuelve a la factura, escribe número y fecha en la cabecera y pulsa **Finalizar**.
6. Entra como **interno@demo.com**, abre *Embarques* → EMB-0003, elige el 40HC #1 y pulsa **Asignar carga**: marca la factura y asígnala; lo que ya está finalizado se confirma en el mismo paso. Luego **Registrar salida**. El proveedor ve el tránsito desde su factura y su inicio.

7. En *Seguimiento* se ve cada OC (y, al abrirla, cada SKU por etapa: por liberar, por facturar, en PL, en unidad de carga, en tránsito, recibido) y cada embarque con sus unidades, con la holgura frente a la fecha requerida en tienda. Todo se descarga en PDF o Excel. En *Mantenimiento* están todos los datos maestros.

## Datos maestros (Mantenimiento)

Un solo lugar, con alta, edición, baja y filtros (listas desplegables con búsqueda), para: **sociedades**, sus **centros**, **contactos**, **almacenes**, **países**, **puertos**, **marcas**, **grupos de artículos**, **proveedores**, **artículos**, **prepacks**, **transportistas** y **tipos de unidad**. No se borra lo que está en uso.

- **Proveedores:** código, nombre, razón social, identificación fiscal, país, dirección y contacto (salen como exportador en la factura y el packing list). Cada proveedor tiene **sus marcas** y **las sociedades con las que trabaja**, y sus propios **artículos**. Todo es consistente: un artículo solo puede ser de una marca de su proveedor; un proveedor no deja de manejar una marca de la que tiene artículos; al importar una OC, cada SKU debe ser del proveedor de la OC y el proveedor debe trabajar con la sociedad de la OC.
- **Transportistas:** código (p. ej. SCAC o IATA), nombre, tipo (marítimo, aéreo, terrestre o multimodal), identificación fiscal, contacto y **sociedades con las que trabajan**. El embarque solo ofrece los del modo que trabajan con la sociedad del centro.
- **Tipos de unidad:** el mantenimiento de los modos de transporte. Cada tipo dice su modo (marítimo, aéreo, terrestre), su **modalidad** (FCL, LCL, aérea, FTL, LTL), su capacidad en m³ y kg y si exige sello (p. ej. 20GP, 40GP, 40HC y LCL en marítimo; guía aérea; camión completo o consolidado). Se agregan los que se necesiten.
- **Puertos:** cada uno es de un tipo (puerto marítimo, aeropuerto o aduana terrestre). Un **centro** tiene su puerto principal y **otros puertos de llegada**.

- **Sociedades y centros:** cada sociedad (8000 El Salvador, PA01 Panamá, GT01, HN01, NI01, CR01) tiene sus centros asignados. La sociedad de la OC es a quien se **factura**; su centro es el **notify party** (bodega que recibe) y tiene país y **puerto de llegada**. El **centro de destino** de la OC (p. ej. 2220) es otro centro del catálogo y dice a qué país llega al final; ya no hay un catálogo aparte de países de destino. En la tabla de sociedades se ven sus centros y contactos, y en la de grupos sus artículos: un clic lleva al catálogo filtrado.
- **Contactos:** personas de una sociedad (facturación) o de un centro (notify, logística) con uno o varios correos y teléfono. Salen en la factura, el packing list, el embarque y el Excel.
- **Almacenes:** separación del inventario en el sistema (virtual, detalle, mayoreo); no son lugares físicos.
- **Artículos:** número de artículo numérico (p. ej. `30095120001`), estilo, color, talla, marca, grupo y **unidad de medida** (PAR, UN o CJ), visible en el maestro, la OC, la factura, el packing list y la explosión. Aquí se crean los **sólidos**, con casepack (calzado) o sin casepack (ropa). Se cargan por archivo (`plantilla_articulos.csv`) o a mano.
- **Prepacks:** un prepack es un **artículo** con su propio código de producto, igual que un sólido. Se crea en un solo paso en la pestaña Prepacks: código de producto, estilo, color, **prepack ID** (su talla; usualmente 2 letras y 2 números, p. ej. `AB12`) y su curva o **explosión**, armada solo con sólidos del mismo estilo y color (p. ej. AB12 de VN000EE3 BLK Negro: 7:1, 8:2, 9:3, 10:3, 11:2, 12:1 = 12 pares por caja). Su unidad es CJ (caja prepack). La explosión **se puede ver** desde el maestro, la OC, la factura, el packing list y el seguimiento (con el total por talla según las cajas), pero **nunca se modifica**; para otra distribución se crea un prepack nuevo. Tampoco cambian el estilo, color, talla o unidad de un sólido que forma parte de una explosión. Carga masiva con `plantilla_prepacks.csv` (sku_prepack, prepack_id, descripción, sku sólido, cantidad).

## Órdenes de compra

- Número de 10 dígitos que empieza con **44** (p. ej. 4400003856); posiciones de 10 en 10.
- Cada posición trae el **SKU**, que debe existir en el maestro de artículos: de ahí salen estilo, color, talla, marca, grupo, tipo de empaque y casepack (si la OC trae casepack, manda el de la OC).
- Cabecera: sociedad (facturar a) y centro (notify; debe ser de la sociedad), centro de destino (el país final), puerto de despacho proyectado, país de origen y de procedencia, **fecha XF original y actualizada**, fecha requerida en tienda, precio y total por posición.
- **Almacén por posición:** una misma OC (misma sociedad y centro) puede mandar cada posición a un almacén distinto, por ejemplo BF19 detalle y BF20 mayoreo. El almacén debe ser de la misma sociedad. Se ve en la OC, la factura, el packing list y el seguimiento, y se puede filtrar por él.
- **Liberaciones (dos equipos):** la **comercial** es `P` (pendiente) o `C` (liberada; si viene vacía se llena como C). La **logística** es **304** no liberada, **300** liberada o **301** liberada con cambios posteriores, y viene en `liberacion_logistica`. Sin liberación comercial no hay logística: con P siempre es 304, y un archivo que traiga P con 300/301 se rechaza. Una OC nueva sin código logístico queda en 304; una ya liberada (300) que cambia pasa a 301. Solo se factura con **C y 300/301**. En la lista de OCs se ven las dos liberaciones y se filtra por cada una.

## Reglas de empaque

- **Sólido con casepack (calzado):** cada caja lleva exactamente el casepack, mismo estilo, color y talla; no se mezclan tallas. Solo la última caja puede quedar incompleta, y queda como aviso para confirmarla con el Commercial Brand Manager.
- **Prepack:** una curva por caja master, con la distribución de tallas fija; no se agregan ni quitan tallas.
- **Casepack especificado / no especificado (ropa y accesorios):** si el artículo trae casepack se respeta; si no, se elige la cantidad (plantilla) y se puede consolidar en cajas mixtas.
- **Etiqueta:** *estándar* si la caja lleva una sola OC, estilo, color y talla; *consolidada* si lleva varias. Sale en el packing list y en el Excel.
- **Centro de destino:** nunca se mezclan destinos en una misma caja.
- **Pallets:** si la mercancía viaja en tarimas, las cajas se paletizan en el packing list (medidas y tara del pallet). El volumen usa las medidas del pallet y el peso bruto suma la tara; sale en el Excel.

## Embarques más estrictos

- **Todo según el modo:** un embarque marítimo solo ofrece puertos marítimos, navieras y contenedores; uno aéreo, aeropuertos, aerolíneas y guías; uno terrestre, aduanas, transportistas terrestres y camiones. La **modalidad es de cada unidad** (sale del tipo de unidad), así que un embarque marítimo puede ser **FCL, LCL o MIXTO** (p. ej. un 40HC y un LCL con el mismo BL). El modo no cambia cuando ya tiene unidades.
- Mientras el embarque está **planificado** se agregan unidades de carga, se asigna, confirma, mueve o quita carga. Al registrar la **salida** la carga queda **cerrada**: ya no hay tentativos, ni se agregan, quitan o mueven PL o contenedores, y el BL, transportista, origen y ETD quedan fijos (la ETA y el destino, al registrar el arribo).
- Los eventos van en orden según el estado (recolección → salida → tránsito → arribo → liberación → entrega → recepción); no se aceptan fechas futuras ni anteriores al último evento.
- No se asigna carga que supere la capacidad nominal de la unidad (según su tipo).
- **Centro que recibe:** cada embarque llega a un solo centro (el de la OC). El destino **se sugiere** con el puerto principal del centro y se puede cambiar por cualquiera de sus otros puertos de llegada del mismo modo; los puertos se eligen del catálogo. Si el embarque aún no tiene centro, lo define la primera carga; no se mezclan centros.
- **Recolección:** se marca por PL con su fecha y se compara con la fecha XF; la salida completa la fecha a los que no la tenían.
- Cada contenedor muestra sus marcas, la primera fecha requerida en tienda y los días de margen o de atraso frente a la ETA.

## Tablas

El menú va en su propia fila, a todo lo ancho, para que nunca se encime con los controles. Las tablas usan todo el ancho de la pantalla. Todas tienen altura fija con encabezado fijo, orden por columna (clic en el encabezado: ascendente, descendente, sin orden) y paginación con filas por página. Los filtros de Órdenes, Seguimiento y Mantenimiento se arman con los valores que realmente existen, usan listas con búsqueda (sin importar acentos, por código o nombre) y se muestran como chips que se quitan con un clic.

## Seguimiento

Tres tableros sin información repetida; los dos de mercancía comparten los mismos filtros (marca, grupo, estilo, color, talla, SKU, almacén, etapa, unidad de carga, BL/AWB, embarque, proveedor, sociedad, centro, riesgo de llegar tarde y rangos de ETA, XF y fecha en tienda). Los indicadores son clicables y aplican su filtro. Cada tablero se descarga en **PDF o Excel** con los filtros de la pantalla.

- **Órdenes de compra:** liberadas o no (comercial P/C y logística 304/300/301), estado de cada OC, barra de avance del pedido a lo recibido, XF vencida sin facturar y holgura frente a la fecha en tienda. Cada OC **se abre en su detalle por SKU**: etapa, factura y PL, embarque y unidad, llegada y margen frente a tienda (reemplaza el antiguo tablero “Mercancía por SKU”). El Excel trae una hoja con ese detalle.
- **Embarques y unidades de carga:** un renglón por embarque y su documento de transporte (BL, AWB o carta de porte) con modo, modalidad (FCL, LCL o mixto), transportista, ruta, salida y llegada. Se abre en sus **unidades** (contenedores, guías o camiones, con tipo, modalidad y sello) y cada unidad en **todo lo que lleva por orden de compra**, con la explosión de cada prepack. Filtro por modo.
- **Facturación y packing lists:** indicadores (facturas e importe, abiertas, empacando, listas para embarcar, con datos pendientes), documentos por paso, carga empacada (cajas, pallets, peso y volumen) y una fila por packing list.

## Factura comercial y packing list (PDF y Excel)

Desde cada factura y cada packing list se descarga el documento en **PDF** (listo para imprimir y firmar) o **Excel**, con la misma estructura y lo que piden las aduanas de Centroamérica (CAUCA/RECAUCA y la DUCA):

- **Partes:** exportador/vendedor (razón social, identificación fiscal, dirección, contacto), importador/facturar a (sociedad con su NIT/RUC) y consignatario/notify party (centro, puerto de llegada y contacto).
- **Condiciones:** número y fecha, OCs, incoterm, moneda, condiciones de pago, países de origen, procedencia y destino, centro de destino, medio de transporte, puertos de embarque y destino, transportista y BL/AWB/carta de porte, contenedores o guías con su sello.
- **Detalle:** por línea, OC y posición, código y UPC, descripción comercial (marca, estilo, color, talla, prepack), **partida arancelaria SAC**, país de origen, cantidad, unidad, precio unitario y total. En el packing list, por grupo de cajas: rango y número de cajas, contenido por caja, medidas, pesos neto y bruto por caja y totales, m³, pallet y tipo de etiqueta; además los pallets y lo pendiente de empacar.
- **Totales:** cantidad por unidad de medida, bultos, pesos neto y bruto, volumen, valor total, **total en letras** (“SON: … DÓLARES CON 00/100”) y **total de bultos en letras**; marcas de embarque (shipping marks) y la **declaración firmada** del exportador.
- Mientras la factura o el PL no están finalizados, el PDF lleva la marca de agua **BORRADOR · NO OFICIAL**. Cada página lleva “Página X de Y”.

Altas, ediciones, cambios de contraseña y bajas se hacen en ventanas emergentes (Mantenimiento, Plantillas y Usuarios).

## Cómo quedaron las reglas principales

**Todo se maneja por cantidades, con la misma fórmula en cada nivel:** disponible = cantidad del nivel de arriba − lo asignado en documentos activos.

| Nivel | Se asigna | Lo libera |
|---|---|---|
| Posición OC → factura | cantidad parcial o total | quitar la línea, reducir la cantidad o cancelar la factura |
| Línea de factura → packing list | cantidad parcial o total, en uno o varios PL | quitar del PL, reducir en la factura o cancelar el PL |
| Fila del PL → cajas | cajas completas, parciales o mixtas | desempacar |

- **Reducir en la factura** algo que ya está en PL: el sistema avisa qué PL tienen esa cantidad y ofrece liberar automáticamente lo que no está en cajas. Lo empacado nunca se toca solo.
- **Quitar líneas** con cantidades en PL: muestra el impacto (PL y cajas) y pide confirmar antes de quitar en cascada.
- **Empacar automático:** un solo paso para todo el PL (o las filas elegidas), cada fila con su propia plantilla. La sugerencia sale del historial: la última plantilla usada en esa fila o, si no hay, con la que el proveedor empacó el mismo estilo. El sobrante que no llena una caja va a una caja parcial o se deja sin caja para armar cajas mixtas.
- **Mover a otro PL** toma una cantidad de lo que no está en cajas (ya no hace falta “dividir” antes). Para llevar lo empacado se usa **Mover cajas**, que se lleva el contenido y recalcula la numeración.
- **Plantillas:** solo llenan datos. Cada caja guarda sus propios valores; editar la plantilla no cambia cajas existentes. No es obligatorio usarlas. Cualquier caja se puede guardar como plantilla nueva.
- **Cajas parciales:** medidas de la plantilla, peso neto proporcional y bruto = neto + tara. Quedan marcadas como “peso estimado” y el PL no se finaliza hasta confirmarlas.
- **Cambios masivos** en todo: líneas de factura (precio, cantidad, país de origen, partida, descripción), cajas (medidas, pesos, número de cajas, valores de plantilla, confirmar pesos), mover, quitar y asignar a transporte. Cada acción masiva es todo o nada: si una fila falla, no se aplica ninguna y se explica cuál.
- **Estados:** Borrador → Finalizado directo; reabrir pasa a “En corrección” y pide motivo. Factura, PL y transporte avanzan por separado; “lista para transporte” se calcula (factura finalizada, todo en PL y todos los PL finalizados).
- **Transporte:** el embarque existe desde el booking (el BL/AWB se agrega después). Sus contenedores y su carga se manejan dentro del mismo embarque. Al asignar, “confirmar los que estén listos” confirma lo que tiene factura y PL finalizados y deja **tentativo** lo demás (para planificar). No se registra la salida con tentativas pendientes. Después de la salida la carga queda cerrada (ver “Embarques más estrictos”).

### Campos obligatorios

Los campos marcados con <span style="color:#b42318">*</span> son obligatorios. El sistema no deja finalizar ni registrar la salida sin ellos (se valida en el servidor, no solo en pantalla):

- **Factura comercial:** número, fecha, incoterm y, por línea, cantidad, precio unitario, país de origen, partida arancelaria y descripción comercial de la mercancía.
- **Packing list:** para cada grupo de cajas, medidas (largo, ancho, alto) y peso neto y bruto.
- **Transporte (para registrar la salida):** número de BL, AWB o carta de porte, transportista, origen y destino, número de cada unidad de carga (contenedor, guía o camión) y el sello en las unidades cuyo tipo lo exige (p. ej. contenedores FCL).

Se basan en los requisitos usuales de la factura comercial y del documento de transporte en la región (RECAUCA y DUCA). Confírmalos con tu agente aduanal antes de usar el sistema con datos reales.

### Tema claro y oscuro

La barra superior tiene tres botones: claro, oscuro e igual que el sistema (por defecto). La elección se recuerda en el navegador.

### Qué se simplificó

| Antes | Ahora |
|---|---|
| Inicio con tarjetas de conteo | Tablero por rol: indicadores, próximos pasos, flujo de mercancía, facturado por mes, envíos, contenedores y resumen por proveedor |
| Factura con 6 pestañas (Resumen y Transporte repetían datos) | Datos editables en la cabecera, pasos de avance y 4 pestañas; el transporte se ve en la de packing lists |
| “Finalizar” y “Finalizar con sus packing lists” | Un botón con la lista de lo que falta y la opción de incluir los PL |
| Crear PL, agregar pendientes y crear PL con la selección | **Empacar**: crea el PL o suma lo pendiente al PL abierto |
| Aplicar plantilla (una a la vez), caja con lo que falta y dividir | **Empacar automático**, cada fila con la suya; mover acepta cantidades parciales |
| Cambiar medidas y usar valores de plantilla por separado | Una sola ventana de medidas y pesos, con opción de copiar de una plantilla |
| Embarque → página de la unidad de carga | Contenedores como pestañas dentro del embarque, asignación en un panel lateral |
| Asignar como tentativo / asignar y confirmar | Un botón que confirma lo que está listo y deja tentativo lo demás |
- **Separación por proveedor:** el proveedor solo ve lo suyo; si pide un documento ajeno recibe 404, no 403.

### Concurrencia

- **Bloqueo de filas** (`SELECT … FOR UPDATE`) al tomar saldo de una posición o de una factura: dos personas no pueden facturar o asignar el mismo saldo. Hay una prueba que lo verifica en PostgreSQL.
- **Versión por documento:** si alguien más cambió la factura o el PL mientras lo tenías abierto, tu cambio no se aplica y se te pide recargar.
- **Idempotencia:** cada operación lleva una clave; si la red la repite, el servidor devuelve el mismo resultado sin duplicar.
- **Historial** de cada cambio con usuario, antes/después y motivo.

## Reglas configurables

Se cambian con variables de entorno, sin tocar el modelo de datos (ver `backend/app/config.py`):

| Variable | Por defecto | Qué hace |
|---|---|---|
| `POSICION_EN_VARIAS_FACTURAS` | `0` | Con `0`, una posición vive en **una sola factura activa**: si facturas 60 de 100, los 40 restantes solo se agregan a esa misma factura (o a otra, si primero la quitas de la primera). Con `1`, el saldo puede ir a otra factura mientras la primera sigue activa. |
| `FACTURA_EN_UNA_SOLA_UNIDAD` | `0` | Con `1`, todos los PL de una factura deben ir en la misma unidad de carga. |
| `PROVEEDOR_PUEDE_FINALIZAR` | `1` | Si el proveedor puede finalizar sus facturas y PL. Reabrir siempre es del equipo interno. |
| `REQUERIR_DATOS_ADUANA` | `1` | Exige país de origen y partida arancelaria por línea para finalizar. |
| `DIAS_ALERTA_BORRADOR` | `7` | A partir de cuántos días un borrador aparece como alerta (sigue reservando saldo). |

También en `config.py`: qué datos de la OC bloquean mezclar en una factura (sociedad, moneda, centro PA10/PA20), cuáles solo advierten (incoterm, país destino) y la capacidad nominal por tipo de contenedor.

Otras variables: `DATABASE_URL`, `SECRET_KEY` (cámbiala en producción), `SEED_DEMO`, `UPLOAD_DIR`, `CORS_ORIGINS`.

## Importar OCs

En *Importar OCs* (equipo interno) se sube el Excel o CSV de SAP. Hay un formato de ejemplo descargable. Primero se ve qué es nuevo, qué cambia, qué no cambia, los conflictos y los errores; nada se guarda hasta confirmar. Los conflictos (por ejemplo, bajar la cantidad por debajo de lo facturado) no se aplican y quedan como alerta en el *Inicio* del equipo interno.

Columnas obligatorias: `proveedor, oc, posicion, sku, cantidad, precio, moneda, sociedad, centro, centro_destino` (también se acepta `pais_destino`). Opcionales: `almacen, incoterm, fecha_oc, puerto, pais_origen, pais_procedencia, fecha_xf_original, fecha_xf, fecha_tienda, liberacion_comercial, liberacion_logistica, unidad, casepack`. Se aceptan algunos alias (`po`, `material`, `qty`, `uom`…). Ver `plantilla_oc.csv`.

Cada fila se valida contra los maestros: OC con formato 44XXXXXXXX, posición múltiplo de 10, centro y almacén de la misma sociedad (el almacén puede cambiar entre posiciones de la misma OC), país de destino y puerto registrados y SKU existente. Carga primero los artículos y las curvas en *Mantenimiento*.

**Reinicio de la base de datos:** en modo demo (`SEED_DEMO=1`) la base se borra y se vuelve a sembrar automáticamente cuando cambia la versión del esquema (`ESQUEMA_VERSION` en `config.py`). En producción (`SEED_DEMO=0`) nunca se borra nada.

Los códigos se guardan como texto para conservar ceros iniciales. Si Excel ya los convirtió a número al exportar, se pierden: formatea esas columnas como texto antes.

## Pruebas

```bash
cd backend
pytest                                   # SQLite
TEST_DATABASE_URL=postgresql+psycopg://usuario:clave@localhost/pruebas pytest   # PostgreSQL (incluye la de concurrencia)
```

## Estructura

```
backend/app/
  config.py          reglas configurables
  models.py          modelo de datos
  services/          toda la lógica de negocio (cantidades, facturas, packing, transporte, importación, tablero)
  routers/           endpoints REST bajo /api
backend/tests/       flujo completo y concurrencia
frontend/src/
  views/             Inicio (tablero), Órdenes, Facturas, Factura, Packing list, Plantillas, Embarques, Embarque, Seguimiento, Mantenimiento, Importar, Admin
  composables/       orden y paginación de tablas
  components/        íconos, indicadores, pasos, gráficas SVG, tabla editable, barra de acciones masivas, modales, estados
  stores/            sesión, selección para facturar, avisos
```

## Para producción, antes de salir

- Usar **Alembic** para migraciones en lugar de `create_all` y poner `SEED_DEMO=0`.
- Cambiar `SECRET_KEY`; idealmente integrar el login con el directorio de la empresa (Entra ID / SSO) para internos.
- Servir archivos adjuntos desde almacenamiento de objetos en lugar de disco local.

## Siguientes pasos sugeridos

1. **Importar el packing list desde Excel** del proveedor (cajas, rangos, pesos), con la misma vista previa que la importación de OCs.
2. **Curvas de talla:** plantillas surtidas (por ejemplo, 1-2-3-3-2-1 por caja) para empacar un estilo-color completo de una vez.
3. **PDF** de factura y packing list con el formato oficial.
4. **Integración con SAP:** OCs por interfaz en lugar de archivo y envío de la factura/PL finalizados.
5. Notificaciones por correo (factura finalizada, PL reabierto, cambios de ETA).
