# Catálogo de clasificación según las Notas Explicativas

Fuente: *Notas Explicativas de la Tarifa arancelaria* (DOF, 6 de marzo de 2006),
que publica en español las Notas Explicativas del Sistema Armonizado de la OMA
(el PDF de origen no se guarda en el repositorio: su contenido ya está en `backend/app/data/motor`). Son la interpretación oficial
de las secciones, capítulos, partidas y subpartidas; el texto de cada código
sale siempre del árbol oficial vigente (SAC, VII Enmienda), no de este archivo.

El catálogo del motor (familias, categorías, preguntas y reglas) se rehízo
desde cero con estas notas para cinco familias: **calzado, ropa, accesorios,
químicos y materias primas**. Todo es configuración editable en *Familias de
producto*; la semilla vive en `backend/app/data/motor/familias/` (un archivo
por familia más `comun.json`).

## Criterios generales

- **Categoría = lo que el proveedor reconoce** (tenis, chaqueta, mochila,
  adhesivo…). Solo decide qué preguntar; el código lo deciden las reglas.
- **Preguntas = los datos que la nota usa para separar partidas y subpartidas**
  (materia de la suela, punto o tejido plano, para hombre o mujer, fibra que
  predomina en peso…). Una pregunta solo se hace si alguna regla la necesita.
- **Reglas = el árbol de la nota**: primero la partida, después la subpartida.
  Cada regla dice en su efecto qué nota la respalda.
- **Árbol vigente manda**: las notas son de 2006; cuando una subpartida ya no
  existe en el SAC vigente, la regla apunta a la que la reemplazó (por ejemplo
  6401.91 → 6401.99, 6403.30 → 6403.91/99, 6406.91/99 → 6406.90).
- **Composición**: la fibra que predomina en peso (Nota 2 de la Sección XI) y
  la materia de mayor superficie del corte y de contacto de la suela (Nota 4
  del capítulo 64) se calculan de la composición que escribe el proveedor.
- Las **Notas aclaratorias nacionales** de México (tallas para hombres,
  jóvenes, niños; fracciones a 8 dígitos) no se usan: el SAC tiene sus
  propias aperturas nacionales.

## Calzado (capítulo 64)

Fuera del capítulo (Nota 1): calzado desechable sin suela aplicada (por su
materia), patucos textiles sin suela aplicada (61/62), calzado ortopédico
(90.21), calzado con patines fijos o de juguete (95).

| Dato | De la nota | Opciones |
|---|---|---|
| Materia del corte | Nota 4 a): la de mayor superficie exterior, sin accesorios ni refuerzos; la lengüeta cuenta | cuero natural · materia textil · caucho o plástico (incluye cuero sintético y textil con capa visible, Nota 3 a) · otra |
| Materia de la suela | Nota 4 b): la de mayor superficie en contacto con el suelo | caucho o plástico · cuero natural o regenerado · otra (madera, corcho, textil, yute) |
| Impermeable moldeado | 64.01: corte y suela de caucho o plástico no unidos por costura, remaches, clavos, tornillos ni espigas | sí / no |
| Deportivo | Nota de subpartida 1: con clavos, tacos, fijaciones o barras; o para esquí, snowboard, lucha, boxeo, ciclismo | esquí o snowboard · otro deporte con tacos/fijaciones · no |
| Tipo tenis, básquetbol, gimnasia, entrenamiento | 6404.11 | sí / no |
| Cubre el tobillo / la rodilla | 6401.92, 6402.91, 6403.51/91 | no cubre · tobillo · rodilla |
| Puntera metálica de protección | 6401.10, 6403.40 | sí / no |
| Tiras fijas a la suela por tetones | 6402.20 | sí / no |
| Suela de cuero y tiras de cuero sobre el empeine y alrededor del dedo gordo | 6403.20 | sí / no |

Árbol: corte y suela de caucho o plástico → 64.01 (impermeable moldeado) o
64.02; corte de cuero natural con suela de caucho, plástico o cuero → 64.03;
corte textil con esas suelas → 64.04; lo demás → 64.05 (por la materia del
corte). Partes, plantillas amovibles y polainas → 64.06.

## Ropa (capítulos 61 y 62; 39.26, 40.15, 42.03 y 43.03 por la materia)

- **Punto o tejido plano** decide el capítulo (61 o 62); el 62.12 (sostenes,
  fajas, tirantes) aplica aunque sea de punto.
- **Para hombre o mujer** (Nota 9 del 61 y 8 del 62): cierre izquierda sobre
  derecha = hombre; derecha sobre izquierda = mujer; lo que no se identifica va
  con mujer. Las camisetas (61.09), suéteres (61.10), chándales, trajes de baño
  de punto y demás prendas (61.14) no distinguen sexo.
- **Bebé** (Nota 6 del 61 y 4 del 62): estatura hasta 86 cm; manda sobre las
  demás partidas (61.11, 62.09).
- **Tela recubierta** de las partidas 59.03, 59.06 o 59.07 (o fieltro y tela
  sin tejer, 56.02/56.03 en el 62): manda sobre las demás partidas (61.13,
  62.10), excepto bebé. Una prenda acolchada de 58.11 no cuenta: se clasifica
  por la tela exterior (nota de subpartida).
- **Fibra que predomina en peso** del tejido exterior (Nota 2 de la Sección
  XI): lana o pelo fino, algodón, sintética, artificial, seda, lino u otra.
