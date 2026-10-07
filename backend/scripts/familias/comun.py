"""Lo que comparten las familias: composición por partes, lo que se lee de ella
(fibra que predomina en peso, Nota 2 de la Sección XI; materia de corte y
suela, Nota 4 del capítulo 64; clase de material), para quién es la prenda y
las palabras aduaneras de cada clase de material."""
from base import atributo, bloqueo, opcion

CLASES_MATERIAL = [
    {"codigo": "textil", "nombre": "Textile", "texto_aduana": "TEXTIL"},
    {"codigo": "cuero", "nombre": "Leather", "texto_aduana": "CUERO"},
    {"codigo": "plastico", "nombre": "Rubber or plastics", "texto_aduana": "SINTÉTICO"},
    {"codigo": "metal", "nombre": "Metal", "texto_aduana": "METAL"},
    {"codigo": "madera", "nombre": "Wood or cork", "texto_aduana": "MADERA"},
    {"codigo": "papel", "nombre": "Paper or paperboard", "texto_aduana": "PAPEL O CARTÓN"},
    {"codigo": "vidrio", "nombre": "Glass", "texto_aduana": "VIDRIO"},
    {"codigo": "paja", "nombre": "Straw or plaiting material", "texto_aduana": "PAJA"},
    {"codigo": "otro", "nombre": "Other material", "texto_aduana": "OTRAS MATERIAS"},
]
VOCABULARIO = {"sintetica": "SINTÉTICO", "artificial": "SINTÉTICO", "caucho": "SINTÉTICO"}

MATERIALES_TEXTILES = [("cotton", "Cotton"), ("polyester", "Polyester"), ("elastane", "Elastane"), ("nylon", "Nylon"), ("viscose", "Viscose"),
                       ("wool", "Wool"), ("acrylic", "Acrylic"), ("linen", "Linen"), ("modal", "Modal"), ("polyamide", "Polyamide"),
                       ("silk", "Silk"), ("leather", "Leather")]


def _comp(codigo, etiqueta, ayuda, materiales, orden):
    return atributo(codigo, etiqueta, "composition", [opcion(c, e) for c, e in materiales], seccion="composicion", ayuda=ayuda, orden=orden)


