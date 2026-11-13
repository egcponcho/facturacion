# Sistema de diseño (archivo maestro)

> Tablero profesional para la operación logística: compras, facturación,
> empaque, embarques y recepción. Limpio y ordenado, sin imitar ningún sistema
> operativo (nada de barras de pestañas inferiores ni widgets de teléfono). Si
> existe `design-system/facturacion/pages/<pantalla>.md`, sus reglas mandan sobre
> este archivo para esa pantalla. Los valores viven como tokens en
> `frontend/src/estilos/tokens.css`: ningún componente usa colores sueltos.

**Estilo:** sobrio y denso, para trabajar muchas horas con datos. Jerarquía por
tamaño y peso, no por mayúsculas ni por color. El color se reserva para lo que
significa algo: la acción principal, lo activo, el estado y el error.

## Hojas de estilo

`frontend/src/estilos/index.css` las importa en este orden; cada archivo trata un tema:

| Archivo | Qué tiene |
|---|---|
| `tokens.css` | Colores (claro, oscuro y paletas de la empresa), espacios, radios y tipografía |
| `base.css` | Elementos HTML, foco visible y movimiento reducido |
| `marco.css` | Barra lateral, barra superior y el cajón del celular |
| `controles.css` | Encabezados de página, botones, campos, paneles, pestañas y pasos |
| `tablas.css` | Tablas de datos, celdas editables y estados |
| `componentes.css` | Avances, barra de selección, panel lateral, indicadores del tablero y gráficas |
| `pantallas.css` | Lo propio de una pantalla: listas de empaque, transporte, ingreso |
| `utilidades.css` | Piezas chicas: cargas de archivos, filtros activos, control segmentado |
| `adaptable.css` | Ajustes para tablet y celular |

## Color

Paleta de fábrica «Pizarra y petróleo» (diseño v3, noviembre de 2026): neutros fríos
tipo pizarra, un solo acento azul petróleo y estados apagados. En el tema claro la barra
lateral también es clara; en el oscuro es grafito. La empresa puede elegir otra en
Configuración → Empresa → Marca («Operación», la anterior con barra grafito y acento
azul; esmeralda, terracota o marino); las paletas solo cambian el acento y la barra lateral.

| Rol | Claro | Oscuro | Token |
|---|---|---|---|
| Barra lateral | `#FBFBFC` | `#12161C` | `--lateral` |
| Acción principal y lo activo | `#0F5F6E` | `#3FA6B3` | `--acento` |
| Texto sobre la acción principal | `#FFFFFF` | `#0B1418` | `--sobre-acento` |
| Fondo tenue de acento (lo activo, acciones de fila) | `#E5F0F1` | `#12303A` | `--acento-claro` |
| Texto principal | `#1D2433` | `#E6E9EE` | `--tinta` |
| Texto secundario | `#4B5565` | `#A7AFBC` | `--tinta-2` |
| Texto tenue (≥ 4.5:1) | `#6B7484` | `#8B94A3` | `--tinta-3` |
| Fondo de la página | `#F6F7F9` | `#0E1116` | `--papel` |
| Tarjetas y paneles | `#FFFFFF` | `#151A21` | `--superficie` |
| Bordes | `#E4E7EC` | `#262D38` | `--linea` |
| Bien / aviso / error / información | `#2E7556` · `#8F5F05` · `#A33A36` · `#3D5A80` | `#4FAE84` · `#D4A64A` · `#E07A72` · `#8AA8D3` | `--ok`, `--aviso`, `--error`, `--info` |
| Series de gráficos | petróleo, azul acero, salvia, arena, gris | versiones claras | `--etapa-1` … `--etapa-7` |

## Navegación

El menú lateral sigue la cadena de abastecimiento y se ordena en grupos
(`nucleo/modulos.js`): **Operación** (Compras, Despacho, Transporte, Inventario),
**Control** (Seguimiento, Análisis), **Datos** (Productos, Terceros, Empaque),
**Módulos opcionales** (Etiquetas, Aduana) y **Sistema** (Configuración). Un módulo
apagado o sin permiso desaparece sin dejar su grupo vacío. Dentro de cada módulo, la
barra del módulo (franja blanca bajo la barra superior) lleva los apartados en
pestañas y la acción principal a la derecha.

- El color nunca va solo: los estados llevan forma (círculo, cuadro, rombo) y texto.
- El tema oscuro tiene sus propios valores (no es el claro invertido) y se prueba aparte.

## Tipografía

- **Inter** (variable, servida por `@fontsource-variable/inter`, sin Google Fonts),
  con las variantes `cv11` y `ss01` para que cifras y códigos se lean sin dudas.
- Base de 14 px para escritorio (densa, para datos); los campos suben a 16 px en el
  celular para que el navegador no haga zoom.
- Títulos 700, rótulos 600, texto 400–500. Números tabulares en tablas y cifras.
- Sin mayúsculas forzadas: rótulos, encabezados de tabla y pasos van en tipo
  oración. La clase `.mayus` queda solo para códigos que de por sí van en mayúsculas.

## Espaciado, forma y elevación

- Múltiplos de 4 px (`--e-1` … `--e-8`). Radios: 8 px controles, 10 px paneles.
- Sombras: `--sombra` (reposo), `--sombra-media` (al pasar), `--sombra-flotante` (menús, avisos).
- Movimiento corto y con sentido: 150 ms (`--rapido`) y 200 ms (`--normal`); sin
  animaciones con `prefers-reduced-motion`.

## Componentes

- **Botones:** uno solo primario por pantalla (en Productos, «Nuevo producto»; en Compras, «Nueva OC»,
  que está en la barra del módulo y no se repite en la pantalla). La acción de cada fila de una tabla
  usa `.btn-tinte` (fondo tenue de acento), nunca `.btn-primario`. Alto de 36 px con ratón y 44 px en
  pantallas táctiles.
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
- Imitar un sistema operativo (barras de pestañas de teléfono, interruptores y
  listas copiados de iOS o Android).
- Mayúsculas para dar jerarquía.

## Revisión antes de entregar

- [ ] Sin emojis como íconos; todos los íconos de `Icono.vue`.
- [ ] Todo lo que se puede pulsar muestra la mano y cambia al pasar (150–200 ms).
- [ ] Contraste ≥ 4.5:1 en claro y en oscuro; foco visible con el teclado.
- [ ] Respeta `prefers-reduced-motion`.
- [ ] Probado a 390, 768, 1024 y 1440 px; sin desplazamiento horizontal de la página.
- [ ] Nada queda tapado por la barra superior ni por la barra de acciones del asistente.
