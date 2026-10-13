"""Ropa: capítulos 61 (de punto) y 62 (excepto de punto) según sus Notas Explicativas.

Orden de decisión que fijan las notas:
1. La materia: una prenda de cuero va a 42.03, de plástico a 39.26, de caucho a
   40.15 y de peletería a 43.03 (exclusiones de los capítulos 61 y 62).
2. Bebé (estatura hasta 86 cm) manda sobre cualquier otra partida (Nota 6 b del
   61, Nota 4 b del 62): 61.11 o 62.09.
3. Tela recubierta o estratificada de 59.03, 59.06 o 59.07 manda sobre las demás
   (Nota 8 del 61, Nota 5 del 62): 61.13 o 62.10; también el fieltro y la tela
   sin tejer en el 62 (62.10.10). Una prenda acolchada de 58.11 no cuenta.
4. Punto o tejido plano decide el capítulo; para hombre o mujer, la partida
   (Nota 9 del 61 y 8 del 62: lo no identificable va con mujer).
5. La fibra que predomina en peso del tejido exterior decide la subpartida
   (Nota 2 de la Sección XI).
Los mapas por fibra se leen del texto del árbol vigente (HS 2022): por ejemplo
6101 ya no tiene subpartida de lana (va a 6101.90) y las corbatas de punto van
a 6117.80.
"""
from base import ambitos, atributo, caso, categoria, cond, opcion, por_fibra, regla, si

DOM = "APPAREL"
NE = "Explanatory Notes, chapters 61 and 62"
M, F = "M", ["F", "U"]  # lo no identificable va con mujer

# categoría → (tejido, género) → partida o prefijo de subpartidas por fibra; None = neutro
PARTIDAS = {
    "chaqueta": {("punto", M): "6101", ("punto", "F"): "6102", ("plano", M): "6201", ("plano", "F"): "6202"},
    "saco": {("punto", M): "61033", ("punto", "F"): "61043", ("plano", M): "62033", ("plano", "F"): "62043"},
    "traje": {("punto", M): "610310", ("punto", "F"): "61041", ("plano", M): "62031", ("plano", "F"): "62041"},
    "conjunto": {("punto", M): "61032", ("punto", "F"): "61042", ("plano", M): "62032", ("plano", "F"): "62042"},
    "pantalon": {("punto", M): "61034", ("punto", "F"): "61046", ("plano", M): "62034", ("plano", "F"): "62046"},
    "falda": {("punto", "F"): "61045", ("plano", "F"): "62045"},
    "vestido": {("punto", "F"): "61044", ("plano", "F"): "62044"},
    "camisa": {("punto", M): "6105", ("punto", "F"): "6106", ("plano", M): "6205", ("plano", "F"): "6206"},
    "camiseta": {("punto", None): "6109"},
    "sueter": {("punto", None): "6110", ("plano", M): "62113", ("plano", "F"): "62114"},
    "chandal": {("punto", None): "61121", ("plano", M): "62113", ("plano", "F"): "62114"},
    "ropa_esqui": {("punto", None): "611220", ("plano", None): "621120"},
    "traje_bano": {("punto", M): "61123", ("punto", "F"): "61124", ("plano", M): "621111", ("plano", "F"): "621112"},
    "prenda_otra": {("punto", None): "6114", ("plano", M): "62113", ("plano", "F"): "62114"},
}
# Con un «tipo»: categoría → atributo → valor → (tejido, género) → partida
POR_TIPO = {
    "ropa_interior": ("tipo_interior", {
        "calzon": {("punto", M): "61071", ("punto", "F"): "61082", ("plano", M): "62071", ("plano", "F"): "62089"},
        "combinacion": {("punto", "F"): "61081", ("plano", "F"): "62081"},
        "camiseta_interior": {("punto", None): "6109", ("plano", M): "62079", ("plano", "F"): "62089"},
    }),
    "ropa_dormir": ("tipo_dormir", {
        "pijama": {("punto", M): "61072", ("punto", "F"): "61083", ("plano", M): "62072", ("plano", "F"): "62082"},
        "bata": {("punto", M): "61079", ("punto", "F"): "61089", ("plano", M): "62079", ("plano", "F"): "62089"},
    }),
}
TEXTILES = list(PARTIDAS) + list(POR_TIPO) + ["prenda_bebe", "calcetines"]
APAREL = TEXTILES + ["brasier"]


