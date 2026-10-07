"""Catálogo del motor rehecho con las Notas Explicativas del SA

Borra toda la configuración anterior del motor (familias, capítulos de cada
familia, categorías, preguntas con sus opciones y ámbitos, reglas, clases de
material y traducciones del catálogo). Al arrancar, el sistema siembra la nueva
desde data/motor/familias. Quedan las reglas del sistema (INTERNAL_ENGINE) y
las de selección nacional (NATIONAL_SELECT), que no son de una familia.

Los artículos pasan a la categoría nueva equivalente; si no hay una, quedan sin
categoría para elegirla otra vez. Sus partidas aprobadas no cambian.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-08 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None

# categoría anterior → categoría nueva (las que no aparecen quedan sin categoría)
CATEGORIAS = {
    "camiseta": "camiseta", "camisa": "camisa", "sudadera": "sueter", "chaqueta": "chaqueta", "pantalon": "pantalon", "falda": "falda",
    "vestido": "vestido", "enterizo": "prenda_otra", "conjunto": "conjunto", "ropa_interior": "ropa_interior", "brasier": "brasier",
    "traje_bano": "traje_bano", "calcetines": "calcetines", "guantes": "guantes", "bufanda": "bufanda", "gorra": "gorra",
    "cinturon": "cinturon", "accesorio_pelo": "accesorio_pelo", "calzado": "calzado", "plantilla": "partes_calzado", "cordones": "cordones",
    "polainas": "polainas", "cuidado_calzado": "betun", "mochila": "mochila", "bolso_viaje": "bolso_viaje", "bolso_mano": "bolso_mano",
    "maleta": "maleta", "billetera": "articulo_bolsillo", "lentes_sol": "lentes", "reloj": "reloj", "bisuteria": "bisuteria",
    "sombrilla": "paraguas", "correa_reloj": "correa_reloj", "avios": "avio", "etiqueta": "cinta_etiqueta", "caja": "papel_carton",
    "inorganic_chemical": "quimico_inorganico", "acid": "quimico_inorganico", "base_alkali": "quimico_inorganico", "salt": "quimico_inorganico",
    "organic_chemical": "quimico_organico", "alcohol": "quimico_organico", "solvent": "disolvente", "dye": "colorante", "pigment": "pigmento",
    "paint_coating": "pintura", "ink": "tinta", "adhesive": "adhesivo", "surfactant": "tensoactivo", "detergent_cleaning": "tensoactivo",
    "lubricant": "lubricante", "wax": "cera", "laboratory_reagent": "reactivo", "chemical_preparation": "preparacion_quimica",
    "rubber_preparation": "aditivo_polimero", "quimico": "preparacion_quimica", "polymer_resin": "resina_plastica",
    "textile_fiber": "fibra_textil", "staple_fiber": "fibra_textil", "filament": "fibra_textil", "yarn": "hilado", "sewing_thread": "hilado",
    "woven_fabric": "tejido_plano", "knitted_fabric": "tejido_punto", "nonwoven": "no_tejido", "felt": "no_tejido",
    "coated_fabric": "tela_recubierta", "laminated_fabric": "tela_recubierta", "leather": "cuero", "split_leather": "cuero",
    "synthetic_leather": "cuero_sintetico", "plastic_resin": "resina_plastica", "plastic_primary_form": "resina_plastica",
    "plastic_sheet": "lamina_plastica", "plastic_film": "lamina_plastica", "plastic_profile": "lamina_plastica", "plastic_foam": "lamina_plastica",
    "natural_rubber": "caucho", "synthetic_rubber": "caucho", "rubber_compound": "caucho", "rubber_sheet": "caucho", "paper": "papel_carton",
    "paperboard": "papel_carton", "metal_sheet": "metal", "metal_wire": "metal", "metal_profile": "metal",
}


def upgrade() -> None:
    con = op.get_bind()
    familia = "tipo_fuente <> 'INTERNAL_ENGINE' AND tipo_regla <> 'NATIONAL_SELECT'"
    con.execute(sa.text(f"DELETE FROM reglas_condiciones WHERE regla_id IN (SELECT id FROM reglas_clasificacion WHERE {familia})"))
    con.execute(sa.text(f"DELETE FROM reglas_clasificacion WHERE {familia}"))
    for t in ("atributo_ambitos", "atributo_opciones", "atributos_def", "categorias_producto", "dominio_capitulos", "dominios_clasificacion",
              "clases_material", "traducciones_catalogo"):
        con.execute(sa.text(f"DELETE FROM {t}"))
    antes = [r[0] for r in con.execute(sa.text("SELECT DISTINCT tipo FROM productos WHERE tipo IS NOT NULL"))]
    for viejo in antes:
        con.execute(sa.text("UPDATE productos SET tipo = :n WHERE tipo = :v"), {"n": CATEGORIAS.get(viejo), "v": viejo})
    antes = [r[0] for r in con.execute(sa.text("SELECT DISTINCT categoria FROM historial_clasificacion WHERE categoria IS NOT NULL"))]
    for viejo in antes:
        con.execute(sa.text("UPDATE historial_clasificacion SET categoria = :n WHERE categoria = :v"), {"n": CATEGORIAS.get(viejo), "v": viejo})
    # Cintas, telas recubiertas y tejidos de punto son materias primas que el motor clasifica solo
    con.execute(sa.text("UPDATE control_capitulos SET candidato_auto = :si, solo_manual = :no WHERE capitulo IN ('58', '59', '60')"),
                {"si": True, "no": False})
    # La configuración cambió: el catálogo en memoria de cada proceso se vuelve a leer
    v = con.execute(sa.text("SELECT valor FROM meta WHERE clave = 'config.version'")).scalar()
    if v is None:
        con.execute(sa.text("INSERT INTO meta (clave, valor) VALUES ('config.version', '1')"))
    else:
        con.execute(sa.text("UPDATE meta SET valor = :v WHERE clave = 'config.version'"), {"v": str(int(v or 0) + 1)})


def downgrade() -> None:
    # Los datos borrados no se recuperan: la configuración anterior ya no existe en el código.
    pass
