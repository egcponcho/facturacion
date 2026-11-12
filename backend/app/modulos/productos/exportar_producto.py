"""La ficha de una versión del producto y su exportación (la ficha en PDF y la
lista de productos en Excel).
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import (
    Producto,
    Usuario,
)
from app.modulos.comex import flujo
from app.modulos.comex.servicio import (  # noqa: F401
    APROBADOS,
    BORRADORES,
    ESTADOS,
    PENDIENTES,
    digitos,
    fmt_codigo,
    sin_marca,
)
from app.modulos.comun import tabla
from app.modulos.documentos import aduana
from app.modulos.maestros import variantes as var_svc
from app.modulos.productos.consulta import _columnas_productos, detalle, listar, ver_producto
from app.modulos.productos.productos import destinos, etiquetas_ficha


def ficha_de_version(db: Session, user: Usuario, producto_id: int, version: int | None = None) -> dict:
    """La ficha vigente o, con `version`, la copia cerrada de una versión anterior."""
    d = {**detalle(db, user, producto_id), "etiquetas": etiquetas_ficha(db)}
    if not version or version == d["version_ficha"]:
        return d
    p = ver_producto(db, user, producto_id)
    v = next((x for x in p.versiones if x.version == version), None)
    if not v:
        raise ErrorNegocio(f"Version {version} does not exist.", 404, "no_encontrado")
    x = v.datos or {}
    partidas = x.get("partidas") or {}
    d = {**d, "version_ficha": v.version, "tipo": x.get("tipo"), "ficha": x.get("ficha") or {},
            "codigo": fmt_codigo(x.get("codigo")) if x.get("codigo") else None,
            "sugerido": fmt_codigo(x.get("sugerido")) if x.get("sugerido") else None,
            "estado": x.get("estado"), "estado_txt": ESTADOS.get(x.get("estado"), x.get("estado")),
            "descripcion_aduana": x.get("descripcion_aduana"), "descripcion_comercial": x.get("descripcion_comercial"),
            "pais_origen": x.get("pais_origen"), "analisis": x.get("analisis") or {}, "confianza": x.get("confianza"),
            "partidas": {k: (c if isinstance(c, dict) else {"codigo": c}) for k, c in partidas.items()},
            "revisado_por": x.get("revisado_por"), "revisado_en": x.get("revisado_en"), "observaciones": None,
            "vigencia": {"desde": v.desde, "hasta": v.hasta, "motivo": v.motivo}, "historica": True}
    if not flujo.ve_sugerencia(db, user) and x.get("estado") not in APROBADOS:
        flujo.ocultar_resumen(d)
    return d


def ver_version(db: Session, user: Usuario, producto_id: int, version: int) -> dict:
    from app.modulos.documentos import documentos
    d = ficha_de_version(db, user, producto_id, version)
    return {"version": d["version_ficha"], "vigencia": d.get("vigencia"), "estado_txt": d.get("estado_txt"),
            **documentos.secciones_ficha(d)}


def exportar_ficha(db: Session, user: Usuario, producto_id: int, formato: str = "pdf",
                   version: int | None = None) -> tuple[bytes, str]:
    from app.modulos.acceso import visibilidad
    from app.modulos.documentos import documentos, exportar
    d = visibilidad.quitar(ficha_de_version(db, user, producto_id, version))  # sin lo que el rol no ve
    nombre = f"ficha_{re.sub(r'[^A-Za-z0-9._-]+', '_', d['codigo_generico'] or str(d['id']))}" + (
        f"_v{d['version_ficha']}" if version else "")
    if formato == "xlsx":
        return exportar.exportar_ficha(d, documentos.secciones_ficha(d)), nombre
    return documentos.pdf_ficha_producto(d), nombre


def exportar_lista(db: Session, user: Usuario, filtros: dict, orden: str | None, formato: str,
                   por_columna: dict | None = None) -> bytes:
    """Reporte de productos con su composición, descripción aduanal y el
    código nacional guardado para cada país destino (con los filtros de la
    lista, también los de cada columna)."""
    from app.modulos.documentos import documentos, exportar
    r = listar(db, user, filtros, 1, 100_000, orden, por_columna)
    k = r["kpis"]
    indicadores = [("Products", f"{k['total']:,}"), ("Drafts", f"{k['borradores']:,}"), ("In review", f"{k['revision']:,}"),
                   ("Returned", f"{k['observado']:,}"), ("Approved", f"{k['aprobados']:,}")]
    ids = [p["id"] for p in r["items"]]
    prods = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(ids))
                                         .options(selectinload(Producto.partidas)))} if ids else {}
    paises = [d["iso"] for d in destinos(db)]
    nombre_parte = etiquetas_ficha(db)["partes"]

    def comp(p: Producto | None) -> str:
        c = ((p.comex.ficha or {}).get("comp") or {}) if p else {}
        return " · ".join(f"{nombre_parte.get(k) or documentos._legible(k)}: {v}" for k, v in c.items() if v) if isinstance(c, dict) else ""

    def codigos(p: Producto | None) -> dict:
        return {x.pais: fmt_codigo(x.codigo) for x in (p.partidas if p else []) if x.codigo}

    nombres = {"q": "Search", "estado": "Status", "tipo": "Type", "proveedor_id": "Supplier", "familia": "Family",
               "producto": "Product", "generico": "Product code", "proveedor": "Supplier", "codigo": "HS code",
               "origen": "Origin"}
    nombres.update({f"atr.{k}": v for k, v in var_svc.nombres(db).items()})
    columnas_validas = _columnas_productos(db, user)
    de_columnas = [(c, ", ".join("—" if x == tabla.VACIO else x for x in v))
                   for c, v in (por_columna or {}).items() if c in columnas_validas]
    texto = " · ".join(f"{nombres.get(c, c)}: {v}" for c, v in [*filtros.items(), *de_columnas] if v not in (None, ""))
    texto = f"Filters: {texto}" if texto else "No filters"
    titulo, sub = "Products and tariff classification", "Technical sheets, composition, HS codes and national codes by destination"
    if formato == "pdf":
        columnas = [("Product code", 1, False), ("Name", 2.1, False), ("Supplier", 1, False), ("Type", 0.8, False),
                    ("Status", 0.8, False), ("HS code", 0.8, False), ("Origin", 0.5, False), ("Composition", 2.6, False)] \
            + [(iso, 1, False) for iso in paises]
        filas = []
        for p in r["items"]:
            cods = codigos(prods.get(p["id"]))
            filas.append([p["codigo_generico"] or "—", p["nombre"] or "—", p["proveedor"] or "—", p["tipo"] or "—", p["estado_txt"],
                          p["codigo"] or "—", p["pais_origen"] or "—", comp(prods.get(p["id"])) or "—"]
                         + [cods.get(iso, "—") for iso in paises])
        return documentos.pdf_reporte(titulo, sub, texto, indicadores, columnas, [[str(v) for v in f] for f in filas])
    columnas = [("Product code", 1, False), ("Name", 1.8, False), ("Attributes", 2.4, False), ("Supplier", 1.2, False), ("Type", 0.9, False), ("Status", 0.9, False), ("Version", 0.6, True), ("HS code", 0.9, False),
                ("Suggested", 0.9, False), ("Origin", 0.6, False), ("Customs description", 4, False),
                ("Commercial description", 1.8, False), ("Composition", 4, False)] \
        + [(f"Code {iso}", 1.4, False) for iso in paises] + [("SKUs", 0.5, True)]
    filas, partes, codigos_filas = [], [], []
    for p in r["items"]:
        pr = prods.get(p["id"])
        cods = codigos(pr)
        filas.append([p["codigo_generico"] or "—", p["nombre"] or "—", var_svc.texto(p["atributos"]) or "—", p["proveedor"] or "—",
                      p["tipo"] or "—", p["estado_txt"], pr.comex.version_ficha if pr else 1, p["codigo"] or "—",
                      p["sugerido"] or "—", p["pais_origen"] or "—", (pr.comex.descripcion_aduana if pr else None) or "—",
                      p.get("descripcion_comercial") or "—", comp(pr) or "—"]
                     + [cods.get(iso, "—") for iso in paises] + [p["skus"]])
        c = ((pr.comex.ficha or {}).get("comp") or {}) if pr else {}
        for parte, materiales in (c.items() if isinstance(c, dict) else []):
            if materiales:
                partes.append([p["codigo_generico"] or "—", p["nombre"] or "—", nombre_parte.get(parte) or documentos._legible(parte),
                               str(materiales)])
        for x in (pr.partidas if pr else []):
            codigos_filas.append([p["codigo_generico"] or "—", p["nombre"] or "—", x.pais, fmt_codigo(x.codigo) or "—",
                                  f"{x.dai}%" if x.dai not in (None, "") else "—", documentos.ESTADO_PARTIDA.get(x.estado, x.estado or "—"),
                                  "By hand" if x.manual else (x.fuente or "—").capitalize()])
    hojas = [
        {"titulo": "Composition", "columnas": [("Product code", 1, False), ("Name", 2.4, False),
                                               ("Part", 1.6, False), ("Materials", 5, False)], "filas": partes},
        {"titulo": "National codes", "columnas": [("Product code", 1, False), ("Name", 2.4, False),
                                                  ("Country", 0.7, False), ("Code", 1.6, False),
                                                  (aduana.titulo_derecho(aduana.nombres(db)), 0.9, False),
                                                  ("Status", 0.9, False), ("Source", 0.9, False)], "filas": codigos_filas},
    ]
    return exportar.exportar_reporte(titulo, sub, texto, indicadores, columnas, filas, hojas)