def atributos() -> list[dict]:
    """Atributos compartidos: cada familia dice en qué categorías aplican (ámbitos)."""
    fibra = [opcion("lana", "Wool or fine animal hair"), opcion("seda", "Silk"), opcion("algodon", "Cotton"),
             opcion("vegetal", "Other vegetable fiber (linen, hemp, ramie)"), opcion("sintetica", "Synthetic fiber"),
             opcion("artificial", "Artificial fiber"), opcion("cuero", "Leather"), opcion("otra", "Unidentified material")]
    nino = {"campo": "edad", "operador": "EQUAL", "valor": "nino"}
    adulto = {"campo": "edad", "operador": "IN", "valor": ["adulto", ""]}
    return [
        _comp("comp.exterior", "Outer fabric or surface", "E.g. 100% polyester, or shell: 100% nylon", MATERIALES_TEXTILES, 620),
        _comp("comp.forro", "Lining", "Only informative: the lining does not change the code", MATERIALES_TEXTILES, 630),
        _comp("comp.relleno", "Filling or padding", "E.g. 90% down 10% feathers, or polyester wadding", [("down", "Down"), ("feathers", "Feathers"),
                                                                                                        ("polyester", "Polyester")], 640),
        _comp("comp.corte", "Upper", "Materials of the upper with their share of the outer surface, e.g. 60% leather 40% textile. "
                                     "Trims, reinforcements and the lining do not count; the tongue does.",
              [("leather", "Leather"), ("suede", "Suede"), ("nubuck", "Nubuck"), ("canvas", "Canvas"), ("mesh", "Mesh"), ("textile", "Textile"),
               ("knit", "Knit"), ("synthetic", "Synthetic leather (PU)"), ("pvc", "PVC"), ("rubber", "Rubber"), ("eva", "EVA")], 650),
        _comp("comp.suela", "Outer sole", "Materials of the part that touches the ground, e.g. 100% rubber, or EVA and rubber",
              [("rubber", "Rubber"), ("eva", "EVA"), ("tpr", "TPR"), ("pu", "PU"), ("tpu", "TPU"), ("pvc", "PVC"), ("leather", "Leather"),
               ("cork", "Cork"), ("wood", "Wood"), ("jute", "Jute"), ("textile", "Textile")], 660),
        _comp("comp.material", "Main material", "E.g. leather, stainless steel, nylon, cotton canvas",
              [("leather", "Leather"), ("synthetic", "Synthetic leather (PU)"), ("polyester", "Polyester"), ("nylon", "Nylon"),
               ("cotton", "Cotton"), ("canvas", "Canvas"), ("plastic", "Plastic"), ("rubber", "Rubber"), ("metal", "Metal"),
               ("stainless steel", "Stainless steel"), ("zinc alloy", "Zinc alloy"), ("wood", "Wood"), ("paper", "Paper"), ("straw", "Straw")], 680),
        atributo("fibra", "Fiber that predominates by weight in the outer fabric", "select", fibra, seccion="derivado",
                 derivacion={"modo": "fibra", "parte": "exterior", "respaldo": ["comp.material", "composicion", "texto%"]}, orden=590,
                 ayuda="Section XI, Note 2: the textile material that predominates by weight over each of the others."),
        atributo("material", "Material class", "select",
                 [opcion("textil", "Textile"), opcion("cuero", "Leather"), opcion("plastico", "Rubber or plastics"), opcion("metal", "Metal"),
                  opcion("madera", "Wood or cork"), opcion("papel", "Paper or paperboard"), opcion("vidrio", "Glass"),
                  opcion("paja", "Straw or plaiting material"), opcion("otro", "Other material")],
                 seccion="derivado", derivacion={"modo": "clase", "parte": "material",
                                                 "mapa": {k: k for k in ("textil", "cuero", "plastico", "metal", "madera", "papel", "vidrio", "paja",
                                                                         "otro")}}, orden=600),
        atributo("tejido", "Fabric construction", "select", [
            opcion("punto", "Knitted or crocheted", texto={"frase": "DE PUNTO", "orden": 10},
                   re_=r"\b(knit|knitted|tejid[oa] de punto|punto|jersey|pique|fleece|polar|terry|rib|interlock|french terry|hoodies?|"
                       r"sweatshirts?|leggings?|t-?shirts?|tees?|polos?|socks?)\b", prioridad=3),
            opcion("plano", "Woven", texto={"frase": "DE TEJIDO PLANO", "orden": 10},
                   re_=r"\b(woven|tejido plano|denim|mezclilla|jeans?|poplin|popelina|oxford|twill|sarga|canvas|lona|chambray|flannel|franela|"
                       r"ripstop|taffeta|tafetan|chiffon|gasa|corduroy|pana|linen shirt)\b", prioridad=2,
                   bloqueo=[bloqueo("A T-shirt is knitted; a woven top is a shirt or blouse.", categoria="camiseta")]),
            opcion("no_tejido", "Felt or nonwoven", texto={"frase": "DE TELA SIN TEJER", "orden": 10},
                   re_=r"\b(nonwoven|non-woven|tela sin tejer|tnt|felt|fieltro|disposable)\b", prioridad=4)],
            [], orden=10,
            ayuda="Knitted (chapter 61) or not knitted (chapter 62). Look at the fabric: knitted fabric is made of interlocking loops."),
        atributo("genero", "For men or for women", "select", [
            opcion("M", "Men or boys", re_=r"\b(mens?|men's|hombres?|caballeros?|boys?|ninos?|male|masculino)\b", prioridad=4,
                   texto=[{"frase": "PARA NIÑO", "orden": 1000, "cuando": [nino]}, {"frase": "PARA HOMBRE", "orden": 1000, "cuando": [adulto]}]),
            opcion("F", "Women or girls", re_=r"\b(womens?|women's|ladies|mujer(es)?|damas?|girls?|ninas?|female|femenin[oa])\b", prioridad=4,
                   texto=[{"frase": "PARA NIÑA", "orden": 1000, "cuando": [nino]}, {"frase": "PARA MUJER", "orden": 1000, "cuando": [adulto]}]),
            opcion("U", "Unisex or not identifiable (classified as women's)", re_=r"\b(unisex)\b", prioridad=3,
                   texto={"frase": "UNISEX", "orden": 1000}),
        ], seccion="producto", orden=30,
            derivacion={"modo": "constante", "valor": "F", "cuando": [{"campo": "categoria", "operador": "IN", "valor": ["falda", "vestido", "brasier"]}],
                        "motivo": "categoria"},
            ayuda="Chapter 61 Note 9 and chapter 62 Note 8: closing left over right is men's, right over left is women's; "
                  "what cannot be identified is classified with women's garments."),
        atributo("edad", "Who it is for", "select", [
            opcion("adulto", "Adult"),
            opcion("nino", "Child or youth", re_=r"\b(kids?|youth|juvenil|ninos?|ninas?|infantil|toddler|boys?|girls?)\b", prioridad=5),
            opcion("bebe", "Baby (up to 86 cm tall)", re_=r"\b(baby|bebes?|infant|newborn|recien nacido|onesies?|bodys?|\d{1,2}\s?m(onths)?|meses)\b",
                   prioridad=2, texto={"frase": "PARA BEBÉ", "orden": 1000}),
        ], seccion="producto", defecto="adulto", orden=20,
            derivacion={"modo": "constante", "valor": "bebe", "cuando": [{"campo": "categoria", "operador": "EQUAL", "valor": "prenda_bebe"}],
                        "motivo": "categoria"},
            ayuda="Baby garments are for children up to 86 cm tall (chapter 61 Note 6, chapter 62 Note 4)."),
    ]
