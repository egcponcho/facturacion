"""Generador de reportes: fuentes y campos que controla el servidor, alcance de
datos del usuario, datos reservados por rol, filtros por tipo, agrupación,
exportación (CSV, Excel, PDF) y reportes guardados (operativos y analíticos)."""
import csv
import io

from conftest import Api
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modelos import OrdenCompra, Proveedor


def _vista(api, definicion):
    return api.post("/reportes/vista", {"definicion": definicion})


def test_fuentes_y_alcance(interno, tnf):
    fuentes = {f["clave"]: f for f in interno.get("/reportes/fuentes").json()}
    assert {"ordenes", "lineas_oc", "facturas", "embarques", "productos"} <= set(fuentes)
    assert all(c["tipo"] in ("texto", "numero", "moneda", "fecha", "estado") for c in fuentes["ordenes"]["campos"])
    assert "embarques" not in {f["clave"] for f in tnf.get("/reportes/fuentes").json()}
    assert _vista(tnf, {"fuente": "embarques", "columnas": ["codigo"]}).status_code == 403
    # Mismo reporte, distinto alcance: el proveedor solo ve sus OCs
    d = {"fuente": "ordenes", "columnas": ["numero", "proveedor"]}
    with SessionLocal() as db:
        todas = db.scalar(select(func.count()).select_from(OrdenCompra))
        prov = db.scalar(select(Proveedor.id).where(Proveedor.codigo == "TNF"))
        de_tnf = db.scalar(select(func.count()).select_from(OrdenCompra).where(OrdenCompra.proveedor_id == prov))
    assert _vista(interno, d).json()["total"] == todas
    r = _vista(tnf, d).json()
    assert r["total"] == de_tnf and {f[1] for f in r["filas"]} == {"The North Face"}


def test_filtros_orden_y_agrupacion(interno):
    with SessionLocal() as db:
        aprobadas = db.scalar(select(func.count()).select_from(OrdenCompra).where(OrdenCompra.estado == "APROBADA"))
    r = _vista(interno, {"fuente": "ordenes", "columnas": ["numero", "estado", "cantidad"],
                         "filtros": [{"campo": "estado", "op": "igual", "valor": "APROBADA"}],
                         "orden": {"campo": "cantidad", "dir": "desc"}}).json()
    assert r["tipo"] == "operativo" and r["total"] == aprobadas
    cantidades = [f[2] for f in r["filas"]]
    assert cantidades == sorted(cantidades, reverse=True)
    # Analítico: totales por proveedor que cuadran con el total
    a = _vista(interno, {"fuente": "ordenes", "agrupar": ["proveedor"],
                         "medidas": [{"campo": "*", "funcion": "contar"}, {"campo": "cantidad", "funcion": "suma"}]}).json()
    assert a["tipo"] == "analitico" and [c["clave"] for c in a["columnas"]] == ["proveedor", "contar_todo", "suma_cantidad"]
    with SessionLocal() as db:
        assert sum(f[1] for f in a["filas"]) == db.scalar(select(func.count()).select_from(OrdenCompra))
    # Texto con comodines: se buscan tal cual, sin romper la consulta
    r = _vista(interno, {"fuente": "ordenes", "columnas": ["numero"], "filtros": [{"campo": "numero", "op": "contiene", "valor": "%'_"}]})
    assert r.status_code == 200 and r.json()["total"] == 0
    # Fechas relativas y rangos
    r = _vista(interno, {"fuente": "lineas_oc", "columnas": ["oc", "cantidad"],
                         "filtros": [{"campo": "fecha_xf", "op": "ultimos_dias", "valor": 3650},
                                     {"campo": "cantidad", "op": "entre", "valor": [0, 1000000]}]})
    assert r.status_code == 200, r.text


def test_validacion_de_la_definicion(interno):
    malos = [
        {"fuente": "otra", "columnas": ["x"]},
        {"fuente": "ordenes", "columnas": []},
        {"fuente": "ordenes", "columnas": ["no_existe"]},
        {"fuente": "ordenes", "agrupar": ["valor"], "medidas": []},
        {"fuente": "ordenes", "columnas": ["numero"], "filtros": [{"campo": "cantidad", "op": "contiene", "valor": "1"}]},
        {"fuente": "ordenes", "columnas": ["numero"], "filtros": [{"campo": "fecha", "op": "desde", "valor": "ayer"}]},
        {"fuente": "ordenes", "agrupar": ["proveedor"], "medidas": [{"campo": "proveedor", "funcion": "suma"}]},
        {"fuente": "ordenes", "columnas": ["numero"], "filtros": [{"campo": "estado", "op": "igual", "valor": "INVENTADO"}]},
    ]
    for d in malos:
        assert _vista(interno, d).status_code == 422, d


