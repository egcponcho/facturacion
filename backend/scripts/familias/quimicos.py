"""Químicos: capítulos 28, 29, 32, 34, 35 y 38 (y 27.10, 27.12 o 22.07 cuando
las notas lo mandan) según sus Notas Explicativas.

- Nota 1 de los capítulos 28 y 29: solo los elementos y compuestos de
  constitución química definida presentados aisladamente, incluso con
  impurezas, en disolución acuosa, en otro disolvente solo por seguridad o
  transporte, o con un estabilizante, antipolvo o colorante para identificarlos.
  Una mezcla o preparación va por su función (capítulos 32, 34, 35, 38).
- Nota 3 del 29: lo que puede ir en dos partidas va en la última.
- Nota 2 del 29: el alcohol etílico (22.07), el metano y propano (27.11) y la
  urea (31) no son del 29.
- 32.08/32.09: el polímero de la pintura disperso o disuelto en disolvente
  orgánico (32.08) o en agua (32.09); Nota 4: una disolución de polímeros de
  39.01–39.13 con más de 50 % de disolvente orgánico es 32.08.
- Nota 3 del 34: la definición de agente de superficie orgánico.
- 34.03: con 70 % o más de aceite de petróleo es aceite de la 27.10.
- 35.06: acondicionados para la venta al por menor de peso neto ≤ 1 kg, 35.06.10.
Dentro de la partida, la subpartida la busca el motor en el texto oficial con
el nombre químico, el CAS y la función.
"""
from base import ambitos, atributo, caso, categoria, cond, opcion, partidas, regla, si

DOM = "CHEMICALS"
NE = "Explanatory Notes, chapters 28, 29, 32, 34, 35 and 38"

GRUPOS_INORG = {
    "elemento": ("Element (sulfur, carbon black, gases, metalloids, alkali metals)", partidas("2801", "2805")),
    "acido": ("Inorganic acid or oxygen compound of non-metals", partidas("2806", "2811")),
    "halogenuro": ("Halide or sulfide of non-metals", partidas("2812", "2813")),
    "base_oxido": ("Base or metal oxide/hydroxide (ammonia, caustic soda, zinc oxide)", partidas("2814", "2825")),
    "sal": ("Salt of an inorganic acid or of a metal (chlorides, sulfates, carbonates, silicates)", partidas("2826", "2842")),
    "otro": ("Other (precious metal compounds, rare earths, peroxide, carbides)", partidas("2843", "2853")),
}
GRUPOS_ORG = {
    "hidrocarburo": ("Hydrocarbon or its halogenated, sulfonated or nitrated derivative (toluene, xylene)", partidas("2901", "2904")),
    "alcohol": ("Alcohol (methanol, isopropanol, glycols, glycerol)", partidas("2905", "2906")),
    "fenol": ("Phenol or phenol-alcohol", partidas("2907", "2908")),
    "eter": ("Ether, peroxide, epoxide or acetal", partidas("2909", "2911")),
    "aldehido": ("Aldehyde (formaldehyde)", partidas("2912", "2913")),
    "cetona": ("Ketone or quinone (acetone, MEK)", partidas("2914", "2914")),
    "acido": ("Carboxylic acid, anhydride or ester (acetic acid, ethyl acetate, phthalates)", partidas("2915", "2918")),
    "ester_inorg": ("Ester of an inorganic acid (phosphates, carbonates)", partidas("2919", "2920")),
    "amina": ("Amine or amino compound", partidas("2921", "2922")),
    "nitrogenado": ("Amide, imide, nitrile, isocyanate or other nitrogen compound", partidas("2923", "2929")),
    "organo_inorg": ("Organo-sulfur or other organo-inorganic compound", partidas("2930", "2931")),
    "heterociclico": ("Heterocyclic compound", partidas("2932", "2935")),
    "otro": ("Vitamin, hormone, sugar, antibiotic or other", partidas("2936", "2942")),
}


