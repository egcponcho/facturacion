"""El catálogo (familias, atributos, productos y artículos) es de un solo
módulo: los demás lo leen por su servicio (`app/modulos/catalogo/servicio.py`)
y nunca importan sus modelos ni sus servicios internos. Así el catálogo cambia
por dentro sin dejar partes mal integradas."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# Modelos que son del catálogo
MODELOS_CATALOGO = {
    "Articulo", "ArticuloAtributo", "ArticuloCodigo", "ArticuloComponente", "ArticuloVersion", "Atributo",
    "EscalaValores", "GrupoCategoria", "GrupoFamilia", "GrupoProducto", "Producto", "ProductoAtributo",
    "atributo_familias",
}
# Módulos internos del catálogo (lo de afuera usa catalogo.servicio)
INTERNOS = ("app.modulos.productos", "app.modulos.grupos", "app.modulos.maestros.variantes",
            "app.modulos.maestros.genericos", "app.modulos.maestros.versiones", "app.modulos.maestros.atributos",
            "app.modulos.maestros.escalas", "app.modulos.catalogo.valores")
# Quienes son el catálogo (o lo serán al terminar la reconstrucción)
DUENOS = ("modelos/", "modulos/catalogo/", "modulos/productos/", "modulos/grupos/", "modulos/maestros/variantes.py",
          "modulos/maestros/genericos.py", "modulos/maestros/versiones.py", "modulos/maestros/atributos.py",
          "modulos/maestros/escalas.py", "instalacion/")
# Archivos que todavía leen el catálogo por dentro: la lista solo puede achicarse
PENDIENTES = {
    "main.py", "modulos/acceso/api.py", "modulos/acceso/permisos.py", "modulos/clasificacion/aranceles.py",
    "modulos/clasificacion/especialista.py", "modulos/clasificacion/familias.py",
    "modulos/clasificacion/impacto.py", "modulos/clasificacion/meta.py",
    "modulos/clasificacion/motor_clasificacion.py", "modulos/compras/flujo_oc.py", "modulos/compras/ordenes.py",
    "modulos/comun/edicion.py", "modulos/documentos/documentos.py", "modulos/empaque/packing.py",
    "modulos/empaque/recetas.py", "modulos/empresa/organizacion.py", "modulos/etiquetado/buscadores.py",
    "modulos/etiquetado/campos.py", "modulos/etiquetado/categorias.py", "modulos/etiquetado/datos.py",
    "modulos/etiquetado/familias.py", "modulos/etiquetado/generacion.py", "modulos/etiquetado/reglas.py",
    "modulos/etiquetado/trabajos.py", "modulos/etiquetado/usos.py", "modulos/facturacion/facturas.py",
    "modulos/integraciones/entidades.py", "modulos/maestros/api.py", "modulos/maestros/cargas.py",
    "modulos/maestros/catalogos.py", "modulos/maestros/gobierno.py", "modulos/reportes/fuentes.py",
    "modulos/seguimiento/buscar.py", "modulos/seguimiento/dashboard.py", "modulos/seguimiento/indicadores.py",
    "modulos/seguimiento/metricas.py", "modulos/seguimiento/seguimiento.py",
}


# Relaciones de modelos de otros módulos hacia el catálogo: se navegarían sin pasar por el
# servicio (`posicion.articulo.producto…`). Guardan el id; la lista solo puede achicarse
RELACIONES_PENDIENTES = {"FacturaLinea.articulo_version", "PosicionOC.articulo", "PosicionOC.articulo_version",
                         "ReglaEmpaque.grupo", "ReglaEmpaque.producto", "ReglaEmpaque.articulo"}
MODELOS_COMEX = {"ClasificacionProducto", "PartidaPais", "ProductoFoto", "ProductoDocumento", "ProductoVersion"}


def _usos(archivo: Path) -> list[str]:
    """Lo que el archivo importa del catálogo por dentro."""
    res = []
    for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres = {a.name for a in nodo.names}
            if nodo.module.startswith("app.modelos") and nombres & MODELOS_CATALOGO:
                res += [f"{nodo.module}.{n}" for n in sorted(nombres & MODELOS_CATALOGO)]
            if any(nodo.module == m or nodo.module.startswith(m + ".") for m in INTERNOS):
                res.append(nodo.module)
            if any(f"{nodo.module}.{n}" in INTERNOS for n in nombres):
                res += [f"{nodo.module}.{n}" for n in sorted(nombres) if f"{nodo.module}.{n}" in INTERNOS]
        elif isinstance(nodo, ast.Import):
            res += [a.name for a in nodo.names if any(a.name == m or a.name.startswith(m + ".") for m in INTERNOS)]
    return res


def _archivos():
    for f in sorted(APP.rglob("*.py")):
        rel = f.relative_to(APP).as_posix()
        if not rel.startswith(DUENOS):
            yield rel, f


def test_nadie_lee_el_catalogo_por_dentro():
    malos = {rel: usos for rel, f in _archivos() if rel not in PENDIENTES and (usos := _usos(f))}
    assert not malos, "Use app.modulos.catalogo.servicio en lugar de:\n" + "\n".join(f"{k}: {v}" for k, v in malos.items())


def test_la_lista_de_pendientes_solo_se_achica():
    """Un pendiente que ya no lee el catálogo por dentro sale de la lista (no se deja de recuerdo)."""
    limpios = sorted(rel for rel, f in _archivos() if rel in PENDIENTES and not _usos(f))
    assert not limpios, f"Ya no leen el catálogo por dentro; quítelos de PENDIENTES: {limpios}"


def test_ningun_modelo_ajeno_navega_hacia_el_catalogo():
    import app.modelos  # noqa: F401  (registra todos los modelos)
    from app.core.db import Base

    propios = MODELOS_CATALOGO | MODELOS_COMEX
    hacia = {f"{m.class_.__name__}.{r.key}" for m in Base.registry.mappers if m.class_.__name__ not in propios
             for r in m.relationships if r.mapper.class_.__name__ in propios}
    assert hacia <= RELACIONES_PENDIENTES, f"Relaciones nuevas hacia el catálogo: {sorted(hacia - RELACIONES_PENDIENTES)}"
    assert hacia == RELACIONES_PENDIENTES, f"Ya no existen; quítelas de RELACIONES_PENDIENTES: {sorted(RELACIONES_PENDIENTES - hacia)}"
