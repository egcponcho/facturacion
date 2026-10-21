# Sistema de diseño (archivo maestro)

> Es el sistema de diseño del ERP (`egcponcho/ERP`, `design-system/erp/MASTER.md`),
> generado con la skill **UI UX Pro Max** (`--design-system`, densidad 8,
> movimiento 3, variación 3: estilo «Minimalism & Swiss Style») y ajustado a azul
> marino y azul de acción. Si existe `design-system/facturacion/pages/<pantalla>.md`,
> sus reglas mandan sobre este archivo para esa pantalla. Los valores viven como tokens en
> `frontend/src/styles.css`: ningún componente usa colores sueltos.

**Estilo:** minimalista y sobrio (suizo), para herramientas de trabajo. Mucha
información por pantalla, jerarquía por tamaño y peso, color solo donde significa
algo (acción principal, estado, error).

## Color

| Rol | Claro | Oscuro | Token |
|---|---|---|---|
| Estructura (menú lateral, texto principal) | `#0F172A` | `#E2E8F0` (texto) · `#070D18` (menú) | `--tinta`, `--lateral` |
| Acción principal y lo activo | `#0369A1` | `#38BDF8` | `--acento` |
| Texto sobre la acción principal | `#FFFFFF` | `#082F49` | `--sobre-acento` |
| Fondo de la página | `#F8FAFC` | `#0B1220` | `--papel` |
| Tarjetas y paneles | `#FFFFFF` | `#121B2D` | `--superficie` |
| Texto secundario | `#334155` | `#CBD5E1` | `--tinta-2` |
| Texto tenue (siempre ≥ 4.5:1) | `#546277` | `#97A3B6` | `--tinta-3` |
| Bordes | `#E2E8F0` | `#253149` | `--linea` |
| Bien / aviso / error | `#15803D` · `#A15C07` · `#C81E1E` | `#4ADE80` · `#FBBF24` · `#F87171` | `--ok`, `--aviso`, `--error` |
| Barras de las gráficas | `#0369A1` | `#0284C7` | `--barra-dato` (validado con la skill dataviz) |

- El color nunca va solo: los estados llevan forma (círculo, cuadro, rombo) y texto.
- El tema oscuro tiene sus propios valores (no es el claro invertido) y se prueba aparte.

## Tipografía

- **Plus Jakarta Sans** (variable, servida por `@fontsource-variable/plus-jakarta-sans`, sin Google Fonts).
- Base de 14 px para escritorio (densa, para datos); los campos suben a 16 px en el
  celular para que iOS no haga zoom.
- Títulos 700–760, rótulos 600–680, texto 400–500. Números tabulares en tablas y cifras.

## Espaciado, forma y elevación

- Múltiplos de 4 px (`--e-1` … `--e-8`). Radios: 8 px controles, 12 px paneles.
- Sombras: `--sombra` (reposo), `--sombra-media` (al pasar), `--sombra-flotante` (menús, avisos).
- Movimiento corto y con sentido: 150 ms (`--rapido`) y 200 ms (`--normal`); sin
  animaciones con `prefers-reduced-motion`.

## Componentes

- **Botones:** uno solo primario por pantalla (en Productos, «Nuevo producto»; en Compras, «Nueva OC»). Alto
  de 36 px con ratón y 44 px en pantallas táctiles.
- **Campos:** rótulo visible siempre, `*` en obligatorios, ayuda debajo y el error
  junto al campo.
- **Tablas:** `TablaDatos` (la de facturacion) para todas las tablas.
- **Formularios en la página, no en ventanas:** `PanelEnLinea`, filas que se
  despliegan, celdas editables y confirmación en el mismo botón (`BotonConfirmar`).
  Las ventanas emergentes (modales) no se usan.
- **Gráficas:** barras horizontales de un solo color, con rótulo y cifra escritos;
  cada barra es un enlace a la lista filtrada.

## Navegación

- Menú lateral: **una entrada por módulo** (Inicio, Compras, Facturación,
  Logística, Productos, Etiquetas, Análisis y Configuración). Cada módulo lleva
  adentro sus apartados en una barra de pestañas, con su acción principal a la
  derecha. La lista de módulos y apartados vive en `frontend/src/nucleo/modulos.js`.
- Migas de pan en la barra superior en todas las páginas.
- Al cambiar de página, el foco pasa al contenido; en el asistente, al título del paso.

## Lo que no se hace

- Emojis como íconos (se usan los SVG de `Icono.vue`).
- Ventanas emergentes para formularios.
- Texto de menos de 4.5:1 de contraste o foco invisible.
- Gradientes decorativos, diseño «juguetón», movimientos que desplazan el contenido.

## Revisión antes de entregar

- [ ] Sin emojis como íconos; todos los íconos de `Icono.vue`.
- [ ] Todo lo que se puede pulsar muestra la mano y cambia al pasar (150–200 ms).
- [ ] Contraste ≥ 4.5:1 en claro y en oscuro; foco visible con el teclado.
- [ ] Respeta `prefers-reduced-motion`.
- [ ] Probado a 390, 768, 1024 y 1440 px; sin desplazamiento horizontal de la página.
- [ ] Nada queda tapado por la barra superior ni por la barra de acciones del asistente.