def familia() -> dict:
    g = "Chemicals"
    cats = [
        categoria("quimico_inorganico", "Inorganic chemical: acid, base, salt, oxide or element", corto="Inorganic chemical",
                  aduana="Producto químico inorgánico", grupo=g, dominio=DOM, capitulos=["28"], orden=10, prioridad=40,
                  re_=r"\b(inorganic|inorganic[oa]|acid[oe]s? (sulfuric|hydrochloric|nitric|phosphoric|sulfurico|clorhidrico|nitrico|fosforico)|"
                      r"sodium hydroxide|hidroxido de sodio|caustic soda|soda caustica|zinc oxide|oxido de zinc|silica gel|titanium dioxide|"
                      r"chlorides?|cloruros?|sulfates?|sulfatos?|carbonates?|carbonatos?|nitrates?|nitratos?|hydroxides?|hidroxidos?)\b",
                  alias="ácido base sal óxido hidróxido cloruro sulfato carbonato", terminos="inorgánicos"),
        categoria("quimico_organico", "Organic chemical (single compound): solvent, alcohol, acid, ester, amine", corto="Organic chemical",
                  aduana="Producto químico orgánico", grupo=g, dominio=DOM, capitulos=["29"], orden=20, prioridad=40,
                  re_=r"\b(organic chemical|acetone|acetona|toluene|tolueno|xylene|xileno|methanol|metanol|isopropanol|isopropyl alcohol|"
                      r"alcohol isopropilico|ethyl acetate|acetato de etilo|butyl acetate|acetato de butilo|mek|methyl ethyl ketone|glycol|glicol|"
                      r"glycerol|glicerina|formaldehyde|formaldehido|acetic acid|acido acetico|citric acid|acido citrico|amines?|aminas?)\b",
                  alias="acetona tolueno metanol alcohol isopropílico acetato glicol", terminos="orgánicos"),
        categoria("colorante", "Dye or colorant", corto="Dye", aduana="Colorante", grupo=g, dominio=DOM, capitulos=["32"], orden=30, prioridad=38,
                  re_=r"\b(dyes?|dyestuffs?|colorantes?|tintes?|tinturas?|disperse|reactive dye|acid dye|vat dye|indigo|anilinas?)\b",
                  alias="colorante tinte anilina", terminos="colorantes"),
        categoria("pigmento", "Pigment or pigment preparation", corto="Pigment", aduana="Pigmento", grupo=g, dominio=DOM, capitulos=["32"], orden=40,
                  prioridad=37, re_=r"\b(pigments?|pigmentos?|masterbatch|pastas? pigmentarias?|color pastes?)\b", alias="pigmento masterbatch",
                  terminos="pigmentos"),
        categoria("pintura", "Paint, varnish, lacquer or leather finish", corto="Paint or varnish", aduana="Pintura", grupo=g, dominio=DOM,
                  capitulos=["32"], orden=50, prioridad=37,
                  re_=r"\b(paints?|pinturas?|varnish(es)?|barnices?|barniz|lacquers?|lacas?|coatings?|recubrimientos?|primers?|enamels?|esmaltes?|"
                      r"leather finish)\b", alias="pintura barniz laca esmalte", terminos="pinturas barnices"),
        categoria("tinta", "Printing or writing ink", corto="Ink", aduana="Tinta", grupo=g, dominio=DOM, capitulos=["32"], orden=60, prioridad=36,
                  re_=r"\b(inks?|tintas?|screen printing ink|plastisol|serigrafia)\b", alias="tinta serigrafía plastisol", terminos="tintas"),
        categoria("adhesivo", "Glue or adhesive", corto="Adhesive", aduana="Adhesivo", grupo=g, dominio=DOM, capitulos=["35"], orden=70, prioridad=39,
                  re_=r"\b(adhesives?|adhesivos?|glues?|pegamentos?|colas?|cements? de contacto|contact cement|hot ?melt|primers? (para )?(suela|sole))\b",
                  alias="adhesivo pegamento cola cemento de contacto hot melt", terminos="adhesivos colas"),
        categoria("tensoactivo", "Surfactant, detergent or washing preparation", corto="Detergent or surfactant", aduana="Detergente",
                  grupo=g, dominio=DOM, capitulos=["34"], orden=80, prioridad=35,
                  re_=r"\b(surfactants?|tensoactivos?|detergents?|detergentes?|wetting agents?|humectantes?|emulsifiers?|emulsionantes?|"
                      r"cleaners?|limpiadores?|desengrasantes?|degreasers?)\b", alias="detergente tensoactivo limpiador", terminos="tensoactivos"),
        categoria("jabon", "Soap", corto="Soap", aduana="Jabón", grupo=g, dominio=DOM, capitulos=["34"], orden=90, prioridad=34,
                  re_=r"\b(soaps?|jabon(es)?|hand ?wash)\b", alias="jabón", terminos="jabón"),
        categoria("lubricante", "Lubricant, release agent or anti-rust preparation", corto="Lubricant", aduana="Lubricante", grupo=g, dominio=DOM,
                  capitulos=["34", "27"], orden=100, prioridad=34,
                  re_=r"\b(lubricants?|lubricantes?|greases?|grasas? lubricantes?|release agents?|desmoldantes?|anti-?rust|antioxidante de metal|"
                      r"cutting oils?|aceites? de corte|silicone spray)\b", alias="lubricante grasa desmoldante", terminos="lubricantes"),
        categoria("cera", "Wax: prepared, artificial or paraffin", corto="Wax", aduana="Cera", grupo=g, dominio=DOM, capitulos=["34", "27"], orden=110,
                  prioridad=33, re_=r"\b(wax(es)?|ceras?|parafinas?|paraffin)\b", alias="cera parafina", terminos="ceras"),
        categoria("betun", "Polish or cream for footwear or leather; scouring paste", corto="Shoe polish", aduana="Betún", grupo=g, dominio=DOM,
                  capitulos=["34"], orden=120, prioridad=36,
                  re_=r"\b(shoe (polish|cream|care)|betun(es)?|crema para (calzado|zapatos)|leather (cream|conditioner|polish)|polishes?|"
                      r"abrillantadores?|lustres?|suede cleaner)\b", alias="betún crema para calzado limpiador de cuero", terminos="betunes cremas calzado"),
        categoria("apresto", "Finishing agent, dye fixer or carrier for textiles, paper or leather", corto="Finishing agent", aduana="Apresto",
                  grupo=g, dominio=DOM, capitulos=["38"], orden=130, prioridad=33,
                  re_=r"\b(finishing agents?|aprestos?|softeners?|suavizantes? textiles?|dye fixing|fijadores?|leveling agents?|igualadores?|"
                      r"waterproofing agents?|repelentes? de agua|dwr|mordants?|mordientes?)\b", alias="apresto suavizante fijador repelente",
                  terminos="aprestos acabado"),
        categoria("aditivo_polimero", "Rubber accelerator, plasticizer, antioxidant or stabilizer", corto="Rubber or plastic additive",
                  aduana="Aditivo para caucho o plástico", grupo=g, dominio=DOM, capitulos=["38"], orden=140, prioridad=32,
                  re_=r"\b(accelerators?|aceleradores?|plasticizers?|plastificantes?|antioxidants?|antioxidantes?|stabilizers?|estabilizantes?|"
                      r"vulcaniz\w+)\b", alias="acelerante plastificante antioxidante estabilizador", terminos="aceleradores plastificantes"),
        categoria("disolvente", "Solvent or thinner (mixture); paint remover", corto="Solvent or thinner", aduana="Disolvente", grupo=g, dominio=DOM,
                  capitulos=["38", "29"], orden=150, prioridad=34,
                  re_=r"\b(solvents?|disolventes?|solventes?|thinners?|diluyentes?|adelgazadores?|paint removers?|removedores?)\b",
                  alias="disolvente thinner diluyente", terminos="disolventes diluyentes"),
        categoria("biocida", "Disinfectant, insecticide, fungicide or similar", corto="Disinfectant or biocide", aduana="Desinfectante", grupo=g,
                  dominio=DOM, capitulos=["38"], orden=160, prioridad=33,
                  re_=r"\b(disinfectants?|desinfectantes?|insecticides?|insecticidas?|fungicides?|fungicidas?|antimicrobial|antimicrobianos?|"
                      r"biocides?|biocidas?|anti-?mold|antimoho)\b", alias="desinfectante insecticida fungicida antimicrobiano", terminos="desinfectantes"),
        categoria("reactivo", "Laboratory or diagnostic reagent", corto="Reagent", aduana="Reactivo de laboratorio", grupo=g, dominio=DOM,
                  capitulos=["38"], orden=170, prioridad=31, re_=r"\b(reagents?|reactivos?|buffer solutions?|test kits?|standards? de laboratorio)\b",
                  alias="reactivo de laboratorio", terminos="reactivos"),
        categoria("preparacion_quimica", "Other chemical preparation", corto="Chemical preparation", aduana="Preparación química", grupo=g,
                  dominio=DOM, capitulos=["38"], orden=180, prioridad=10, re_=r"\b(chemical preparations?|preparaciones? quimicas?|compound|blend)\b",
                  alias="preparación química", terminos="preparaciones químicas"),
    ]
    funcion = ["colorante", "pigmento", "pintura", "tinta", "adhesivo", "tensoactivo", "jabon", "lubricante", "cera", "betun", "apresto",
               "aditivo_polimero", "disolvente", "biocida", "reactivo", "preparacion_quimica"]
    todas = [c["codigo"] for c in cats]
    atrs = [
        atributo("nombre_quimico", "Chemical or technical name", "text", [], ambitos(todas), orden=10,
                 ayuda="As in the safety data sheet (SDS). It is used to find the subheading in the official text."),
        atributo("cas", "CAS number", "text", [], ambitos(todas), orden=11, ayuda="Optional, from the SDS, e.g. 67-64-1."),
        atributo("componentes", "Composition (component, CAS and %)", "text", [], ambitos(funcion), orden=12, informativo=True,
                 ayuda="One component per line, from the SDS."),
        atributo("estado_fisico", "Physical state", "select", [opcion("liquido", "Liquid"), opcion("solido", "Solid"), opcion("polvo", "Powder"),
                                                               opcion("pasta", "Paste or gel"), opcion("gas", "Gas")], ambitos(todas), orden=13,
                 informativo=True),
        atributo("definido", "Single chemically defined compound", "boolean", [], ambitos(["quimico_inorganico", "quimico_organico", "disolvente",
                                                                                              "aditivo_polimero"], "REQUIRE"),
                 defecto="true", orden=20,
                 ayuda="Notes 1 to chapters 28 and 29: one compound with one formula, even with impurities, in water solution, or with a "
                       "stabilizer added only for safety or transport. A mixture or preparation is classified by its function."),
        atributo("grupo_inorganico", "Kind of inorganic compound", "select",
                 [opcion(k, v[0], terminos=None) for k, v in GRUPOS_INORG.items()],
                 ambitos(["quimico_inorganico"], "REQUIRE", condicion=[cond("definido", True)]), orden=21),
        atributo("grupo_organico", "Functional group", "select", [opcion(k, v[0]) for k, v in GRUPOS_ORG.items()],
                 ambitos(["quimico_organico", "disolvente"], "REQUIRE", condicion=[cond("definido", True)]), orden=22,
                 ayuda="Chapter 29 Note 3: a compound that fits two headings goes in the one that comes last."),
        atributo("clase_colorante", "Kind of dye", "select", [
            opcion("dispersos", "Disperse dyes (polyester)", terminos="dispersos", re_=r"\bdisperse\b"),
            opcion("acidos", "Acid or mordant dyes (wool, nylon, leather)", terminos="ácidos mordientes", re_=r"\bacid dyes?\b"),
            opcion("basicos", "Basic dyes (acrylic)", terminos="básicos", re_=r"\bbasic dyes?\b"),
            opcion("directos", "Direct dyes (cotton)", terminos="directos", re_=r"\bdirect dyes?\b"),
            opcion("tina", "Vat dyes, including indigo", terminos="tina", re_=r"\b(vat|indigo|indigo)\b"),
            opcion("reactivos", "Reactive dyes (cotton)", terminos="reactivos", re_=r"\breactive\b"),
            opcion("otros", "Other synthetic dyes or mixtures of the above"),
            opcion("abrillantador", "Fluorescent brightening agent", terminos="avivado fluorescente", re_=r"\b(optical brighteners?|blanqueador optico)\b"),
            opcion("natural", "Of vegetable or animal origin", terminos="origen vegetal", re_=r"\b(natural dyes?|vegetal|cochineal|cochinilla)\b")],
            ambitos(["colorante"], "REQUIRE"), orden=30),
        atributo("tipo_pigmento", "Kind of pigment", "select", [
            opcion("organico", "Synthetic organic pigment", terminos="pigmentos orgánicos"),
            opcion("dioxido_titanio", "Titanium dioxide based (80 % or more)", terminos="dióxido de titanio", re_=r"\b(titanium dioxide|tio2|dioxido de titanio)\b"),
            opcion("dioxido_titanio_bajo", "Titanium dioxide based (under 80 %)", terminos="dióxido de titanio"),
            opcion("inorganico", "Other inorganic pigment (iron oxide, carbon black preparation)", terminos="pigmentos inorgánicos"),
            opcion("dispersion", "Dispersed in a non-aqueous medium, for making paints (pigment paste, masterbatch for paints)",
                   terminos="dispersos medios no acuosos")],
            ambitos(["pigmento"], "REQUIRE"), orden=31),
        atributo("medio_pintura", "Medium", "select", [
            opcion("disolvente", "Polymer dissolved or dispersed in an organic solvent (solvent-based)", re_=r"\b(solvent[- ]based|base solvente)\b"),
            opcion("agua", "Polymer dispersed or dissolved in water (water-based)", re_=r"\b(water[- ]based|base agua|acuos[oa])\b"),
            opcion("otro", "Other (oil paints, leather water pigments)")],
            ambitos(["pintura"], "REQUIRE"), orden=32,
            ayuda="Chapter 32 Note 4: solutions of polymers of 39.01–39.13 with more than 50 % organic solvent by weight are 32.08."),
        atributo("polimero_pintura", "Base polymer", "select", [
            opcion("poliester", "Polyester", terminos="poliésteres", re_=r"\bpolyester\b"),
            opcion("acrilico", "Acrylic or vinyl polymer", terminos="acrílicos vinílicos", re_=r"\b(acrylic|acrilic[oa]|vinyl|vinil\w*)\b"),
            opcion("otro", "Other (polyurethane, epoxy, alkyd, nitrocellulose)", re_=r"\b(polyurethane|poliuretano|pu|epoxy|epoxi|alkyd)\b")],
            ambitos(["pintura"], "REQUIRE", condicion=[cond("medio_pintura", ["disolvente", "agua"])]), orden=33),
        atributo("tipo_tinta", "Kind of ink", "select", [
            opcion("imprimir_negra", "Printing ink, black"), opcion("imprimir_color", "Printing ink, other colors (incl. screen printing, plastisol)"),
            opcion("otra", "Writing, drawing or other ink")], ambitos(["tinta"], "REQUIRE"), orden=34),
        atributo("menor_1kg", "Put up for retail sale, net weight 1 kg or less", "boolean", [], ambitos(["adhesivo"]), defecto="false", orden=40),
        atributo("base_adhesivo", "Adhesive base", "select", [
            opcion("polimero", "Polymers of 39.01–39.13 or rubber (PU, polychloroprene, EVA hot-melt, acrylic)",
                   re_=r"\b(polyurethane|poliuretano|pu|neoprene|neopreno|polychloroprene|policloropreno|hot ?melt|eva|acrylic|rubber|caucho|latex)\b"),
            opcion("otro", "Other (starch, dextrin, casein, animal glue)")],
            ambitos(["adhesivo"], "REQUIRE", condicion=[cond("menor_1kg", False)]), orden=41),
        atributo("tipo_tensoactivo", "What it is", "select", [
            opcion("anionico", "Anionic surface-active agent"), opcion("cationico", "Cationic surface-active agent"),
            opcion("no_ionico", "Non-ionic surface-active agent"), opcion("otro_agente", "Other surface-active agent"),
            opcion("preparacion_menor", "Washing or cleaning preparation put up for retail sale"),
            opcion("preparacion", "Washing, cleaning or surface-active preparation, not for retail sale")],
            ambitos(["tensoactivo"], "REQUIRE"), orden=42,
            ayuda="Chapter 34 Note 3: a surface-active agent at 0.5 % in water at 20 °C gives a clear or stable liquid and lowers the "
                  "surface tension of water to 45 dyn/cm or less."),
        atributo("forma_jabon", "Form", "select", [
            opcion("barra_tocador", "Bar, toilet use"), opcion("barra_otra", "Bar, other use (laundry)"),
            opcion("liquido_piel", "Liquid or cream for washing the skin"), opcion("otra", "Other forms (flakes, powder)")],
            ambitos(["jabon"], "REQUIRE"), orden=43),
        atributo("aceite_petroleo", "Petroleum oil content", "select", [
            opcion("ninguno", "No petroleum oil"), opcion("menos_70", "Contains petroleum oil, under 70 % by weight"),
            opcion("70_o_mas", "70 % or more petroleum oil (it is a lubricating oil)")],
            ambitos(["lubricante"], "REQUIRE"), orden=44,
            ayuda="Heading 34.03 versus 27.10: with 70 % or more of petroleum oil it is an oil of chapter 27."),
        atributo("uso_textil_cuero", "For treating textiles, leather or furskins", "boolean", [],
                 ambitos(["lubricante"], condicion=[cond("aceite_petroleo", ["ninguno", "menos_70"])]), defecto="false", orden=45),
        atributo("tipo_cera", "Kind of wax", "select", [
            opcion("preparada", "Artificial or prepared wax (mixtures, waxes with resins)"), opcion("peg", "Polyethylene glycol wax"),
            opcion("parafina", "Paraffin with under 0.75 % oil", terminos="parafina"), opcion("mineral", "Other mineral wax (microcrystalline, slack wax)")],
            ambitos(["cera"], "REQUIRE"), orden=46),
        atributo("uso_pulimento", "For", "select", [
            opcion("calzado_cuero", "Footwear or leather", defecto=True), opcion("madera", "Wooden furniture or floors"),
            opcion("carroceria", "Vehicle bodies, glass or metal"), opcion("fregar", "Scouring pastes and powders"), opcion("otro", "Other")],
            ambitos(["betun"], "REQUIRE"), orden=47),
        atributo("industria_apresto", "Used in the industry of", "select", [
            opcion("textil", "Textiles", re_=r"\b(textile|textil|fabric|tela)\b"), opcion("cuero", "Leather", re_=r"\b(leather|cuero|piel)\b"),
            opcion("papel", "Paper")], ambitos(["apresto"], "REQUIRE"), orden=48),
        atributo("tipo_aditivo", "Kind of additive", "select", [
            opcion("acelerante", "Prepared rubber accelerator"), opcion("plastificante", "Compound plasticizer"),
            opcion("antioxidante_tmq", "Antioxidant: mixture of TMQ oligomers"), opcion("antioxidante", "Other antioxidant or stabilizer")],
            ambitos(["aditivo_polimero"], "REQUIRE", condicion=[cond("definido", False)]), orden=49),
        atributo("tipo_biocida", "Kind", "select", [
            opcion("desinfectante", "Disinfectant or antimicrobial"), opcion("insecticida", "Insecticide"), opcion("fungicida", "Fungicide or anti-mold"),
            opcion("otro", "Other")], ambitos(["biocida"], "REQUIRE"), orden=50),
        atributo("tipo_reactivo", "Kind", "select", [
            opcion("referencia", "Certified reference material"), opcion("otro", "Other diagnostic or laboratory reagent")],
            ambitos(["reactivo"], "REQUIRE"), orden=51),
    ]
    R = regla
    reglas = [R("R-NE-QUI-INORG-MEZCLA", "quimico_inorganico", si(definido=False), tipo="REVIEW",
                efecto="Not a chemically defined compound: chapter 28 does not apply (Note 1). Choose the category by its function, "
                       "or other chemical preparations (38.24).")]
    reglas += [R(f"R-NE-QUI-INORG-{k.upper()}", "quimico_inorganico", si(definido=True, grupo_inorganico=k), v[1],
                 f"Chemically defined inorganic compound, {v[0].split(' (')[0].lower()} → headings {v[1][0][:2]}.{v[1][0][2:]}–{v[1][-1][2:]} "
                 "(chapter 28 Note 1); the name finds the subheading") for k, v in GRUPOS_INORG.items()]
    reglas += [R("R-NE-QUI-ORG-MEZCLA", "quimico_organico", si(definido=False), tipo="REVIEW",
                 efecto="Not a chemically defined compound: chapter 29 does not apply (Note 1). A mixture of solvents is 38.14; "
                        "otherwise classify it by its function.")]
    reglas += [R(f"R-NE-QUI-ORG-{k.upper()}", "quimico_organico", si(definido=True, grupo_organico=k), v[1],
                 f"Chemically defined organic compound, {v[0].split(' (')[0].lower()} → headings {v[1][0][:2]}.{v[1][0][2:]}–{v[1][-1][2:]} "
                 "(chapter 29 Note 1); the name finds the subheading") for k, v in GRUPOS_ORG.items()]
    reglas += [R(f"R-NE-QUI-DISOLV-{k.upper()}", "disolvente", si(definido=True, grupo_organico=k), v[1],
                 f"A single solvent compound is chapter 29 ({v[0].split(' (')[0].lower()})") for k, v in GRUPOS_ORG.items()]
    reglas += [
        R("R-NE-QUI-DISOLV-MEZCLA", "disolvente", si(definido=False), ["381400"],
          "Composite organic solvents and thinners; paint removers → 3814.00"),
        # Colorantes, pigmentos, pinturas, tintas
        *[R(f"R-NE-QUI-COLOR-{k.upper()}", "colorante", si(clase_colorante=k), [c], f"{t} → {c[:4]}.{c[4:]}") for k, c, t in (
            ("dispersos", "320411", "Disperse dyes"), ("acidos", "320412", "Acid and mordant dyes"), ("basicos", "320413", "Basic dyes"),
            ("directos", "320414", "Direct dyes"), ("tina", "320415", "Vat dyes"), ("reactivos", "320416", "Reactive dyes"),
            ("otros", "320419", "Other synthetic organic dyes"), ("abrillantador", "320420", "Fluorescent brightening agents"),
            ("natural", "320300", "Colouring matter of vegetable or animal origin"))],
        *[R(f"R-NE-QUI-PIGM-{k.upper()}", "pigmento", si(tipo_pigmento=k), cs, t) for k, cs, t in (
            ("organico", ["320417"], "Synthetic organic pigments → 3204.17"),
            ("dioxido_titanio", ["320611"], "Titanium dioxide pigments, 80 % or more → 3206.11"),
            ("dioxido_titanio_bajo", ["320619"], "Other titanium dioxide pigments → 3206.19"),
            ("inorganico", ["320620", "320641", "320642", "320649", "320650"], "Other inorganic pigments → 32.06 (the name finds the subheading)"),
            ("dispersion", ["321210", "321290"], "Pigments dispersed in non-aqueous media for paints → 32.12 (chapter 32 Note 3)"))],
        R("R-NE-QUI-PINT-DIS-POL", "pintura", si(medio_pintura="disolvente", polimero_pintura="poliester"), ["320810"],
          "Solvent-based paint of polyesters → 3208.10"),
        R("R-NE-QUI-PINT-DIS-ACR", "pintura", si(medio_pintura="disolvente", polimero_pintura="acrilico"), ["320820"],
          "Solvent-based paint of acrylic or vinyl polymers → 3208.20"),
        R("R-NE-QUI-PINT-DIS-OTRO", "pintura", si(medio_pintura="disolvente", polimero_pintura="otro"), ["320890"],
          "Other solvent-based paints and varnishes (PU, epoxy, alkyd) → 3208.90"),
        R("R-NE-QUI-PINT-AGUA-ACR", "pintura", si(medio_pintura="agua", polimero_pintura="acrilico"), ["320910"],
          "Water-based paint of acrylic or vinyl polymers → 3209.10"),
        R("R-NE-QUI-PINT-AGUA-OTRO", "pintura", si(medio_pintura="agua", polimero_pintura=["poliester", "otro"]), ["320990"],
          "Other water-based paints → 3209.90"),
        R("R-NE-QUI-PINT-OTRO", "pintura", si(medio_pintura="otro"), ["321000"], "Other paints; water pigments for finishing leather → 3210.00"),
        R("R-NE-QUI-TINTA-NEG", "tinta", si(tipo_tinta="imprimir_negra"), ["321511"], "Black printing ink → 3215.11"),
        R("R-NE-QUI-TINTA-COL", "tinta", si(tipo_tinta="imprimir_color"), ["321519"], "Other printing inks → 3215.19"),
        R("R-NE-QUI-TINTA-OTRA", "tinta", si(tipo_tinta="otra"), ["321590"], "Writing, drawing and other inks → 3215.90"),
        # Adhesivos
        R("R-NE-QUI-ADH-MENOR", "adhesivo", si(menor_1kg=True), ["350610"], "Glue or adhesive put up for retail sale, 1 kg or less → 3506.10"),
        R("R-NE-QUI-ADH-POL", "adhesivo", si(menor_1kg=False, base_adhesivo="polimero"), ["350691"],
          "Adhesive based on polymers of 39.01–39.13 or rubber → 3506.91"),
        R("R-NE-QUI-ADH-OTRO", "adhesivo", si(menor_1kg=False, base_adhesivo="otro"), ["350699"], "Other glues → 3506.99"),
        # Chapter 34
        *[R(f"R-NE-QUI-TENSO-{k.upper()}", "tensoactivo", si(tipo_tensoactivo=k), cs, t) for k, cs, t in (
            ("anionico", ["340231", "340239"], "Anionic organic surface-active agents → 3402.31/39"),
            ("cationico", ["340241"], "Cationic organic surface-active agents → 3402.41"),
            ("no_ionico", ["340242"], "Non-ionic organic surface-active agents → 3402.42"),
            ("otro_agente", ["340249"], "Other organic surface-active agents → 3402.49"),
            ("preparacion_menor", ["340250"], "Washing and cleaning preparations put up for retail sale → 3402.50"),
            ("preparacion", ["340290"], "Other washing, cleaning and surface-active preparations → 3402.90"))],
        *[R(f"R-NE-QUI-JABON-{k.upper()}", "jabon", si(forma_jabon=k), [c], t) for k, c, t in (
            ("barra_tocador", "340111", "Toilet soap in bars → 3401.11"), ("barra_otra", "340119", "Other soap in bars → 3401.19"),
            ("liquido_piel", "340130", "Liquid or cream for washing the skin → 3401.30"), ("otra", "340120", "Soap in other forms → 3401.20"))],
        R("R-NE-QUI-LUB-ACEITE", "lubricante", si(aceite_petroleo="70_o_mas"), ["271019"],
          "With 70 % or more of petroleum oil it is a lubricating oil of 27.10 (heading 34.03, exclusions)"),
        R("R-NE-QUI-LUB-PET-TEX", "lubricante", si(aceite_petroleo="menos_70", uso_textil_cuero=True), ["340311"],
          "Lubricating preparation with petroleum oil, for textiles or leather → 3403.11"),
        R("R-NE-QUI-LUB-PET", "lubricante", si(aceite_petroleo="menos_70", uso_textil_cuero=False), ["340319"],
          "Other lubricating preparations with petroleum oil → 3403.19"),
        R("R-NE-QUI-LUB-SIN-TEX", "lubricante", si(aceite_petroleo="ninguno", uso_textil_cuero=True), ["340391"],
          "Lubricating preparation without petroleum oil, for textiles or leather → 3403.91"),
        R("R-NE-QUI-LUB-SIN", "lubricante", si(aceite_petroleo="ninguno", uso_textil_cuero=False), ["340399"],
          "Other lubricating preparations (silicone, release agents) → 3403.99"),
        R("R-NE-QUI-CERA-PREP", "cera", si(tipo_cera="preparada"), ["340490"], "Artificial and prepared waxes → 3404.90 (chapter 34 Note 5)"),
        R("R-NE-QUI-CERA-PEG", "cera", si(tipo_cera="peg"), ["340420"], "Polyethylene glycol waxes → 3404.20"),
        R("R-NE-QUI-CERA-PARAF", "cera", si(tipo_cera="parafina"), ["271220"], "Paraffin wax with under 0.75 % oil → 2712.20 (chapter 34 Note 5 c)"),
        R("R-NE-QUI-CERA-MIN", "cera", si(tipo_cera="mineral"), ["271290"], "Other mineral waxes → 2712.90"),
        *[R(f"R-NE-QUI-BETUN-{k.upper()}", "betun", si(uso_pulimento=k), [c], t) for k, c, t in (
            ("calzado_cuero", "340510", "Polishes and creams for footwear or leather → 3405.10"),
            ("madera", "340520", "Polishes for wooden furniture and floors → 3405.20"),
            ("carroceria", "340530", "Polishes for vehicle bodies, glass or metal → 3405.30"),
            ("fregar", "340540", "Scouring pastes and powders → 3405.40"), ("otro", "340590", "Other polishes → 3405.90"))],
        # Chapter 38
        R("R-NE-QUI-APRESTO-TEX", "apresto", si(industria_apresto="textil"), ["380991"], "Finishing agents for the textile industry → 3809.91"),
        R("R-NE-QUI-APRESTO-CUE", "apresto", si(industria_apresto="cuero"), ["380993"], "Finishing agents for the leather industry → 3809.93"),
        R("R-NE-QUI-APRESTO-PAP", "apresto", si(industria_apresto="papel"), ["380992"], "Finishing agents for the paper industry → 3809.92"),
        R("R-NE-QUI-ADIT-DEF", "aditivo_polimero", si(definido=True), ["29"],
          "A single defined compound (e.g. a phthalate plasticizer) is chapter 29, not 38.12", revision=True),
        *[R(f"R-NE-QUI-ADIT-{k.upper()}", "aditivo_polimero", si(definido=False, tipo_aditivo=k), [c], t) for k, c, t in (
            ("acelerante", "381210", "Prepared rubber accelerators → 3812.10"), ("plastificante", "381220", "Compound plasticizers → 3812.20"),
            ("antioxidante_tmq", "381231", "Mixtures of TMQ oligomers → 3812.31"), ("antioxidante", "381239", "Other antioxidants and stabilizers → 3812.39"))],
        *[R(f"R-NE-QUI-BIOC-{k.upper()}", "biocida", si(tipo_biocida=k), [c], t) for k, c, t in (
            ("desinfectante", "380894", "Disinfectants → 3808.94"), ("insecticida", "380891", "Insecticides → 3808.91"),
            ("fungicida", "380892", "Fungicides → 3808.92"), ("otro", "380899", "Other → 3808.99"))],
        R("R-NE-QUI-REACT-REF", "reactivo", si(tipo_reactivo="referencia"), ["382290"], "Certified reference materials → 3822.90 (chapter 38 Note 2)"),
        R("R-NE-QUI-REACT-OTRO", "reactivo", si(tipo_reactivo="otro"), ["382219"], "Other diagnostic or laboratory reagents → 3822.19"),
        R("R-NE-QUI-PREP", "preparacion_quimica", [], ["382499"], "Chemical preparations not elsewhere specified → 3824.99"),
    ]
    casos = [
        caso("quimico_organico", "291411", nombre_quimico="Acetona", definido=True, grupo_organico="cetona"),
        caso("quimico_inorganico", "281511", nombre_quimico="Hidróxido de sodio sólido (soda cáustica)", definido=True, grupo_inorganico="base_oxido"),
        caso("adhesivo", "350691", menor_1kg=False, base_adhesivo="polimero", nombre_quimico="Polyurethane adhesive for soles"),
        caso("adhesivo", "350610", menor_1kg=True),
        caso("pintura", "320890", medio_pintura="disolvente", polimero_pintura="otro"),
        caso("pintura", "320910", medio_pintura="agua", polimero_pintura="acrilico"),
        caso("tinta", "321519", tipo_tinta="imprimir_color"),
        caso("colorante", "320411", clase_colorante="dispersos"),
        caso("pigmento", "320611", tipo_pigmento="dioxido_titanio"),
        caso("tensoactivo", "340250", tipo_tensoactivo="preparacion_menor"),
        caso("lubricante", "340399", aceite_petroleo="ninguno", uso_textil_cuero=False),
        caso("cera", "340490", tipo_cera="preparada"),
        caso("betun", "340510", uso_pulimento="calzado_cuero"),
        caso("apresto", "380991", industria_apresto="textil"),
        caso("aditivo_polimero", "381210", definido=False, tipo_aditivo="acelerante"),
        caso("disolvente", "381400", definido=False),
        caso("biocida", "380894", tipo_biocida="desinfectante"),
        caso("preparacion_quimica", "382499"),
    ]
    return {"dominio": {"codigo": DOM, "nombre": "Chemicals", "orden": 40,
                        "descripcion": "Chemically defined compounds (28, 29) and chemical preparations by their function (32, 34, 35, 38).",
                        "capitulos": [{"capitulo": c, "relevancia": "PRIMARY"} for c in ("28", "29", "32", "34", "35", "38")]
                        + [{"capitulo": c, "relevancia": "SECONDARY"} for c in ("27", "22", "33", "39")]},
            "fuente": NE, "categorias": cats, "atributos": atrs, "ambitos_comunes": {}, "reglas": reglas, "casos": casos}