- Prenda de cuero → 42.03; de plástico → 39.26; de caucho → 40.15; con
  peletería que no sea adorno → 43.03/43.04.

Categorías y su partida: abrigo, chaqueta o chaleco acolchado (61.01/61.02,
62.01/62.02); saco tipo sastre (61.03/61.04, 62.03/62.04); traje y conjunto
(mismas partidas); pantalón, short y pantalón con peto; falda; vestido;
camisa o blusa (61.05/61.06, 62.05/62.06; sin bolsillos bajo la cintura ni
ajuste en el bajo); camiseta y tank top (61.09; sin ajuste en el bajo);
suéter, sudadera, cárdigan o chaleco (61.10; el de tejido plano va como
«demás prendas» 62.11); ropa interior; ropa de dormir y batas; brasier, faja
y tirantes (62.12); chándal, ropa de esquí y traje de baño (61.12, 62.11);
overol, bata y demás prendas (61.14, 62.11); calcetines, medias y pantimedias
(61.15).

## Accesorios

| Categoría | Partidas | Dato decisivo |
|---|---|---|
| Maleta, maletín, portafolios | 42.02.1x | superficie exterior: cuero · plástico o textil · otra |
| Bolso de mano | 42.02.2x | superficie exterior |
| Billetera, monedero, estuche de bolsillo | 42.02.3x | superficie exterior |
| Mochila, bolso de viaje o deporte, lonchera, estuche | 42.02.9x | superficie exterior |
| Cinturón | 42.03.30, 61.17.80, 62.17.10, 39.26.20 | materia |
| Guantes | 42.03.21/29, 61.16, 62.16, 39.26.20, 40.15.1x | materia, punto, deporte, recubiertos |
| Bufanda, chal, pañuelo de cuello | 61.17.10, 62.14, 62.13 (≤60 cm) | punto, fibra, tamaño |
| Corbata | 61.17.20, 62.15 | punto, fibra |
| Gorra, sombrero, gorro | 65.04–65.06 | trenzado, de punto o tela en pieza, casco de protección, caucho o plástico |
| Paraguas y sombrillas | 66.01 | de jardín, telescópico |
| Bisutería | 71.17 | metal común (gemelos u otra) u otra materia |
| Reloj de pulsera | 91.02 | pantalla y mecanismo |
| Correa de reloj | 91.13 | materia |
| Lentes de sol | 90.04.10 | — |
| Accesorios para el cabello | 96.15, 61.17.80, 62.17.10 | peines o pasadores; diadema textil |

## Químicos (capítulos 28, 29, 32, 34, 35, 38; 27.10 y 33 cuando aplica)

- **¿Es de constitución química definida y se presenta aislado?** (Nota 1 de
  los capítulos 28 y 29) → 28 si es inorgánico, 29 si es orgánico. Las
  disoluciones acuosas y las que solo se hacen por seguridad o transporte no
  cambian su clasificación.
- **Mezclas y preparaciones** van por su función: colorantes y pigmentos
  (32.04–32.06), pinturas y barnices (32.08 si el polímero está en disolvente
  orgánico; 32.09 en medio acuoso; 32.10 los demás), tintas (32.15), jabón
  (34.01), tensoactivos y detergentes (34.02, con su definición de la Nota 3),
  lubricantes (34.03; con 70 % o más de aceite de petróleo, 27.10), ceras
  (34.04), betunes y cremas para calzado y cuero (34.05.10), colas y adhesivos
  (35.06: al por menor ≤1 kg, a base de polímeros o caucho, demás), aprestos
  y acabados para textil o cuero (38.09), plastificantes y aceleradores para
  caucho o plástico (38.12), disolventes y diluyentes compuestos (38.14),
  reactivos de laboratorio (38.22) y preparaciones químicas n.e.p. (38.24).
- El nombre químico, el CAS y la función alimentan la búsqueda en el texto
  oficial para elegir la subpartida dentro de la partida.

## Materias primas (Sección XI, capítulos 39, 40, 41, 48; trims de 83 y 96)

- **Textiles**: fibras (50–55), hilados (y si son para la venta al por menor o
  hilo de coser, Notas 4 y 5 de la Sección XI), tejidos planos (por fibra y
  peso), tejidos de punto (60), fieltro y tela sin tejer (56.02, 56.03), telas
  recubiertas o laminadas (59.03 plástico, 59.06 caucho, 59.07 otras),
  cintas, etiquetas, encajes y bordados (58).
- **Plástico** (39): formas primarias por polímero (39.01–39.14), placas y
  láminas (39.20 sin reforzar ni celular, 39.21 celular o reforzada, 39.19
  autoadhesiva), según la Nota 10.
- **Caucho** (40): natural (40.01), sintético (40.02), mezclas sin vulcanizar
  (40.05), placas y perfiles vulcanizados (40.08, celular o no).
- **Cuero** (41): bovino (41.04 curtido, 41.07 preparado), otros animales
  (41.05, 41.06, 41.12–41.13), gamuza, charol y metalizado (41.14), regenerado
  (41.15). El cuero sintético va como plástico (39.21) o tela recubierta
  (59.03) según su soporte.
- **Papel y cartón** (48) y **avíos**: cierres (96.07), botones (96.06),
  hebillas, ojetes y broches (83.08), velcro y elásticos (58.06), etiquetas
  (58.07, 48.21).
