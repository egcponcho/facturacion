"""Dependencias entre las partes del sistema (app/core/modulos.py).

Se revisan leyendo el código (ast), sin ejecutarlo. Cada carpeta de primer
nivel de `app/` (core, modelos, web, instalacion…) y cada módulo de
`app/modulos/` es una «parte».

Reglas que ya se cumplen y no pueden romperse:

1. `core` no importa nada de afuera de `core`.
2. `modelos` (las tablas) solo usa `core`.
3. `comun` (piezas compartidas) no conoce ningún módulo de negocio, salvo `acceso`.
4. `main.py` no conoce ningún módulo por nombre: los lee de su contrato.
5. Cada módulo tiene su contrato `modulo.py` con `MODULO`.

Deudas que vienen de antes y solo pueden achicarse (una entrada nueva hace
fallar la prueba; una que ya se resolvió también, para sacarla de la lista):

- DEPENDENCIAS: qué módulo importa a qué otro. Para conectar dos módulos sin
  agregar una dependencia, el que ofrece algo publica un registro y el otro
  se inscribe desde su `modulo.py` (ver comun/edicion.registrar_documento).
- CICLOS: pares de partes que se importan mutuamente.
- IMPORTS_EN_FUNCIONES: imports dentro de funciones, por parte (esconden ciclos).
- ARCHIVOS_GRANDES: archivos de más de MAX_LINEAS líneas.
"""
import ast
import importlib
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
MAX_LINEAS = 500
# Toda parte puede usar estas: el núcleo, las tablas, los esquemas y los textos
BASE = {"core", "modelos", "esquemas", "i18n"}


def _archivos():
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)


def _parte(nombre: str) -> str | None:
    """«app.modulos.compras.ordenes» → «compras»; «app.core.db» → «core»."""
    p = nombre.split(".")
    if p[0] != "app" or len(p) < 2:
        return None
    if p[1] == "modulos":
        return p[2] if len(p) > 2 else None
    return p[1]


def _parte_de(archivo: Path) -> str:
    rel = archivo.relative_to(APP.parent).with_suffix("").as_posix().replace("/", ".")
    return _parte(rel) or "app"


def _imports(archivo: Path) -> list[tuple[str, bool]]:
    """(parte importada, ¿dentro de una función?) de cada import del archivo."""
    res = []

    def visitar(nodo, en_funcion: bool):
        for hijo in ast.iter_child_nodes(nodo):
            nombres = []
            if isinstance(hijo, ast.Import):
                nombres = [a.name for a in hijo.names]
            elif isinstance(hijo, ast.ImportFrom) and hijo.module and hijo.level == 0:
                # «from app.modulos import compras» importa el módulo compras
                nombres = [f"{hijo.module}.{a.name}" for a in hijo.names] if hijo.module == "app.modulos" else [hijo.module]
            res.extend((p, en_funcion) for n in nombres if (p := _parte(n)))
            visitar(hijo, en_funcion or isinstance(hijo, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda))

    visitar(ast.parse(archivo.read_text(encoding="utf-8")), False)
    return res


def _grafo() -> dict[str, set[str]]:
    res: dict[str, set[str]] = {}
    for f in _archivos():
        origen = _parte_de(f)
        res.setdefault(origen, set()).update(d for d, _ in _imports(f) if d != origen)
    return res


MODULOS = sorted(p.name for p in (APP / "modulos").iterdir() if (p / "__init__.py").exists())


# ---- Reglas que ya se cumplen -------------------------------------------------------------------
def test_core_no_importa_nada_de_afuera():
    assert _grafo()["core"] == set()


def test_modelos_solo_usan_core():
    assert _grafo()["modelos"] <= {"core"}


def test_comun_no_conoce_modulos_de_negocio():
    assert _grafo()["comun"] - BASE <= {"acceso", "web"}


def test_main_no_conoce_modulos_por_nombre():
    assert not set(MODULOS) & _grafo()["main"]


def test_cada_modulo_tiene_su_contrato():
    from app.core.modulos import Modulo, disponibles

    assert disponibles() == MODULOS, "Cada carpeta de app/modulos/ necesita su modulo.py"
    for clave in MODULOS:
        m = importlib.import_module(f"app.modulos.{clave}.modulo").MODULO
        assert isinstance(m, Modulo) and m.clave == clave and m.descripcion


