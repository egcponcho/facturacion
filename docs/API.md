# API

La interfaz web usa la misma API que cualquier otro cliente: todo lo que se
ve en pantalla sale de `/api/...`. Este documento explica las convenciones
comunes; el detalle de cada ruta está en la documentación interactiva.

## Documentación interactiva

| Ruta | Qué es |
|---|---|
| `/docs` | Swagger UI: cada ruta con sus parámetros y respuestas, agrupadas por módulo. |
| `/redoc` | La misma documentación en formato de lectura. |
| `/openapi.json` | El esquema OpenAPI 3, para generar clientes. |

Se publica en la demostración (`SEED_DEMO=1`) o con `API_DOCS=1`. En
producción viene apagada: publicar el mapa de rutas no expone datos (cada
ruta sigue pidiendo sesión y permisos), pero tampoco hace falta para operar.

Cada ruta tiene una etiqueta de su módulo (Órdenes de compra, Facturas,
Listas de empaque, Transporte, Productos, Datos maestros, Reportes…) y un
resumen que sale de la primera línea de su docstring.
`tests/test_api_docs.py` falla si una ruta nueva queda sin etiqueta o sin
resumen.

## Sesión

1. `POST /api/auth/login` con `{"email", "password"}`. Con la verificación en
   dos pasos encendida responde `{"desafio": …}` y envía un código por SMS al
   celular registrado (en la demostración el código viene en la respuesta como
   `codigo_demo`).
2. `POST /api/auth/verificar` con `{"desafio", "codigo"}`. Deja la sesión en
   la cookie `sesion` (`HttpOnly`, `SameSite=Strict` y `Secure` salvo
   `COOKIE_SEGURA=0`) y responde el usuario.
3. `POST /api/auth/logout` cierra la sesión.

También se acepta `Authorization: Bearer <token de sesión>`. Hoy no hay
tokens de integración de larga vida para un sistema externo (ERP): la
integración se hace con un usuario y su sesión, o importando archivos.

Con contraseña temporal, solo responden `/api/auth/*` y `/api/perfil`
(`403 clave_temporal`) hasta que se cambie.

Los intentos de ingreso se limitan por red: 20 ingresos o verificaciones y
10 reenvíos de código cada 5 minutos (`429 limite`).

## Encabezados

| Encabezado | Cuándo | Para qué |
|---|---|---|
| `X-Requested-With: fetch` | Toda petición que cambia datos (POST, PUT, PATCH, DELETE) con la sesión en la cookie | Protección CSRF: otro sitio no puede enviarlo. Sin él, `403 csrf`. |
| `Idempotency-Key: <texto único>` | Las operaciones que crean o confirman (124 rutas lo aceptan) | Si la misma petición se repite con la misma clave (por un corte de red, un doble clic), se devuelve el resultado guardado sin repetir el efecto. |
| `Content-Type: application/json` | Cuerpos JSON | Las subidas de archivo van como `multipart/form-data`. |

## Errores

Toda respuesta de error tiene la misma forma:

```json
{"mensaje": "Check the data you sent.", "codigo": "datos_invalidos", "detalle": [{"campo": "lineas.0.cantidad", "mensaje": "…"}]}
```

- `codigo` es estable y es lo que un cliente debe revisar.
- `mensaje` viene en inglés, el idioma base del sistema. La interfaz lo
  traduce con su diccionario (`frontend/src/i18n`).
- `detalle` trae datos extra cuando los hay (campos con error, faltantes).

| Estado | Significa |
|---|---|
| 400 | La operación no tiene sentido con estos datos. |
| 401 `no_autenticado` | Falta la sesión o venció. |
| 403 | Sin permiso para la ruta o para el registro (por ejemplo, de otro proveedor), o `csrf`. |
| 404 `no_encontrado` | No existe o pertenece a otra organización (no se distingue a propósito). |
| 409 | Choca con el estado del documento (por ejemplo, editar una factura finalizada) o con otro registro (`integridad`: un número repetido). |
| 413 `muy_grande` | El archivo supera `MAX_SUBIDA_MB` (25 MB por defecto). |
| 422 `datos_invalidos` | Faltan datos o tienen un formato inválido; `detalle` dice cuáles. |
| 429 `limite` | Demasiados intentos de ingreso. |

## Listas, orden y filtros

Las listas que crecen se paginan en el servidor:

- `page` (desde 1) y `size` (25 por defecto; el máximo lo fija cada ruta,
  normalmente 200).
- `orden=<campo>:asc` u `orden=<campo>:desc`.
- Los filtros van como parámetros de la ruta (`estado`, `proveedor_id`, `q`
  para buscar texto…).
- La respuesta tiene la forma `{"items": [...], "total": 120, "page": 1, "size": 25}`.

Los selectores con listas grandes (proveedores, artículos, puertos) buscan en
el servidor con `q` y devuelven pocas opciones.

## Lo que cada usuario ve

- **Organización:** cada usuario pertenece a una organización y solo ve sus
  datos. El filtro está en la capa de datos y, en PostgreSQL, también en la
  base (seguridad por fila).
- **Alcance:** un usuario de proveedor ve solo lo de su proveedor; un usuario
  interno puede tener su alcance limitado a algunos proveedores, sociedades o
  transportistas.
- **Datos visibles por rol:** los campos que el rol no ve (precios, códigos
  internos…) se quitan de las respuestas de las pantallas de trabajo antes de
  enviarlas. Los documentos oficiales (factura comercial, lista de empaque)
  salen completos.

## Documentos y exportaciones

- PDF y Excel: `formato=pdf` o `formato=xlsx` en las rutas que exportan; los
  reportes del generador también aceptan `csv`.
- Idioma del documento: `idioma=es` o `idioma=en`; sin él, el idioma de
  documentos del perfil (o el de la pantalla).
- Las celdas de texto que empiezan con `=`, `+`, `-` o `@` salen como texto
  (no como fórmula).

## Cambios de la API

La API no tiene versión en la ruta. Las rutas se agregan sin romper las
existentes. Un cambio que rompe se anuncia en el mensaje del commit y en este
documento.