def _accion(destino: str) -> dict:
    """Un código fijo o el mapa por fibra de un grupo de subpartidas."""
    if len(destino) == 6:
        return {"codigos": [destino]}
    return {"por": "fibra", "mapa": por_fibra(destino)}


def _nombre(destino: str) -> str:
    return f"{destino[:4]}.{destino[4:]}" if len(destino) == 6 else (destino[:4] + (f".{destino[4:]}x" if len(destino) > 4 else ""))


def _genero(g):
    if g is None:
        return {}
    return {"genero": g if g == M else F}


def reglas_textil(cat: str, tabla: dict, extra: dict, sufijo: str, etiqueta: str) -> list[dict]:
    out = []
    for (tejido, g), destino in tabla.items():
        quien = "" if g is None else (" for men or boys" if g == M else " for women or girls (or not identifiable)")
        conds = si(materia_base="textil", edad_no="bebe", recubierta=False, tejido=tejido, **_genero(g), **extra)
        out.append(regla(f"R-NE-ROP-{cat.upper()}-{sufijo}{tejido[:2].upper()}{g or 'X'}"[:40], cat, conds,
                         efecto=f"{etiqueta}, {'knitted' if tejido == 'punto' else 'woven'}{quien} → {_nombre(destino)} "
                                f"({'by the predominant fiber, Section XI Note 2' if len(destino) < 6 else NE})",
                         **_accion(destino)))
    return out


def reglas_comunes(cat: str) -> list[dict]:
    """Materia distinta de la textil, bebé, tela recubierta y tela sin tejer: valen para toda la ropa."""
    C = cat.upper()
    out = [
        regla(f"R-NE-ROP-{C}-CUERO", cat, si(materia_base="cuero"), ["420310"], "Garment of leather → 42.03.10 (excluded from chapters 61 and 62)"),
        regla(f"R-NE-ROP-{C}-PLAST", cat, si(materia_base="plastico"), ["392620"], "Garment of plastics → 39.26.20"),
        regla(f"R-NE-ROP-{C}-CAUCHO", cat, si(materia_base="caucho"), ["401590"], "Garment of vulcanized rubber → 40.15.90"),
        regla(f"R-NE-ROP-{C}-PIEL", cat, si(materia_base="peleteria"), ["430310"],
              "Garment of furskin or with fur parts beyond mere trimming → 43.03.10"),
    ]
    if cat == "brasier":
        return out
    out += [
        regla(f"R-NE-ROP-{C}-BEBEPU", cat, si(materia_base="textil", edad="bebe", tejido="punto"),
              efecto="Knitted baby garment (up to 86 cm) → 61.11, before any other heading (chapter 61 Note 6 b)", **_accion("6111")),
        regla(f"R-NE-ROP-{C}-BEBEPL", cat, si(materia_base="textil", edad="bebe", tejido=["plano", "no_tejido"]),
              efecto="Woven baby garment (up to 86 cm) → 62.09, before any other heading (chapter 62 Note 4 b)", **_accion("6209")),
        regla(f"R-NE-ROP-{C}-NOTEJ", cat, si(materia_base="textil", edad_no="bebe", tejido="no_tejido"), ["621010"],
              "Garment of felt or nonwovens (56.02, 56.03) → 6210.10 (chapter 62 Note 5)"),
        regla(f"R-NE-ROP-{C}-RECPU", cat, si(materia_base="textil", edad_no="bebe", recubierta=True, tejido="punto"), ["611300"],
              "Garment of knitted fabric coated or laminated (59.03, 59.06, 59.07) → 61.13 (chapter 61 Note 8)"),
    ]
    abrigo = cat == "chaqueta"
    out += [
        regla(f"R-NE-ROP-{C}-RECPLM", cat, si(materia_base="textil", edad_no="bebe", recubierta=True, tejido="plano", genero=M),
              ["621020" if abrigo else "621040"], f"Woven coated garment for men → {'6210.20' if abrigo else '6210.40'} (chapter 62 Note 5)"),
        regla(f"R-NE-ROP-{C}-RECPLF", cat, si(materia_base="textil", edad_no="bebe", recubierta=True, tejido="plano", genero=F),
              ["621030" if abrigo else "621050"], f"Woven coated garment for women → {'6210.30' if abrigo else '6210.50'} (chapter 62 Note 5)"),
    ]
    return out


