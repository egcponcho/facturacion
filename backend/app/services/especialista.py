"""Opinión del especialista en clasificación con Claude (opcional).

Solo se ofrece si hay ANTHROPIC_API_KEY. Le pasa la ficha del producto tal
como la lee el motor único (campos, composición, sugerencia, razones,
alertas y parecidos) y hasta dos fotos, y devuelve una opinión
estructurada (JSON validado por el esquema). Es una segunda opinión: nunca
aprueba nada por su cuenta.
"""
import base64
import json
import logging

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Usuario
from . import productos
from .common import ErrorNegocio, exigir

log = logging.getLogger(__name__)

ROL = ("You are a customs tariff classification specialist for Central America and Panama. You use the Central "
       "American Tariff System (SAC), based on the Harmonized System 2022, its General Rules of Interpretation, the "
       "section and chapter notes and the Explanatory Notes. You are precise and conservative: if a piece of data "
       "changes the subheading, you say so. Answer in English.")

ESQUEMA = {
    "type": "object",
    "properties": {
        "codigo": {"type": "string", "description": "6-digit HS subheading, digits only"},
        "descripcion": {"type": "string"},
        "confianza": {"type": "string", "enum": ["high", "medium", "low"]},
        "razonamiento": {"type": "string"},
        "reglas_aplicadas": {"type": "array", "items": {"type": "string"}},
        "alternativas": {"type": "array", "items": {
            "type": "object", "properties": {"codigo": {"type": "string"}, "cuando": {"type": "string"}},
            "required": ["codigo", "cuando"], "additionalProperties": False}},
        "datos_faltantes": {"type": "array", "items": {"type": "string"}},
        "preguntas_proveedor": {"type": "array", "items": {"type": "string"}},
        "correcciones": {"type": "array", "items": {
            "type": "object", "properties": {"campo": {"type": "string"}, "valor": {"type": "string"},
                                             "motivo": {"type": "string"}},
            "required": ["campo", "valor", "motivo"], "additionalProperties": False}},
    },
    "required": ["codigo", "descripcion", "confianza", "razonamiento", "reglas_aplicadas", "alternativas",
                 "datos_faltantes", "preguntas_proveedor", "correcciones"],
    "additionalProperties": False,
}


def disponible() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def entrada(db: Session, p) -> dict:
    """Lo que ve el especialista, armado con el motor único de clasificación."""
    from .motor_clasificacion import clasificar_producto

    r = clasificar_producto(db, productos.entrada_producto(p), paises=False)
    lineas = [f"Category: {(r.get('categoria') or {}).get('nombre') or p.tipo or 'not chosen'}",
              f"Style / name: {p.estilo} {p.nombre or ''}".strip(), f"Country of origin: {p.pais_origen or 'not given'}"]
    corregibles = []
    for c in r["campos"]:
        if c["tipo_dato"] == "composition":
            if c.get("valor"):
                lineas.append(f"{c['etiqueta']}: {c['valor']}")
            continue
        if c.get("valor") not in (None, "", [], False) or (c["tipo_dato"] == "boolean" and c.get("respondida")):
            lineas.append(f"{c['etiqueta']}: {productos._valor_legible(c)}")
        if c["tipo_dato"] in ("select", "boolean") and c["seccion"] != "derivado":
            ops = "Yes / No (true / false)" if c["tipo_dato"] == "boolean" else ", ".join(f"{o['codigo']} = {o['etiqueta']}" for o in c["opciones"])
            corregibles.append(f"- {c['codigo']} ({c['etiqueta']}): {ops}")
    for c in r["campos"]:
        if c["tipo_dato"] == "composition" and c["codigo"].startswith("comp."):
            corregibles.append(f"- {c['codigo']} ({c['etiqueta']}): composition text, e.g. 60% cotton, 40% polyester")
    if (p.ficha or {}).get("uso"):
        lineas.append(f"What it is for: {p.ficha['uso']}")
    parecidos = [f"{x['estilo']} {x.get('color') or ''}: {x['codigo_txt']}" for x in r.get("parecidos") or []]
    return {"ficha_texto": "\n".join(lineas), "sugerido": r.get("hs6_txt"), "confianza": r["confianza"], "razones": r["razones"][:30],
            "alertas": [a["msg"] for a in r["alertas"]][:30], "parecidos": parecidos[:10], "campos": "\n".join(corregibles)}