# ---- Deudas que solo pueden achicarse --------------------------------------------------------------
DEPENDENCIAS = {
    ("acceso", "comex"), ("acceso", "comun"), ("acceso", "empresa"), ("acceso", "web"),
    ("catalogo", "acceso"), ("catalogo", "comun"), ("catalogo", "maestros"), ("catalogo", "productos"),
    ("catalogo", "web"), ("clasificacion", "acceso"), ("clasificacion", "comun"), ("clasificacion", "documentos"),
    ("clasificacion", "instalacion"), ("clasificacion", "productos"), ("clasificacion", "web"), ("comex", "acceso"),
    ("comex", "catalogo"), ("comex", "comun"), ("compras", "acceso"), ("compras", "catalogo"),
    ("compras", "comex"), ("compras", "comun"), ("compras", "documentos"), ("compras", "empaque"),
    ("compras", "facturacion"), ("compras", "maestros"), ("compras", "transporte"), ("compras", "web"),
    ("comun", "acceso"), ("comun", "web"), ("documentos", "acceso"), ("documentos", "catalogo"),
    ("documentos", "comex"), ("documentos", "empaque"), ("documentos", "empresa"), ("documentos", "facturacion"),
    ("documentos", "maestros"), ("empaque", "acceso"), ("empaque", "catalogo"), ("empaque", "comun"),
    ("empaque", "documentos"), ("empaque", "facturacion"), ("empaque", "maestros"), ("empaque", "recepcion"),
    ("empaque", "transporte"), ("empaque", "web"), ("empresa", "acceso"), ("empresa", "catalogo"),
    ("empresa", "comun"), ("empresa", "instalacion"), ("empresa", "web"), ("etiquetado", "acceso"),
    ("etiquetado", "catalogo"), ("etiquetado", "comex"), ("etiquetado", "comun"), ("etiquetado", "empaque"),
    ("etiquetado", "empresa"), ("etiquetado", "maestros"), ("etiquetado", "web"), ("facturacion", "acceso"),
    ("facturacion", "catalogo"), ("facturacion", "comex"), ("facturacion", "comun"), ("facturacion", "documentos"),
    ("facturacion", "empaque"), ("facturacion", "maestros"), ("facturacion", "web"), ("instalacion", "acceso"),
    ("instalacion", "catalogo"), ("instalacion", "clasificacion"), ("instalacion", "comun"), ("instalacion", "empaque"),
    ("instalacion", "empresa"), ("instalacion", "etiquetado"), ("instalacion", "maestros"), ("instalacion", "productos"),
    ("instalacion", "transporte"), ("integraciones", "acceso"), ("integraciones", "catalogo"), ("integraciones", "compras"),
    ("integraciones", "comun"), ("integraciones", "documentos"), ("integraciones", "web"), ("maestros", "acceso"),
    ("maestros", "catalogo"), ("maestros", "clasificacion"), ("maestros", "comun"), ("maestros", "documentos"),
    ("maestros", "empresa"), ("maestros", "productos"), ("maestros", "transporte"), ("maestros", "web"),
    ("main", "instalacion"), ("plataforma", "acceso"), ("plataforma", "comun"), ("plataforma", "instalacion"),
    ("plataforma", "web"), ("productos", "acceso"), ("productos", "catalogo"), ("productos", "clasificacion"),
    ("productos", "comex"), ("productos", "comun"), ("productos", "documentos"), ("productos", "empaque"),
    ("productos", "etiquetado"), ("productos", "facturacion"), ("productos", "maestros"), ("productos", "web"),
    ("recepcion", "acceso"), ("recepcion", "catalogo"), ("recepcion", "comun"), ("recepcion", "facturacion"),
    ("recepcion", "maestros"), ("recepcion", "transporte"), ("recepcion", "web"), ("reportes", "acceso"),
    ("reportes", "catalogo"), ("reportes", "comex"), ("reportes", "comun"), ("reportes", "documentos"),
    ("reportes", "seguimiento"), ("reportes", "web"), ("seguimiento", "acceso"), ("seguimiento", "catalogo"),
    ("seguimiento", "comex"), ("seguimiento", "compras"), ("seguimiento", "comun"), ("seguimiento", "documentos"),
    ("seguimiento", "empaque"), ("seguimiento", "empresa"), ("seguimiento", "facturacion"), ("seguimiento", "transporte"),
    ("seguimiento", "web"), ("transporte", "acceso"), ("transporte", "catalogo"), ("transporte", "comun"),
    ("transporte", "documentos"), ("transporte", "facturacion"), ("transporte", "recepcion"), ("transporte", "web"),
    ("web", "acceso"), ("web", "comun"), ("web", "documentos"), ("web", "empresa"),
    ("web", "maestros"),
}
CICLOS = {
    ("acceso", "comex"), ("acceso", "comun"), ("acceso", "empresa"), ("acceso", "web"),
    ("catalogo", "maestros"), ("catalogo", "productos"), ("clasificacion", "instalacion"), ("clasificacion", "productos"),
    ("comun", "web"), ("documentos", "empaque"), ("documentos", "facturacion"), ("documentos", "maestros"),
    ("empaque", "facturacion"), ("empresa", "instalacion"), ("empresa", "web"), ("maestros", "productos"),
    ("maestros", "web"), ("recepcion", "transporte"),
}
IMPORTS_EN_FUNCIONES = {
    "acceso": 9, "catalogo": 20, "clasificacion": 150, "comex": 6, "compras": 12,
    "comun": 2, "core": 6, "documentos": 11, "empaque": 11, "empresa": 3,
    "etiquetado": 67, "facturacion": 5, "instalacion": 28, "integraciones": 6, "maestros": 33,
    "main": 6, "modelos": 13, "plataforma": 6, "productos": 45, "recepcion": 1,
    "reportes": 7, "seguimiento": 20, "transporte": 5, "web": 3,
}
ARCHIVOS_GRANDES = {
    "instalacion/demo.py", "modelos/clasificacion.py",
    "modelos/maestros.py", "modulos/catalogo/servicio.py",
    "modulos/clasificacion/api.py", "modulos/clasificacion/aranceles.py",
    "modulos/clasificacion/atributos.py", "modulos/clasificacion/motor_clasificacion.py",
    "modulos/clasificacion/oficial.py", "modulos/compras/flujo_oc.py",
    "modulos/compras/ordenes.py", "modulos/documentos/documentos.py",
    "modulos/empaque/packing.py", "modulos/empaque/recetas.py",
    "modulos/etiquetado/api.py", "modulos/etiquetado/campos.py",
    "modulos/etiquetado/generacion.py", "modulos/etiquetado/plantillas.py",
    "modulos/etiquetado/render.py", "modulos/etiquetado/trabajos.py",
    "modulos/etiquetado/usos.py", "modulos/facturacion/facturas.py",
    "modulos/integraciones/servicio.py", "modulos/maestros/cargas.py",
    "modulos/maestros/catalogos.py", "modulos/productos/ficha.py",
    "modulos/productos/productos.py", "modulos/seguimiento/indicadores.py",
    "modulos/seguimiento/seguimiento.py", "modulos/transporte/transporte.py",
}


