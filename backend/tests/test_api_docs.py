"""Documentación de la API (docs/API.md): cada ruta tiene la etiqueta de su
módulo y un resumen escrito (la primera línea de su docstring), no el nombre
de la función. Una ruta nueva sin docstring hace fallar esta prueba."""
from app.main import ETIQUETAS, RUTAS, app

METODOS = ("get", "post", "put", "patch", "delete")


def test_cada_ruta_tiene_docstring():
    sin = [f"{m.__name__}.{r.endpoint.__name__}" for m in RUTAS for r in m.router.routes
           if hasattr(r, "endpoint") and not (r.endpoint.__doc__ or "").strip()]
    assert not sin, f"Rutas sin docstring: {sin}"


def test_el_esquema_tiene_etiqueta_y_resumen_en_cada_operacion():
    esquema = app.openapi()
    nombres = {e["name"] for e in ETIQUETAS}
    ops = [(ruta, metodo, op) for ruta, d in esquema["paths"].items() for metodo, op in d.items() if metodo in METODOS]
    assert len(ops) > 250
    sin_etiqueta = [f"{m.upper()} {r}" for r, m, op in ops if not op.get("tags") or not set(op["tags"]) <= nombres]
    assert not sin_etiqueta, sin_etiqueta
    # FastAPI pone el nombre de la función («Listar Facturas») si no hay resumen
    sin_resumen = [f"{m.upper()} {r}" for r, m, op in ops
                   if not op.get("summary") or op["summary"] == op["operationId"].split("_api_")[0].replace("_", " ").title()]
    assert not sin_resumen, sin_resumen
    # Las etiquetas declaradas se usan todas
    assert {t for *_, op in ops for t in op["tags"]} == nombres


def test_la_documentacion_interactiva_sigue_api_docs():
    from app.core.config import settings
    # Las pruebas corren como demostración: la documentación está publicada
    assert settings.API_DOCS is True
    assert app.docs_url == "/docs" and app.openapi_url == "/openapi.json"