def familia() -> dict:
    tops = "Tops"
    cats = [
        categoria("chaqueta", "Coat, jacket, anorak, parka, raincoat or padded vest", corto="Jacket or coat", aduana="Chaqueta", grupo="Outerwear",
                  dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=10, prioridad=48,
                  re_=r"\b(jackets?|jkt|chaquetas?|chamarras?|chumpas?|parkas?|anoraks?|windbreakers?|rompevientos|puffer|softshell|hardshell|"
                      r"coats?|abrigos?|raincoats?|impermeables?|ponchos?|capas?|padded vests?|chalecos? acolchados?|gilet)\b",
                  alias="jacket chaqueta chumpa chamarra parka anorak abrigo impermeable chaleco acolchado"),
        categoria("saco", "Tailored jacket or blazer", corto="Blazer", aduana="Saco", grupo="Outerwear", dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"],
                  orden=20, prioridad=30, re_=r"\b(blazers?|sport ?coats?|sacos? de vestir|americanas?|suit jackets?)\b", alias="saco blazer americana"),
        categoria("traje", "Suit (jacket and trousers or skirt of the same fabric)", corto="Suit", aduana="Traje", grupo="Sets", dominio=DOM,
                  capitulos=["61", "62", "42", "39", "40", "43"], orden=30, prioridad=29, re_=r"\b(suits?|trajes? (de vestir|sastre)|tuxedos?|esmoquin|ternos?)\b",
                  alias="traje terno traje sastre esmoquin"),
        categoria("conjunto", "Ensemble: matching top and bottom sold together", corto="Ensemble", aduana="Conjunto", grupo="Sets", dominio=DOM,
                  capitulos=["61", "62", "42", "39", "40", "43"], orden=40, prioridad=28, re_=r"\b(ensembles?|conjuntos?|co-?ords?|matching sets?|twinsets?)\b",
                  alias="conjunto set"),
        categoria("pantalon", "Trousers, jeans, shorts or bib overalls", corto="Trousers or shorts", aduana="Pantalón", grupo="Bottoms",
                  dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=50, prioridad=44,
                  re_=r"\b(pants|trousers|pantalon(es)?|jeans?|shorts?|joggers?|chinos?|cargos?|leggings?|mallas?|overalls?|bermudas?|capris?)\b",
                  alias="pantalón jeans short legging jogger overol de peto"),
        categoria("falda", "Skirt or divided skirt", corto="Skirt", aduana="Falda", grupo="Bottoms", dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=60,
                  prioridad=43, re_=r"\b(skirts?|faldas?|skorts?)\b", alias="falda skort"),
        categoria("vestido", "Dress", corto="Dress", aduana="Vestido", grupo="Dresses", dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=70, prioridad=42,
                  re_=r"\b(dress(es)?|vestidos?)\b", alias="vestido"),
        categoria("camisa", "Shirt, blouse or polo", corto="Shirt or blouse", aduana="Camisa", grupo=tops, dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"],
                  orden=80, prioridad=46, re_=r"\b(shirts?|camisas?|blouses?|blusas?|polos?|button[- ]?(down|up))\b", alias="camisa blusa polo"),
        categoria("camiseta", "T-shirt, tank top or singlet", corto="T-shirt", aduana="Camiseta", grupo=tops, dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"],
                  orden=90, prioridad=49, re_=r"\b(tees?|t-?shirts?|camisetas?|playeras?|tanks?|tank tops?|singlets?|base ?layers?)\b",
                  alias="camiseta playera t-shirt tank top"),
        categoria("sueter", "Sweater, sweatshirt, hoodie, cardigan or vest", corto="Sweater or sweatshirt", aduana="Suéter", grupo=tops,
                  dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=100, prioridad=47,
                  re_=r"\b(sweaters?|sueter(es)?|sweatshirts?|sudaderas?|hoodies?|pullovers?|jerseys?|cardigans?|fleece|polar|crew ?necks?|vests?|chalecos?)\b",
                  alias="suéter sudadera hoodie cárdigan chaleco fleece"),
        categoria("ropa_interior", "Underwear: briefs, boxers, panties, slips, undershirts", corto="Underwear", aduana="Ropa interior",
                  grupo="Underwear and nightwear", dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=110, prioridad=30,
                  re_=r"\b(underwear|briefs?|boxers?|calzon(cillos?|es)?|panties|bragas?|bikinis? brief|thongs?|tangas?|slips?|enaguas?|"
                      r"camisetas? interiores?|undershirts?|ropa interior)\b", alias="ropa interior calzoncillo bóxer calzón braga tanga fondo"),
        categoria("ropa_dormir", "Pajamas, nightgown, bathrobe or dressing gown", corto="Nightwear", aduana="Ropa de dormir",
                  grupo="Underwear and nightwear", dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=120, prioridad=30,
                  re_=r"\b(pajamas?|pyjamas?|pijamas?|nightgowns?|camisones?|sleepwear|bathrobes?|batas?|robes?|dressing gowns?|loungewear)\b",
                  alias="pijama camisón bata albornoz"),
        categoria("brasier", "Bra, girdle, corset, braces or garters", corto="Bra or shapewear", aduana="Sostén", grupo="Underwear and nightwear",
                  dominio=DOM, capitulos=["62", "42", "39", "40", "43"], orden=130, prioridad=26,
                  re_=r"\b(bras?|brassieres?|brasier|sostenes?|sujetadores?|corpinos?|bralettes?|sports bras?|girdles?|fajas?|corsets?|corses?|"
                      r"suspenders|tirantes|garters?|ligas?|shapewear)\b", alias="brasier sostén top deportivo faja corsé tirantes",
                  plantilla={"material": "DE {fibra}", "requiere": ["fibra"], "como": {"fibra": {"cuero": "CUERO", "*": "TEXTIL"}}}),
        categoria("chandal", "Track suit (jacket and trousers for sport)", corto="Track suit", aduana="Conjunto deportivo", grupo="Sportswear",
                  dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=140, prioridad=27, re_=r"\b(track ?suits?|tracksuits?|chandal(es)?|pants? y chaqueta deportiv)\b",
                  alias="chándal pants deportivo conjunto deportivo"),
        categoria("ropa_esqui", "Ski suit or ski ensemble", corto="Ski suit", aduana="Ropa de esquí", grupo="Sportswear", dominio=DOM,
                  capitulos=["61", "62", "42", "39", "40", "43"], orden=150, prioridad=26, re_=r"\b(ski (suits?|overalls?|sets?)|traje de esqui|snow ?suits?)\b",
                  alias="traje de esquí"),
        categoria("traje_bano", "Swimwear: swimsuit, bikini, swim trunks", corto="Swimwear", aduana="Traje de baño", grupo="Sportswear", dominio=DOM,
                  capitulos=["61", "62", "42", "39", "40", "43"], orden=160, prioridad=25,
                  re_=r"\b(swim(wear|suits?| trunks| shorts)?|trajes? de bano|banadores?|bikinis?|board ?shorts?|boardshorts)\b",
                  alias="traje de baño bikini bañador"),
        categoria("prenda_otra", "Overall, jumpsuit, work coat, apron or other garment", corto="Other garment", aduana="Prenda de vestir",
                  grupo="Other garments", dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=170, prioridad=20,
                  re_=r"\b(jumpsuits?|enterizos?|monos?|rompers?|overoles?|coveralls?|boiler ?suits?|aprons?|delantales?|gabachas?|smocks?|"
                      r"lab coats?|scrubs?|uniform(es)?|leotards?|body ?suits?)\b", alias="enterizo mono overol gabacha delantal uniforme"),
        categoria("calcetines", "Socks, stockings, tights or pantyhose", corto="Socks", aduana="Calcetines", grupo="Hosiery", dominio=DOM,
                  capitulos=["61", "62", "42", "39", "40", "43"], orden=180, prioridad=38,
                  re_=r"\b(socks?|calcetines|calcetas?|medias?|stockings?|tights|pantyhose|pantimedias?|leotardos?|knee ?highs?)\b",
                  alias="calcetines calcetas medias pantimedias"),
        categoria("prenda_bebe", "Baby garment: bodysuit, romper, baby set, bib", corto="Baby garment", aduana="Prenda para bebé", grupo="Baby",
                  dominio=DOM, capitulos=["61", "62", "42", "39", "40", "43"], orden=190, prioridad=24,
                  re_=r"\b(onesies?|bodysuits? (para )?bebe|baby (set|bodysuit|romper|bib)|mamelucos?|peleles?|baberos?|bibs?|pañales? de tela)\b",
                  alias="body de bebé mameluco babero pañal de tela"),
    ]
    plantilla = {"material": "DE {fibra}", "requiere": ["fibra"], "como": {"fibra": {"cuero": "CUERO", "*": "TEXTIL"}},
                 "si": [{"cuando": [{"campo": "recubierta", "operador": "EQUAL", "valor": True}], "material": "DE SINTÉTICO"}]}
    for c in cats:
        c.setdefault("plantilla_aduana", plantilla)

    no_bebe = [cond("edad", "bebe", negado=True)]
    atrs = [
        atributo("materia_base", "Material of the garment", "select", [
            opcion("textil", "Textile (woven, knitted, felt or nonwoven)"),
            opcion("cuero", "Leather (natural or regenerated)", re_=r"\b(leather|cuero|piel de (res|vaca|cordero))\b", prioridad=5),
            opcion("plastico", "Plastic sheeting (not a fabric)", re_=r"\b(pvc raincoat|vinyl|plastic sheeting)\b", prioridad=6),
            opcion("caucho", "Vulcanized rubber (e.g. neoprene without fabric)", prioridad=7),
            opcion("peleteria", "Furskin or with fur parts beyond mere trimming", re_=r"\b(fur coat|abrigo de piel|mink|zorro)\b", prioridad=6)],
            ambitos(APAREL), defecto="textil", orden=5,
            ayuda="Garments of leather (42.03), plastics (39.26), rubber (40.15) or furskin (43.03) are excluded from chapters 61 and 62."),
        atributo("recubierta", "Fabric coated, covered or laminated with plastics or rubber visible to the naked eye", "boolean", [],
                 ambitos(TEXTILES, condicion=[cond("materia_base", "textil"), cond("tejido", ["punto", "plano"])] + no_bebe), defecto="false",
                 orden=12, patrones=[{"re": r"\b(pu coated|pvc coated|laminated|laminad[oa]|recubiert[oa]|coated|rubberi[sz]ed|engomad[oa])\b",
                                      "en": "todo"}],
                 texto={"frase": "RECUBIERTA CON PLÁSTICO O CAUCHO", "orden": 20},
                 ayuda="Fabrics of headings 59.03, 59.06 or 59.07 (chapter 61 Note 8, chapter 62 Note 5). A membrane between two fabrics that "
                       "is not visible, or a quilted padded fabric (58.11), does not count: the outer fabric decides."),
        atributo("tipo_interior", "Type of underwear", "select", [
            opcion("calzon", "Briefs, boxers, panties or thongs", re_=r"\b(briefs?|boxers?|calzon(cillos?|es)?|panties|bragas?|thongs?|tangas?)\b"),
            opcion("combinacion", "Slip or petticoat", re_=r"\b(slips?|petticoats?|enaguas?|fondos?|combinacion(es)?)\b"),
            opcion("camiseta_interior", "Undershirt or vest worn under clothes", re_=r"\b(undershirts?|camisetas? interiores?|vests?)\b")],
            ambitos(["ropa_interior"], "REQUIRE"), orden=40),
        atributo("tipo_dormir", "Type of nightwear", "select", [
            opcion("pijama", "Pajamas, nightdress or nightshirt", re_=r"\b(pajamas?|pyjamas?|pijamas?|nightgowns?|camisones?|nightshirts?)\b"),
            opcion("bata", "Bathrobe, dressing gown or house coat", re_=r"\b(bathrobes?|batas?|robes?|dressing gowns?|albornoz)\b")],
            ambitos(["ropa_dormir"], "REQUIRE"), orden=41),
        atributo("tipo_soporte", "Type of support garment", "select", [
            opcion("sosten", "Bra or brassiere (including sports bras and bralettes)", re_=r"\b(bras?|brassieres?|sostenes?|sujetadores?|bralettes?)\b"),
            opcion("faja", "Girdle or panty-girdle", re_=r"\b(girdles?|fajas?)\b"),
            opcion("faja_sosten", "Corselette (girdle and bra combined)", re_=r"\b(corselettes?|bodys? reductor)\b"),
            opcion("otro", "Corset, braces, suspenders, garters or similar", re_=r"\b(corsets?|suspenders|tirantes|garters?|ligas?)\b")],
            ambitos(["brasier"], "REQUIRE"), orden=42),
        atributo("tipo_calceteria", "Type of hosiery", "select", [
            opcion("calcetin", "Socks or ankle socks", re_=r"\b(socks?|calcetines|calcetas?)\b", defecto=True),
            opcion("pantimedia", "Tights or pantyhose", re_=r"\b(tights|pantyhose|pantimedias?|leotardos?)\b"),
            opcion("media", "Women's stockings or knee-highs", re_=r"\b(stockings?|knee ?highs?|medias?)\b"),
            opcion("compresion", "Graduated compression (e.g. for varicose veins)", re_=r"\b(compression|compresion|varices)\b")],
            ambitos(["calcetines"], "REQUIRE"), orden=43),
        atributo("titulo_fino", "Sheer: synthetic single yarn under 67 decitex", "boolean", [],
                 ambitos(["calcetines"], condicion=[cond("tipo_calceteria", ["pantimedia", "media"])]), defecto="false", orden=44,
                 ayuda="Subheadings 6115.21 and 6115.30: measured per single yarn."),
        atributo("ajuste_bajo", "Elastic, drawstring or ribbed waistband at the bottom hem", "boolean", [],
                 ambitos(["camisa", "camiseta"], condicion=[cond("tejido", "punto")]), defecto="false", orden=46,
                 ayuda="Chapter 61 Notes 4 and 5: shirts, blouses and T-shirts cannot have any means of tightening at the bottom."),
        atributo("sin_mangas", "Sleeveless", "boolean", [], ambitos(["camisa"], condicion=[cond("tejido", "punto")]), defecto="false", orden=47,
                 ayuda="Chapter 61 Note 4: heading 61.05 does not cover sleeveless garments."),
    ]
    comunes = {
        "tejido": ambitos([c for c in APAREL if c != "brasier"], "REQUIRE", condicion=[cond("materia_base", "textil")]),
        "comp.exterior": ambitos(APAREL, "REQUIRE"),
        "comp.forro": ambitos(["chaqueta", "saco", "traje", "vestido", "falda", "pantalon"]),
        "comp.relleno": ambitos(["chaqueta"]),
        "fibra": ambitos(APAREL),
        "genero": ambitos([c for c in APAREL if c not in ("camiseta", "ropa_esqui")], "REQUIRE",
                          condicion=[cond("materia_base", "textil")] + no_bebe),
        "edad": ambitos(APAREL),
        # Datos que piden algunos aranceles nacionales (no cambian la subpartida)
        "usoPrevisto": ambitos(APAREL),
        "manga": ambitos(["camisa", "camiseta", "sueter", "vestido", "chaqueta", "prenda_bebe"]),
        "largo": ambitos(["pantalon", "chandal", "prenda_bebe"]),
        "peto": ambitos(["pantalon"]),
        "mezclilla": ambitos(["pantalon", "chaqueta", "falda", "vestido", "camisa"]),
        "conCuello": ambitos(["camisa", "camiseta", "sueter"]),
        "capucha": ambitos(["chaqueta", "sueter", "chandal"]),
    }
    reglas = []
    for cat in APAREL:
        reglas += reglas_comunes(cat)
    for cat, tabla in PARTIDAS.items():
        reglas += reglas_textil(cat, tabla, {}, "", next(c["nombre_corto"] for c in cats if c["codigo"] == cat))
    for cat, (attr, tipos) in POR_TIPO.items():
        for valor, tabla in tipos.items():
            reglas += reglas_textil(cat, tabla, {attr: valor}, valor[:3].upper(), f"{next(c['nombre_corto'] for c in cats if c['codigo'] == cat)} "
                                                                                    f"({valor})")
    reglas += [
        regla("R-NE-ROP-BRASIER-10", "brasier", si(materia_base="textil", tipo_soporte="sosten"), ["621210"],
              "Brassieres, knitted or not → 6212.10"),
        regla("R-NE-ROP-BRASIER-20", "brasier", si(materia_base="textil", tipo_soporte="faja"), ["621220"], "Girdles and panty-girdles → 6212.20"),
        regla("R-NE-ROP-BRASIER-30", "brasier", si(materia_base="textil", tipo_soporte="faja_sosten"), ["621230"], "Corselettes → 6212.30"),
        regla("R-NE-ROP-BRASIER-90", "brasier", si(materia_base="textil", tipo_soporte="otro"), ["621290"],
              "Corsets, braces, suspenders, garters → 6212.90"),
        # Calcetería (61.15); la que no es de punto, 62.17
        regla("R-NE-ROP-CALCET-CAL", "calcetines", si(materia_base="textil", edad_no="bebe", tejido="punto", tipo_calceteria="calcetin"),
              efecto="Knitted socks → 6115.9x by the predominant fiber", **_accion("61159")),
        regla("R-NE-ROP-CALCET-PANF", "calcetines", si(materia_base="textil", edad_no="bebe", tejido="punto", tipo_calceteria="pantimedia",
                                                        titulo_fino=True, fibra="sintetica"), ["611521"],
              "Tights of synthetic fibers under 67 decitex per single yarn → 6115.21"),
        regla("R-NE-ROP-CALCET-PANG", "calcetines", si(materia_base="textil", edad_no="bebe", tejido="punto", tipo_calceteria="pantimedia",
                                                        titulo_fino=False, fibra="sintetica"), ["611522"],
              "Tights of synthetic fibers of 67 decitex or more → 6115.22"),
        regla("R-NE-ROP-CALCET-PANO", "calcetines", si(materia_base="textil", edad_no="bebe", tejido="punto", tipo_calceteria="pantimedia",
                                                        fibra_no="sintetica"), ["611529"], "Tights of other textile materials → 6115.29"),
        regla("R-NE-ROP-CALCET-MEDF", "calcetines", si(materia_base="textil", edad_no="bebe", tejido="punto", tipo_calceteria="media",
                                                        titulo_fino=True), ["611530"],
              "Women's full-length or knee-length hosiery under 67 decitex → 6115.30"),
        regla("R-NE-ROP-CALCET-MEDG", "calcetines", si(materia_base="textil", edad_no="bebe", tejido="punto", tipo_calceteria="media",
                                                        titulo_fino=False), efecto="Other knitted stockings → 6115.9x by fiber", **_accion("61159")),
        regla("R-NE-ROP-CALCET-COMP", "calcetines", si(materia_base="textil", edad_no="bebe", tejido="punto", tipo_calceteria="compresion"),
              ["611510"], "Graduated compression hosiery → 6115.10"),
        regla("R-NE-ROP-CALCET-PLANO", "calcetines", si(materia_base="textil", edad_no="bebe", tejido=["plano", "no_tejido"]), ["621710"],
              "Socks that are not knitted → 6217.10 (heading 62.17, item 12)"),
        # Exclusiones que la nota obliga a revisar
        regla("R-NE-ROP-CAMISA-AJUSTE", "camisa", si(tejido="punto", ajuste_bajo=True), tipo="REVIEW",
              efecto="A knitted shirt with a tightening at the bottom is not 61.05/61.06 (chapter 61 Note 4): it goes as a jacket "
                     "(61.01/61.02) or a sweater (61.10)."),
        regla("R-NE-ROP-CAMISA-SINMANGA", "camisa", si(tejido="punto", genero=M, sin_mangas=True), tipo="REVIEW",
              efecto="Heading 61.05 does not cover sleeveless garments (chapter 61 Note 4): it goes in 61.09, 61.10 or 61.14."),
        regla("R-NE-ROP-CAMISETA-AJUSTE", "camiseta", si(tejido="punto", ajuste_bajo=True), tipo="REVIEW",
              efecto="A T-shirt with a ribbed waistband, drawstring or other tightening at the bottom is not 61.09 (chapter 61 Note 5): "
                     "it goes in 61.10."),
    ]
    casos = [
        caso("camiseta", "610910", **{"comp.exterior": "100% cotton"}, tejido="punto"),
        caso("camiseta", "610990", **{"comp.exterior": "60% polyester 40% cotton"}, tejido="punto"),
        caso("chaqueta", "620140", **{"comp.exterior": "100% nylon"}, tejido="plano", genero="M", recubierta=False),
        caso("chaqueta", "620240", **{"comp.exterior": "100% polyester"}, tejido="plano", genero="U", recubierta=False),
        caso("chaqueta", "621020", **{"comp.exterior": "100% nylon"}, tejido="plano", genero="M", recubierta=True),
        caso("chaqueta", "611300", **{"comp.exterior": "100% polyester"}, tejido="punto", genero="F", recubierta=True),
        caso("chaqueta", "610190", **{"comp.exterior": "100% wool"}, tejido="punto", genero="M", recubierta=False),
        caso("sueter", "611020", **{"comp.exterior": "80% cotton 20% polyester"}, tejido="punto", genero="M", recubierta=False),
        caso("sueter", "611030", **{"comp.exterior": "100% polyester fleece"}, tejido="punto", genero="F", recubierta=False),
        caso("pantalon", "620342", **{"comp.exterior": "98% cotton 2% elastane"}, tejido="plano", genero="M", recubierta=False),
        caso("pantalon", "620462", **{"comp.exterior": "100% cotton denim"}, tejido="plano", genero="F", recubierta=False),
        caso("pantalon", "610463", **{"comp.exterior": "88% polyester 12% elastane"}, tejido="punto", genero="F", recubierta=False),
        caso("camisa", "620520", **{"comp.exterior": "100% cotton"}, tejido="plano", genero="M", recubierta=False),
        caso("camisa", "610610", **{"comp.exterior": "100% cotton"}, tejido="punto", genero="F", recubierta=False),
        caso("camisa", "620610", **{"comp.exterior": "100% silk"}, tejido="plano", genero="F", recubierta=False),
        caso("vestido", "620444", **{"comp.exterior": "100% viscose"}, tejido="plano", recubierta=False),
        caso("falda", "610453", **{"comp.exterior": "95% polyester 5% elastane"}, tejido="punto", recubierta=False),
        caso("prenda_bebe", "611120", **{"comp.exterior": "100% cotton"}, tejido="punto"),
        caso("camiseta", "611130", **{"comp.exterior": "100% polyester"}, tejido="punto", edad="bebe"),
        caso("pantalon", "620920", **{"comp.exterior": "100% cotton"}, tejido="plano", edad="bebe"),
        caso("ropa_interior", "610711", **{"comp.exterior": "95% cotton 5% elastane"}, tejido="punto", genero="M", tipo_interior="calzon",
             recubierta=False),
        caso("ropa_interior", "610822", **{"comp.exterior": "90% nylon 10% elastane"}, tejido="punto", genero="F", tipo_interior="calzon",
             recubierta=False),
        caso("ropa_dormir", "620821", **{"comp.exterior": "100% cotton"}, tejido="plano", genero="F", tipo_dormir="pijama", recubierta=False),
        caso("brasier", "621210", **{"comp.exterior": "80% nylon 20% elastane"}, tipo_soporte="sosten"),
        caso("traje_bano", "611241", **{"comp.exterior": "82% nylon 18% elastane"}, tejido="punto", genero="F", recubierta=False),
        caso("traje_bano", "621111", **{"comp.exterior": "100% polyester"}, tejido="plano", genero="M", recubierta=False),
        caso("calcetines", "611595", **{"comp.exterior": "80% cotton 18% polyester 2% elastane"}, tejido="punto", tipo_calceteria="calcetin"),
        caso("calcetines", "611521", **{"comp.exterior": "100% nylon"}, tejido="punto", tipo_calceteria="pantimedia", titulo_fino=True),
        caso("chandal", "611212", **{"comp.exterior": "100% polyester"}, tejido="punto", recubierta=False),
        caso("prenda_otra", "621143", **{"comp.exterior": "65% polyester 35% cotton"}, tejido="plano", genero="F", recubierta=False),
        caso("chaqueta", "420310", **{"comp.exterior": "100% leather"}, materia_base="cuero"),
        caso("traje", "620311", **{"comp.exterior": "100% wool"}, tejido="plano", genero="M", recubierta=False),
        caso("conjunto", "610422", **{"comp.exterior": "100% cotton"}, tejido="punto", genero="F", recubierta=False),
        caso("saco", "620333", **{"comp.exterior": "100% polyester"}, tejido="plano", genero="M", recubierta=False),
        caso("chaqueta", "621010", **{"comp.exterior": "100% polypropylene"}, tejido="no_tejido", genero="M"),
    ]
    return {"dominio": {"codigo": DOM, "nombre": "Apparel", "orden": 20,
                        "descripcion": "Garments of chapters 61 (knitted) and 62 (not knitted); leather, plastic, rubber and fur garments by their material.",
                        "capitulos": [{"capitulo": "61", "relevancia": "PRIMARY"}, {"capitulo": "62", "relevancia": "PRIMARY"},
                                      {"capitulo": "42", "relevancia": "SECONDARY"}, {"capitulo": "39", "relevancia": "SECONDARY"},
                                      {"capitulo": "40", "relevancia": "SECONDARY"}, {"capitulo": "43", "relevancia": "SECONDARY"}]},
            "fuente": NE, "categorias": cats, "atributos": atrs, "ambitos_comunes": comunes, "reglas": reglas, "casos": casos}