def test_dependencias_entre_modulos_solo_se_achican():
    actual = {(o, d) for o, ds in _grafo().items() for d in ds - BASE}
    nuevas = sorted(actual - DEPENDENCIAS)
    assert not nuevas, ("Dependencias nuevas entre partes; conéctelas por un registro (ver comun/edicion."
                        f"registrar_documento y core/modulos.py): {nuevas}")
    resueltas = sorted(DEPENDENCIAS - actual)
    assert not resueltas, f"Ya no existen; quítelas de DEPENDENCIAS: {resueltas}"


def test_ciclos_solo_se_achican():
    g = _grafo()
    actual = {(a, b) for a in g for b in g[a] if a < b and a in g.get(b, set())}
    assert actual <= CICLOS, f"Ciclos nuevos entre partes: {sorted(actual - CICLOS)}"
    assert actual == CICLOS, f"Ciclos resueltos; quítelos de CICLOS: {sorted(CICLOS - actual)}"


def test_imports_en_funciones_solo_se_achican():
    actual: dict[str, int] = {}
    for f in _archivos():
        n = sum(1 for _, dentro in _imports(f) if dentro)
        if n:
            actual[_parte_de(f)] = actual.get(_parte_de(f), 0) + n
    mas = {p: (n, IMPORTS_EN_FUNCIONES.get(p, 0)) for p, n in actual.items() if n > IMPORTS_EN_FUNCIONES.get(p, 0)}
    assert not mas, f"Imports nuevos dentro de funciones (actual, permitido); súbalos al inicio del archivo: {mas}"
    menos = {p: (actual.get(p, 0), n) for p, n in IMPORTS_EN_FUNCIONES.items() if actual.get(p, 0) < n}
    assert not menos, f"Bajaron los imports dentro de funciones (actual, en la lista); actualice IMPORTS_EN_FUNCIONES: {menos}"


def test_archivos_grandes_solo_se_achican():
    actual = {f.relative_to(APP).as_posix() for f in _archivos()
              if len(f.read_text(encoding="utf-8").splitlines()) > MAX_LINEAS}
    assert actual <= ARCHIVOS_GRANDES, f"Archivos nuevos de más de {MAX_LINEAS} líneas; pártalos: {sorted(actual - ARCHIVOS_GRANDES)}"
    assert actual == ARCHIVOS_GRANDES, f"Ya bajaron de {MAX_LINEAS} líneas; quítelos: {sorted(ARCHIVOS_GRANDES - actual)}"