def _prompt(d: dict, notas: list | None = None) -> str:
    partes = [
        "Product to classify (data captured by the supplier; it may contain errors):", d["ficha_texto"],
        f"\nRule engine suggestion: {d['sugerido'] or 'no code'} (confidence {d['confianza'] or 'n/a'}).",
    ]
    if d["razones"]:
        partes.append("Engine reasoning:\n" + "\n".join(f"- {r}" for r in d["razones"]))
    partes.append("Inconsistencies detected by the system:\n" + "\n".join(f"- {a}" for a in d["alertas"])
                  if d["alertas"] else "The system found no inconsistencies, but review it anyway.")
    if d["parecidos"]:
        partes.append("Similar products already approved:\n" + "\n".join(f"- {p}" for p in d["parecidos"]))
    if notas:
        partes.append("Legal notes of the SAC that apply (rules, section and chapter notes):\n" + "\n".join(
            f"- {n.codigo} note {n.numero}: {n.texto}" for n in notas))
    partes.append(
        "First check whether the data contradict each other (name, use, composition, attributes and photos); if they "
        "do, say so and classify with the most reliable data. Do not invent data: if something is missing, ask for it "
        "in the questions. In the reasoning (3 to 5 sentences) cite the General Rules of Interpretation and the legal "
        "notes that apply. Only propose corrections when the evidence shows a captured value is wrong, and only with "
        "these fields and values (use the code before the parenthesis as the field):\n" + (d["campos"] or "- uso"))
    return "\n\n".join(partes)


def analizar(db: Session, user: Usuario, producto_id: int, d) -> dict:
    exigir(user, "producto.clasificar")
    p = productos._producto(db, user, producto_id)
    if not disponible():
        raise ErrorNegocio("The specialist opinion is not configured (ANTHROPIC_API_KEY).", 409, "sin_especialista")
    import anthropic  # solo se carga si la opción está configurada

    contenido = []
    datos = entrada(db, p)
    if d.con_fotos:
        for f in p.fotos[:2]:
            try:
                with open(f.ruta, "rb") as fh:
                    img = fh.read()
            except OSError:
                continue
            if f.tipo_mime in ("image/jpeg", "image/png", "image/webp") and len(img) <= 5 * 1024 * 1024:
                contenido.append({"type": "image", "source": {"type": "base64", "media_type": f.tipo_mime,
                                                              "data": base64.standard_b64encode(img).decode()}})
    texto = _prompt(datos, productos.notas_de(db, productos.digitos(datos["sugerido"])))
    if contenido:
        texto += f"\n\n{len(contenido)} photo(s) of the product are attached: use them to confirm fabric, style, height and visible materials."
    contenido.append({"type": "text", "text": texto})

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=120.0)
    try:
        r = client.beta.messages.create(
            model=settings.CLAUDE_MODELO,
            max_tokens=16000,
            system=ROL,
            messages=[{"role": "user", "content": contenido}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": ESQUEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError:
        raise ErrorNegocio("The specialist is busy right now. Try again in a minute.", 429, "limite")
    except anthropic.APIConnectionError:
        raise ErrorNegocio("Could not reach the specialist service. Try again.", 502, "sin_conexion")
    except anthropic.APIStatusError as e:
        log.warning("Claude: %s %s", e.status_code, getattr(e, "message", ""))
        raise ErrorNegocio("The specialist could not answer this time.", 502, "error_especialista")
    if r.stop_reason == "refusal":
        raise ErrorNegocio("The specialist declined this request.", 422, "rechazado")
    if r.stop_reason == "max_tokens":
        raise ErrorNegocio("The specialist answer was cut off. Try again.", 502, "incompleto")
    texto = next((b.text for b in r.content if b.type == "text"), "")
    try:
        op = json.loads(texto)
    except ValueError:
        raise ErrorNegocio("The specialist answer could not be read.", 502, "respuesta_invalida")
    op["codigo"] = productos.digitos(op.get("codigo"))[:6]
    op["con_fotos"] = sum(1 for b in contenido if b["type"] == "image")
    op["fecha"] = productos.ahora().isoformat()
    productos.guardar_opinion(db, user, producto_id, op)
    productos.registrar(db, user, "producto", p.id, "opinion_especialista",
                        {"codigo": productos.fmt_codigo(op["codigo"]), "confianza": op.get("confianza")})
    return op