def test_datos_reservados_por_rol(client, admin):
    """Un rol que no ve precios no los puede pedir en un reporte."""
    rol = admin.post("/roles", {"nombre": "Report reader", "permisos": ["oc.ver"], "datos_ocultos": ["precios"]}).json()
    u = admin.post("/usuarios", {"email": "lector@demo.com", "nombre": "Reader", "rol_id": rol["id"],
                                 "telefono": "+50370000151", "dos_pasos": True}).json()
    api = Api(client, "lector@demo.com", u["password_temporal"])
    api.post("/auth/password", {"actual": u["password_temporal"], "nueva": "Lee#Reportes2026"})
    campos = {c["clave"] for c in next(f for f in api.get("/reportes/fuentes").json() if f["clave"] == "ordenes")["campos"]}
    assert "valor" not in campos and "numero" in campos
    assert _vista(api, {"fuente": "ordenes", "columnas": ["numero", "valor"]}).status_code == 422


def test_exportar_csv_excel_y_pdf(interno):
    d = {"fuente": "ordenes", "columnas": ["numero", "proveedor", "estado"]}
    r = interno.post("/reportes/exportar?formato=csv&idioma=en", {"definicion": d, "titulo": "POs"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    filas = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert filas[0] == ["PO", "Supplier", "Status"] and len(filas) == _vista(interno, d).json()["total"] + 1
    assert all(f[2] in ("Draft", "Pending approval", "Rejected", "Approved", "Closed", "Cancelled") for f in filas[1:])
    r = interno.post("/reportes/exportar?formato=xlsx", {"definicion": d})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    r = interno.post("/reportes/exportar?formato=pdf", {"definicion": d})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert interno.post("/reportes/exportar?formato=doc", {"definicion": d}).status_code == 422


def test_reportes_guardados(interno, admin, tnf):
    d = {"fuente": "ordenes", "columnas": ["numero", "proveedor"], "filtros": [{"campo": "estado", "op": "igual", "valor": "APROBADA"}]}
    r = interno.post("/reportes", {"nombre": "Approved POs", "definicion": d})
    assert r.status_code == 200, r.text
    op = r.json()
    an = interno.post("/reportes", {"nombre": "POs by supplier", "compartido": True,
                                    "definicion": {"fuente": "ordenes", "agrupar": ["proveedor"],
                                                   "medidas": [{"campo": "*", "funcion": "contar"}]}}).json()
    lista = interno.get("/reportes").json()
    assert op["id"] in [x["id"] for x in lista["operativos"]] and an["id"] in [x["id"] for x in lista["analiticos"]]
    assert lista["sistema"]
    assert interno.post("/reportes", {"nombre": "Approved POs", "definicion": d}).status_code == 409
    # Se vuelve a calcular al abrirlo
    det = interno.get(f"/reportes/{op['id']}").json()
    assert det["resultado"]["total"] == _vista(interno, d).json()["total"]
    assert interno.get(f"/reportes/{op['id']}/exportar", params={"formato": "csv"}).status_code == 200
    # Uno privado no lo ve otra persona; uno compartido sí, pero no lo cambia
    assert admin.get(f"/reportes/{op['id']}").status_code == 404
    assert admin.get(f"/reportes/{an['id']}").status_code == 200
    assert tnf.get(f"/reportes/{an['id']}").status_code == 200  # puede ver su fuente: con sus propios datos
    assert tnf.patch(f"/reportes/{an['id']}", {"nombre": "Mine"}).status_code == 403
    assert tnf.post("/reportes", {"nombre": "Shared", "compartido": True, "definicion": d}).status_code == 403
    # Quien lo creó lo cambia y lo borra
    assert interno.patch(f"/reportes/{op['id']}", {"nombre": "Approved POs (all)"}).json()["nombre"] == "Approved POs (all)"
    assert interno.delete_(f"/reportes/{op['id']}").status_code == 200
    assert interno.delete_(f"/reportes/{an['id']}").status_code == 200
    assert interno.get(f"/reportes/{op['id']}").status_code == 404
