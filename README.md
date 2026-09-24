# Workspace de proveedor: OC → factura → packing list → cajas → transporte

Sistema para que cada proveedor (y el equipo interno) arme sus facturas desde las OCs, las distribuya en packing lists y cajas, y el equipo de importaciones las asigne a unidades de carga y dé seguimiento al embarque.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL (SQLite para desarrollo rápido).
- **Frontend:** Vue 3 + Vite, sin librerías de componentes.
- **Probado:** 16 pruebas del flujo completo en PostgreSQL (15 en SQLite) y un recorrido en navegador real de punta a punta.

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

### Usuarios de prueba (contraseña `demo123`)

| Correo | Rol |
|---|---|
| tnf@demo.com | Proveedor The North Face |
| vans@demo.com | Proveedor Vans |
| interno@demo.com | Equipo de importaciones |
| admin@demo.com | Administrador |

## Recorrido de 5 minutos

1. Entra como **tnf@demo.com** y ve a *Órdenes de compra*. En la OC 4500012345 usa **Agregar completa**, o ábrela y cambia “A facturar” para tomar solo una parte. Se pueden juntar varias OCs.
2. En el panel *Selección para facturar* pulsa **Crear factura**. Cambia un precio: te pide motivo.
3. En *Packing lists* pulsa **Crear packing list con lo pendiente**.
4. Selecciona todas las filas y **Aplicar plantilla** con “Caja chaqueta 10 un”. La talla XL tiene 27: la vista previa muestra 2 cajas de 10 y un sobrante de 7, y te pregunta si creas una caja parcial (con sus propios valores y peso estimado) o lo dejas sin caja.
5. En *Cajas* confirma los pesos estimados y **Finaliza** el PL. Vuelve a la factura, completa número y fecha en *Resumen* y finalízala.
6. Entra como **interno@demo.com**, ve a *Transporte*, abre EMB-0001, el 40HC #1, y asigna la factura completa (o PL sueltos). Registra la salida en *Seguimiento*. El proveedor ve ese estado desde su factura.

## Cómo quedaron las reglas principales

**Todo se maneja por cantidades, con la misma fórmula en cada nivel:** disponible = cantidad del nivel de arriba − lo asignado en documentos activos.

| Nivel | Se asigna | Lo libera |
|---|---|---|
| Posición OC → factura | cantidad parcial o total | quitar la línea, reducir la cantidad o cancelar la factura |
| Línea de factura → packing list | cantidad parcial o total, en uno o varios PL | quitar del PL, reducir en la factura o cancelar el PL |
| Fila del PL → cajas | cajas completas, parciales o mixtas | desempacar |

- **Reducir en la factura** algo que ya está en PL: el sistema avisa qué PL tienen esa cantidad y ofrece liberar automáticamente lo que no está en cajas. Lo empacado nunca se toca solo.
- **Quitar líneas** con cantidades en PL: muestra el impacto (PL y cajas) y pide confirmar antes de quitar en cascada.
- **Dividir** una fila solo toma lo que no está en cajas. Para mover lo empacado se usa **Mover cajas**, que se lleva el contenido y recalcula la numeración.
- **Plantillas:** solo llenan datos. Cada caja guarda sus propios valores; editar la plantilla no cambia cajas existentes. No es obligatorio usarlas. Cualquier caja se puede guardar como plantilla nueva.
- **Cajas parciales:** medidas de la plantilla, peso neto proporcional y bruto = neto + tara. Quedan marcadas como “peso estimado” y el PL no se finaliza hasta confirmarlas.
- **Cambios masivos** en todo: líneas de factura (precio, cantidad, país de origen, partida, descripción), cajas (medidas, pesos, número de cajas, valores de plantilla, confirmar pesos), mover, quitar y asignar a transporte. Cada acción masiva es todo o nada: si una fila falla, no se aplica ninguna y se explica cuál.
- **Estados:** Borrador → Finalizado directo; reabrir pasa a “En corrección” y pide motivo. Factura, PL y transporte avanzan por separado; “lista para transporte” se calcula (factura finalizada, todo en PL y todos los PL finalizados).
- **Transporte:** el embarque existe desde el booking (el BL/AWB se agrega después). Las asignaciones pueden ser **tentativas** (para planificar) o **confirmadas** (solo con factura y PL finalizados). No se registra la salida con tentativas pendientes. Después de la salida, mover o quitar carga pide motivo.
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

En *Importar OCs* (equipo interno) se sube el Excel o CSV de SAP. Hay un formato de ejemplo descargable. Primero se ve qué es nuevo, qué cambia, qué no cambia, los conflictos y los errores; nada se guarda hasta confirmar. Los conflictos (por ejemplo, bajar la cantidad por debajo de lo facturado) no se aplican y quedan como alerta en *Pendientes*.

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
  services/          toda la lógica de negocio (cantidades, facturas, packing, transporte, importación)
  routers/           endpoints REST bajo /api
backend/tests/       flujo completo y concurrencia
frontend/src/
  views/             Órdenes, Facturas, Factura, Packing list, Plantillas, Transporte, Unidad, Importar, Admin
  components/        tabla editable, barra de acciones masivas, modales, estados
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
