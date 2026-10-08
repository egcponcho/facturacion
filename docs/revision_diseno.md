# Revisión de diseño (UX/UI) — segunda revisión

Recorrido completo de las pantallas con tres perfiles (administrador, equipo
interno y proveedor) a 1440 px y en celular. Este documento lista lo que se
encontró y qué se hizo con cada punto. Las propuestas anteriores siguen en
`propuesta_revision_integral.md`.

## 1. Hallazgos

### 1.1 Tablas saturadas

| Pantalla | Qué pasa | Efecto |
|---|---|---|
| Órdenes | 11 columnas; la tabla se sale de la pantalla en 1440 px («Valor de la OC» y «Facturado» quedan cortadas). Cada fila mide ~100 px porque mezcla número, fecha, líneas, proveedor y dos insignias de liberación apiladas | Hay que desplazarse en las dos direcciones para leer 8 OC |
| Seguimiento | 10 columnas + una gráfica de 300 px y 5 indicadores antes de la tabla; «Est. en tienda» se corta | La tabla empieza a media pantalla |
| Factura → Líneas | 13 columnas; «Precio» y «Total» quedan fuera | El dato más importante para el proveedor (importe) no se ve sin desplazar |
| Lista de empaque → Cajas | 12 columnas (largo, ancho, alto, tara…) siempre visibles | Se cortan; son datos de captura, no de consulta |
| Usuarios | Filas de ~160 px con espacio vacío | Error de estilo: la celda ocupa toda la altura del avatar + márgenes heredados |
| Órdenes en celular | Cada OC se vuelve una tarjeta con las 11 columnas (~540 px por OC; 8 OC = 4 900 px) | En celular solo se ve una OC por pantalla |
| Administración | Proveedores, roles, flujo de clasificación y usuarios en una sola página de 2 500 px | Difícil encontrar lo que se busca |

### 1.2 Información que no todos deberían ver

Hoy **todos los usuarios con acceso a una pantalla ven todas sus columnas**.
Ejemplos con el proveedor:

- Códigos internos de la empresa: sociedad, centro, almacén, centro de destino.
- Fechas internas de la empresa: fecha en tienda, estimado en tienda, días de holgura.
- Liberaciones comercial y logística con los códigos del ERP («300/301/304», «C/P»).
- Tasas arancelarias por país de destino (15 %…), base legal y notas del clasificador.
- Contactos internos (nombre, correo y teléfono del centro receptor).

No existe forma de decidir, por rol, qué datos se muestran. Además ocultarlos
solo en pantalla no basta: el servidor los sigue enviando y salen en Excel/PDF.

### 1.3 Filtros

- Seguimiento: 4 filtros visibles + «Más filtros» + 4 pestañas + 7 estados
  clicables de la gráfica: tres maneras distintas de filtrar lo mismo.
- Datos maestros: 5 filtros en dos filas, dos de ellos sin traducir («Brand: todos»,
  «Item group: todos», «Supplier: todos», «Unit: todos»).
- Productos: abre en la pestaña «Por revisar» aunque esté vacía (0); el usuario
  ve «Nada pendiente aquí» y cree que no hay productos.

### 1.4 Textos y consistencia

- «Company» se tradujo «Sociedad», igual que «Legal entity»: el menú muestra
  «Sociedad» y «Sociedades», dos cosas distintas con casi el mismo nombre.
- Mezcla de idiomas: «packing lists» en las reglas, «Brand/Item group» en los
  filtros, «Ship TNF-2026-0915» en siguientes pasos, «Supplier (view only)».
- Los códigos SAP aparecen en pantalla: «comercial C y logística 300/301»,
  «Sin liberación logística (304)», «comercial P».
- Empresa: «País» y «Zona horaria» son texto libre (se puede escribir cualquier cosa).

### 1.5 Multiempresa visible

Menú con «Sociedad» (empresa) y «Sociedades» (plataforma), aviso de «trabajando
en otra empresa», selector de empresas. Se decidió **una empresa por instalación**.

## 2. Qué se hace

| # | Cambio | Dónde |
|---|---|---|
| 1 | **Datos visibles por rol**: cada rol tiene una lista de grupos de datos ocultos (precios e importes, códigos internos, fechas internas, liberaciones, aranceles y tasas, contactos internos, auditoría). El servidor los quita de cada respuesta y de cada Excel/PDF; la pantalla oculta sus columnas y filtros. Se configura en *Usuarios y accesos → Rol* | Backend + Admin |
| 2 | **Columnas por usuario**: botón «Columnas» en las tablas principales para mostrar u ocultar columnas (dentro de lo que su rol permite), guardado en su perfil. Cada tabla trae una vista inicial corta con lo esencial | Órdenes, Seguimiento, Facturas, Productos, Embarques, Líneas de factura, Cajas del PL |
| 3 | **Filas compactas**: Órdenes y Seguimiento en una línea por OC (insignia de liberación única con el detalle en el tooltip); fechas con su indicador a la derecha | Órdenes, Seguimiento |
| 4 | **Gráfica de Seguimiento plegable** y cerrada por defecto; los estados quedan como pestañas | Seguimiento |
| 5 | **Administración en pestañas**: Usuarios · Roles · Proveedores · Flujo de clasificación; corrige la altura de las filas | Admin |
| 6 | **Productos** abre en la primera pestaña con datos | Productos |
| 7 | **Textos**: «Empresa» para la organización, «Sociedad» para la entidad legal; filtros traducidos; sin códigos SAP en pantalla (estados con nombre) | Todo |
| 8 | **Empresa**: país y zona horaria con selector | Empresa |
| 9 | **Una empresa**: se quita la plataforma multiempresa | Todo |
