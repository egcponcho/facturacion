# Grupos de producto

Un solo árbol de la empresa para agrupar lo que vende (calzado → calzado
técnico → sandalias…). Lo comparten el etiquetado y las reglas de empaque, y
es la base del catálogo (módulo `catalogo`).

Pantalla: **Configuración → Datos maestros → Grupos de producto**
(`/grupos-producto`). Las pantallas del etiquetado (Etiquetas → Familias y sus
categorías) siguen funcionando igual: editan estos mismos nodos.

## 1. El árbol

| Clase | Qué es | Cómo se asigna |
|---|---|---|
| Familia | Un grupo (con subfamilias, sin límite de niveles) | A mano, a un grupo de artículos, a un producto (estilo-color) o a un artículo |
| Categoría | Una hoja dentro de una familia (sandalias, botas…) | Sola, por condiciones sobre los datos del artículo y del producto, o a mano en el producto |

- El código es único en todo el árbol: una familia y una categoría no pueden
  tener el mismo.
- Una familia no puede quedar dentro de sí misma ni de una de sus subfamilias.
- Lo que algo usa (un artículo, una regla, una etiqueta del historial) no se
  borra: se desactiva.

**El grupo de un artículo:**
1. Su familia: la propia, si no la de su producto y si no la de su grupo de
   artículos.
2. Su categoría: la puesta a mano en su producto, si es de esa familia o de
   una superior; si no, la primera cuyas condiciones cumple, empezando por la
   familia más específica y en el orden de cada familia.

El producto guarda un solo nodo (`productos.grupo_producto_id`): su familia o,
si se le puso una categoría a mano, esa categoría (que dice también su
familia).

## 2. El motor común

`app/modulos/catalogo/familias.py` (`ruta_efectiva`) da a quien lo use la **ruta del artículo**, de
lo más específico a lo más general: su categoría, su familia y las familias de
arriba. La recorren:
- el etiquetado: artículo, producto, categoría, familias y toda la empresa;
- las reglas de empaque: una regla para un grupo vale para todo lo que tiene
  dentro y gana la del grupo más profundo.

Las condiciones se evalúan con un solo evaluador
(`app/modulos/comun/condiciones.py`) en los dos módulos.

## 3. API

| Ruta | Para qué |
|---|---|
| `GET /api/grupos-producto` | El árbol en orden, con lo que usa cada nodo |
| `GET /api/grupos-producto/campos` | Datos y operadores para las condiciones de una categoría |
| `POST /api/grupos-producto` | Crear una familia o una categoría |
| `PATCH /api/grupos-producto/{id}` | Cambiar nombre, lugar, condiciones o si está activo |
| `DELETE /api/grupos-producto/{id}` | Borrar un nodo sin uso |

Permisos:
- Ver: `catalogos.ver` o `etiquetas.familias`.
- Editar: `catalogos.editar` o `etiquetas.familias`.
- Un proveedor no ve el árbol.
