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
2. En *Órdenes de compra*, en la OC 4500012345, pulsa **Facturar** (o ábrela y cambia “A facturar” para tomar solo una parte; se pueden juntar varias OCs). Revisa la selección y pulsa **Crear factura**.
3. En la factura, los pasos de arriba dicen qué falta. Pulsa **Empacar pendientes**: crea el packing list con todo y lo abre.
4. En *Por empacar*, pulsa **Empacar con plantillas**. Cada producto trae sugerida la plantilla que se usó antes con ese estilo; la talla XL (27) deja 2 cajas de 10 y un sobrante de 7, que va a una caja parcial con peso estimado (o se queda sin caja, si lo prefieres).
5. En *Revisión*, **Confirmar estimados** y **Finalizar packing list**. Vuelve a la factura, escribe número y fecha en la cabecera y pulsa **Finalizar**.
6. Entra como **interno@demo.com**, abre *Embarques* → EMB-0003, elige el 40HC #1 y pulsa **Asignar carga**: marca la factura y asígnala; lo que ya está finalizado se confirma en el mismo paso. Luego **Registrar salida**. El proveedor ve el tránsito desde su factura y su inicio.

## Cómo quedaron las reglas principales

**Todo se maneja por cantidades, con la misma fórmula en cada nivel:** disponible = cantidad del nivel de arriba − lo asignado en documentos activos.

| Nivel | Se asigna | Lo libera |
|---|---|---|
| Posición OC → factura | cantidad parcial o total | quitar la línea, reducir la cantidad o cancelar la factura |
| Línea de factura → packing list | cantidad parcial o total, en uno o varios PL | quitar del PL, reducir en la factura o cancelar el PL |
| Fila del PL → cajas | cajas completas, parciales o mixtas | desempacar |

- **Reducir en la factura** algo que ya está en PL: el sistema avisa qué PL tienen esa cantidad y ofrece liberar automáticamente lo que no está en cajas. Lo empacado nunca se toca solo.
- **Quitar líneas** con cantidades en PL: muestra el impacto (PL y cajas) y pide confirmar antes de quitar en cascada.
- **Empacar con plantillas:** un solo paso para todo el PL (o las filas elegidas), cada fila con su propia plantilla. La sugerencia sale del historial: la última plantilla usada en esa fila o, si no hay, con la que el proveedor empacó el mismo estilo. El sobrante que no llena una caja va a una caja parcial o se deja sin caja para armar cajas mixtas.
- **Mover a otro PL** toma una cantidad de lo que no está en cajas (ya no hace falta “dividir” antes). Para llevar lo empacado se usa **Mover cajas**, que se lleva el contenido y recalcula la numeración.
- **Plantillas:** solo llenan datos. Cada caja guarda sus propios valores; editar la plantilla no cambia cajas existentes. No es obligatorio usarlas. Cualquier caja se puede guardar como plantilla nueva.
- **Cajas parciales:** medidas de la plantilla, peso neto proporcional y bruto = neto + tara. Quedan marcadas como “peso estimado” y el PL no se finaliza hasta confirmarlas.
- **Cambios masivos** en todo: líneas de factura (precio, cantidad, país de origen, partida, descripción), cajas (medidas, pesos, número de cajas, valores de plantilla, confirmar pesos), mover, quitar y asignar a transporte. Cada acción masiva es todo o nada: si una fila falla, no se aplica ninguna y se explica cuál.
- **Estados:** Borrador → Finalizado directo; reabrir pasa a “En corrección” y pide motivo. Factura, PL y transporte avanzan por separado; “lista para transporte” se calcula (factura finalizada, todo en PL y todos los PL finalizados).
- **Transporte:** el embarque existe desde el booking (el BL/AWB se agrega después). Sus contenedores y su carga se manejan dentro del mismo embarque. Al asignar, “confirmar los que estén listos” confirma lo que tiene factura y PL finalizados y deja **tentativo** lo demás (para planificar). No se registra la salida con tentativas pendientes. Después de la salida, mover o quitar carga pide motivo.

### Qué se simplificó

| Antes | Ahora |
|---|---|
| Inicio con tarjetas de conteo | Tablero por rol: indicadores, próximos pasos, flujo de mercancía, facturado por mes, envíos, contenedores y resumen por proveedor |
| Factura con 6 pestañas (Resumen y Transporte repetían datos) | Datos editables en la cabecera, pasos de avance y 4 pestañas; el transporte se ve en la de packing lists |
| “Finalizar” y “Finalizar con sus packing lists” | Un botón con la lista de lo que falta y la opción de incluir los PL |
| Crear PL, agregar pendientes y crear PL con la selección | **Empacar**: crea el PL o suma lo pendiente al PL abierto |
| Aplicar plantilla (una a la vez), caja con lo que falta y dividir | **Empacar con plantillas**, cada fila con la suya; mover acepta cantidades parciales |
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

Columnas obligatorias: `proveedor, oc, posicion, sociedad, moneda, codigo_sap, cantidad, unidad, precio`. Opcionales: `centro, pais_destino, incoterm, fecha_oc, upc, estilo, color, talla, descripcion, fecha_entrega, pais_origen, partida_arancelaria, liberada`. Se aceptan algunos alias (`po`, `material`, `qty`, `uom`, `hs_code`…).

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
  views/             Inicio (tablero), Órdenes, Facturas, Factura, Packing list, Plantillas, Embarques, Embarque, Importar, Admin
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
