"""Materias primas para calzado, ropa y accesorios según las Notas Explicativas:
textiles (Sección XI: fibras, hilados, tejidos, tejidos de punto, no tejidos,
telas recubiertas, cintas, etiquetas, encajes), plástico (39), caucho (40),
cuero (41), papel y cartón (48), metales (72–76) y avíos (83.08, 96.06, 96.07).

- Nota 2 de la Sección XI: la materia textil que predomina en peso decide.
- Notas 4 y 5 de la Sección XI: hilados para la venta al por menor e hilo de coser.
- Capítulo 59: las telas recubiertas de plástico (59.03) o caucho (59.06) cuando la
  capa se ve a simple vista; si el textil solo refuerza una hoja de plástico, es 39.21.
- Capítulo 60: tejidos de punto de pelo o bucles (60.01), angostos (≤ 30 cm, 60.02/60.03),
  con 5 % o más de elastómero (60.02/60.04), de urdimbre (60.05), los demás (60.06).
- Capítulo 39, Nota 10: placas y hojas sin cortar más que en cuadrado o rectángulo;
  celulares o reforzadas 39.21, autoadhesivas 39.19, las demás 39.20.
- Capítulo 41: cuero curtido o crust (41.04–41.06), preparado después del
  curtido (41.07, 41.12, 41.13), agamuzado y charol (41.14), regenerado (41.15).
"""
from base import ambitos, atributo, caso, categoria, cond, opcion, partidas, regla, si

DOM = "RAW_MATERIALS"
NE = "Explanatory Notes, Section XI and chapters 39, 40, 41, 48, 58, 59, 60, 83 and 96"
TEXTILES = ["fibra_textil", "hilado", "tejido_plano", "tejido_punto", "no_tejido", "tela_recubierta", "cinta_etiqueta"]


def familia() -> dict:
    g_tex, g_otros = "Textile materials", "Other materials"
    cats = [
        categoria("fibra_textil", "Textile fiber, not spun (raw cotton, staple fiber, wool, filling fiber)", corto="Textile fiber",
                  aduana="Fibra textil", grupo=g_tex, dominio=DOM, capitulos=["50", "51", "52", "53", "54", "55"], orden=10, prioridad=30,
                  re_=r"\b(staple fibers?|fibras? (cortas?|discontinuas?|textiles?)|raw cotton|algodon sin cardar|polyester fiber|fibra de poliester|"
                      r"wadding fiber|fiberfill|guata de fibra|wool tops?|tow)\b", alias="fibra textil fibra corta fibra de relleno"),
        categoria("hilado", "Yarn or sewing thread", corto="Yarn or thread", aduana="Hilado", grupo=g_tex, dominio=DOM,
                  capitulos=["50", "51", "52", "53", "54", "55"], orden=20, prioridad=33,
                  re_=r"\b(yarns?|hilos?|hilados?|sewing threads?|hilo de coser|filament yarns?|spun yarns?)\b", alias="hilo hilado hilo de coser"),
        categoria("tejido_plano", "Woven fabric in the piece", corto="Woven fabric", aduana="Tejido plano", grupo=g_tex, dominio=DOM,
                  capitulos=["50", "51", "52", "53", "54", "55"], orden=30, prioridad=32,
                  re_=r"\b(woven fabrics?|tejidos? planos?|telas?|fabrics? (in rolls?|by the meter)|denim|mezclilla|canvas|lona|poplin|popelina|"
                      r"twill|sarga|ripstop|oxford|taffeta|tafetan|chambray|gabardin[ae])\b", alias="tela tejido plano lona mezclilla"),
        categoria("tejido_punto", "Knitted or crocheted fabric in the piece", corto="Knitted fabric", aduana="Tejido de punto", grupo=g_tex,
                  dominio=DOM, capitulos=["60"], orden=40, prioridad=32,
                  re_=r"\b(knit(ted)? fabrics?|tejidos? de punto|jersey fabric|mesh fabric|malla|spacer mesh|fleece fabric|tela polar|rib knit|"
                      r"single jersey|interlock|tricot|pique fabric)\b", alias="tejido de punto malla jersey polar"),
        categoria("no_tejido", "Nonwoven or felt", corto="Nonwoven", aduana="Tela sin tejer", grupo=g_tex, dominio=DOM, capitulos=["56"], orden=50,
                  prioridad=31, re_=r"\b(nonwovens?|non-woven|tela sin tejer|tnt|spunbond|felt|fieltro|needle ?punch|punzonad[oa])\b",
                  alias="tela sin tejer fieltro spunbond"),
        categoria("tela_recubierta", "Fabric coated, covered or laminated with plastics or rubber", corto="Coated fabric",
                  aduana="Tela recubierta", grupo=g_tex, dominio=DOM, capitulos=["59", "39"], orden=60, prioridad=31,
                  re_=r"\b(coated fabrics?|telas? recubiertas?|laminated fabrics?|telas? laminadas?|pvc coated|pu coated|rubberi[sz]ed fabric|"
                      r"neoprene fabric|tela engomada)\b", alias="tela recubierta tela laminada tela engomada"),
        categoria("cinta_etiqueta", "Narrow fabric, label, elastic, hook-and-loop, lace, braid or embroidery", corto="Tape, label or trim",
                  aduana="Cinta textil", grupo=g_tex, dominio=DOM, capitulos=["58", "48"], orden=70, prioridad=34,
                  re_=r"\b(labels?|etiquetas?|elastic (bands?|tapes?)|elasticos?|cintas?|ribbons?|listones?|webbing|reatas?|hook and loop|velcro|"
                      r"lace|encajes?|braids?|trenzas?|embroider(y|ies)|bordados?|patches? bordad\w*|piping|vivos?)\b",
                  alias="etiqueta elástico cinta reata velcro encaje bordado"),
        categoria("avio", "Trim: zipper, button, snap, buckle, eyelet or hook", corto="Trim", aduana="Avío", grupo=g_otros, dominio=DOM,
                  capitulos=["96", "83"], orden=80, prioridad=35,
                  re_=r"\b(zippers?|cierres?|cremalleras?|buttons?|botones?|snaps?|broches?|buckles?|hebillas?|eyelets?|ojetes?|ojales metalicos|"
                      r"grommets?|hooks?|ganchos?|rivets?|remaches?|sliders?|tiradores?|cord locks?|topes?)\b",
                  alias="cierre zipper botón broche hebilla ojete remache"),
        categoria("resina_plastica", "Plastic in primary forms: pellets, powder, liquid resin, masterbatch base", corto="Plastic resin",
                  aduana="Resina plástica", grupo=g_otros, dominio=DOM, capitulos=["39"], orden=90, prioridad=31,
                  re_=r"\b(resins?|resinas?|pellets?|granul(es|os)|polymers?|polimeros?|compounds? de pvc|pvc compound|tpu pellets?|eva pellets?|"
                      r"polyurethane (resin|system)|poliol|polyol|isocyanate|isocianato)\b", alias="resina pellets polímero compuesto de PVC"),
        categoria("lamina_plastica", "Plastic sheet, film, foam sheet or strip", corto="Plastic sheet or foam", aduana="Lámina de plástico",
                  grupo=g_otros, dominio=DOM, capitulos=["39"], orden=100, prioridad=31,
                  re_=r"\b(plastic (sheets?|films?)|laminas? (de )?plastic\w*|films?|peliculas?|foam sheets?|espumas?|eva foam|pu foam|"
                      r"sheets? of (eva|pvc|tpu)|tpu film|hot melt film)\b", alias="lámina plástica película espuma EVA"),
        categoria("caucho", "Rubber: natural, synthetic, compounded or sheets", corto="Rubber", aduana="Caucho", grupo=g_otros, dominio=DOM,
                  capitulos=["40"], orden=110, prioridad=31,
                  re_=r"\b(rubber (sheets?|compound|crepe)?|caucho|latex|hule|rubber soling sheets?|planchas? de caucho|crepe)\b",
                  alias="caucho hule látex lámina de caucho"),
        categoria("cuero", "Leather: tanned, crust or finished hides and skins", corto="Leather", aduana="Cuero", grupo=g_otros, dominio=DOM,
                  capitulos=["41"], orden=120, prioridad=32,
                  re_=r"\b(leather|cueros?|hides?|wet ?blue|crust|nubuck|suede|gamuza|napa|nappa|patent leather|charol|split leather|carnaza|vaqueta)\b",
                  alias="cuero piel wet blue crust nobuck gamuza charol"),
        categoria("cuero_sintetico", "Synthetic leather (PU or PVC)", corto="Synthetic leather", aduana="Cuero sintético", grupo=g_otros,
                  dominio=DOM, capitulos=["59", "39", "56"], orden=130, prioridad=33,
                  re_=r"\b(synthetic leather|cuero sintetico|pu leather|pvc leather|faux leather|vegan leather|leatherette|microfiber leather|"
                      r"similcuero|cuerina|ecocuero)\b", alias="cuero sintético PU PVC cuerina"),
        categoria("papel_carton", "Paper, paperboard, boxes or paper bags", corto="Paper or box", aduana="Papel o cartón", grupo=g_otros,
                  dominio=DOM, capitulos=["48"], orden=140, prioridad=30,
                  re_=r"\b(paper|papel|paperboard|carton|cardboard|boxes?|cajas?|corrugated|corrugad[oa]|tissue paper|papel de seda|"
                      r"paper bags?|bolsas? de papel|kraft)\b", alias="papel cartón caja corrugada bolsa de papel papel de seda"),
        categoria("metal", "Metal sheet, wire, bar or profile", corto="Metal", aduana="Metal", grupo=g_otros, dominio=DOM,
                  capitulos=["72", "74", "76"], orden=150, prioridad=28,
                  re_=r"\b(steel (sheets?|wire|bars?)|acero|alumin(i)?um|aluminio|copper|cobre|brass|laton|wire|alambre|metal sheets?|laminas? metalicas?)\b",
                  alias="acero aluminio latón alambre lámina metálica"),
    ]
    fib = {"lana": "lana", "algodon": "algodon", "seda": "seda", "sintetica": "sintetica", "artificial": "artificial", "vegetal": "vegetal"}
    atrs = [
        atributo("filamento", "Man-made fiber form", "select", [
            opcion("filamento", "Filament (continuous)", re_=r"\b(filament|filamento|continuous|dty|fdy|poy|multifilament)\b"),
            opcion("discontinua", "Staple (spun from short fibers)", re_=r"\b(staple|spun|discontinu\w+|ring spun|open end)\b")],
            ambitos(["fibra_textil", "hilado", "tejido_plano"], "REQUIRE", condicion=[cond("fibra", ["sintetica", "artificial"])]), orden=20,
            ayuda="Chapters 54 (filaments) and 55 (staple fibers); Section XI Note 2 B c) treats them together against other chapters."),
        atributo("uso_hilado", "Put up as", "select", [
            opcion("industrial", "Industrial yarn (cones, beams)", defecto=True),
            opcion("venta_menor", "Put up for retail sale (Section XI Note 4)"),
            opcion("hilo_coser", "Sewing thread (Section XI Note 5: on supports up to 1,000 g, dressed, final Z twist)",
                   re_=r"\b(sewing thread|hilo de coser|hilo para coser)\b")],
            ambitos(["hilado"], "REQUIRE"), orden=21),
        atributo("predominio85", "Contains 85 % or more by weight of the predominant fiber", "boolean", [],
                 ambitos(["hilado", "tejido_plano"], condicion=[cond("fibra", ["algodon", "sintetica", "artificial"])]), defecto="true", orden=22),
        atributo("mezcla_con", "Mainly mixed with", "select", [
            opcion("artificiales_sinteticas", "Man-made fibers"), opcion("algodon", "Cotton"), opcion("lana", "Wool or fine animal hair"),
            opcion("otras", "Other fibers or filaments")],
            ambitos(["tejido_plano"], condicion=[cond("predominio85", False)]), orden=23),
        atributo("peso_g_m2", "Weight", "number", [], ambitos(["tejido_plano", "no_tejido"], "REQUIRE"), unidad="g/m²", orden=24,
                 ayuda="Weight per square meter: cotton fabrics split at 200 g/m², synthetic staple mixed with cotton at 170 g/m², nonwovens at 25, "
                       "70 and 150 g/m²."),
        atributo("tipo_punto", "Kind of knitted fabric", "select", [
            opcion("pelo", "Pile, long pile, terry or looped (velour, fleece with pile)", re_=r"\b(pile|velour|terry|toalla|plush|felpa|sherpa)\b"),
            opcion("angosto_elastico", "Width up to 30 cm, 5 % or more elastomeric yarn"),
            opcion("angosto", "Width up to 30 cm, other"),
            opcion("elastico", "Width over 30 cm, 5 % or more elastomeric yarn", re_=r"\b(spandex|elastane|elastano|lycra|stretch)\b"),
            opcion("urdimbre", "Warp knit (tricot, raschel, mesh)", re_=r"\b(warp|tricot|raschel|spacer|mesh|malla)\b"),
            opcion("otro", "Other weft knit (jersey, rib, interlock, fleece without pile)", defecto=True)],
            ambitos(["tejido_punto"], "REQUIRE"), orden=25),
        atributo("tipo_no_tejido", "Kind", "select", [
            opcion("filamentos", "Nonwoven of man-made filaments (spunbond)", re_=r"\b(spunbond|spun ?bond|filament)\b"),
            opcion("otro", "Other nonwoven (needle-punched staple, spunlace)", defecto=True),
            opcion("fieltro", "Felt", re_=r"\b(felt|fieltro)\b")], ambitos(["no_tejido"], "REQUIRE"), orden=26),
        atributo("recubrimiento", "Coating", "select", [
            opcion("pvc", "Poly(vinyl chloride)", re_=r"\b(pvc|vinyl|vinil\w*)\b"), opcion("pu", "Polyurethane", re_=r"\b(pu|polyurethane|poliuretano|tpu)\b"),
            opcion("otro_plastico", "Other plastics (acrylic, silicone)"), opcion("caucho", "Rubber (incl. neoprene laminated with fabric)",
                                                                                 re_=r"\b(rubber|caucho|neoprene|neopreno|latex)\b"),
            opcion("otro", "Other (wax, oil, tar)")],
            ambitos(["tela_recubierta", "cuero_sintetico"], "REQUIRE"), orden=27),
        atributo("soporte", "Backing", "select", [
            opcion("tejido", "Woven or knitted fabric, coating visible"), opcion("no_tejido", "Nonwoven or microfiber backing"),
            opcion("sin_soporte", "No textile backing (or fabric used only to reinforce)")],
            ambitos(["tela_recubierta", "cuero_sintetico"], "REQUIRE"), defecto="tejido", orden=28,
            ayuda="Chapter 59 Note 2: when the textile only reinforces a plastic sheet, or the coating cannot be seen, it is not 59.03."),
        atributo("tipo_cinta", "Kind", "select", [
            opcion("elastico", "Narrow woven fabric with 5 % or more elastomeric yarn (elastic tape)", re_=r"\b(elastic|elastico)\b"),
            opcion("velcro", "Hook-and-loop or pile narrow fabric (velvet ribbon)", re_=r"\b(velcro|hook and loop|terciopelo)\b"),
            opcion("cinta", "Other narrow woven fabric (webbing, ribbon, tape)", re_=r"\b(webbing|reata|ribbon|liston|tape|cinta|twill tape)\b", defecto=True),
            opcion("etiqueta_tejida", "Woven label or badge", re_=r"\b(woven labels?|etiquetas? tejidas?)\b"),
            opcion("etiqueta_textil", "Other textile label (printed satin, heat transfer on fabric)"),
            opcion("etiqueta_papel", "Paper or cardboard label or hang tag", re_=r"\b(hang ?tags?|colgantes?|paper labels?|etiquetas? de (papel|carton))\b"),
            opcion("encaje", "Lace", re_=r"\b(lace|encaje)\b"), opcion("trenza", "Braid, cord or ornamental trimming in the piece"),
            opcion("bordado", "Embroidery or embroidered badge", re_=r"\b(embroider\w*|bordad\w*)\b")],
            ambitos(["cinta_etiqueta"], "REQUIRE"), orden=29),
        atributo("impresa", "Printed", "boolean", [], ambitos(["cinta_etiqueta"], condicion=[cond("tipo_cinta", "etiqueta_papel")]), defecto="true",
                 orden=30),
        atributo("tipo_avio", "Kind", "select", [
            opcion("cierre_metal", "Zipper with base metal teeth", re_=r"\b(metal zippers?|cierres? metalicos?|brass zipper)\b"),
            opcion("cierre_otro", "Zipper with plastic or nylon teeth", re_=r"\b(zippers?|cierres?|cremalleras?|coil|nylon zipper|vislon)\b"),
            opcion("cierre_parte", "Zipper part (slider, tape with teeth)", re_=r"\b(sliders?|tiradores?|zipper tape|cadena)\b"),
            opcion("broche_presion", "Press-fastener, snap or press-stud", re_=r"\b(snaps?|broches? de presion|press studs?)\b"),
            opcion("boton_plastico", "Button of plastic, not covered with textile", re_=r"\b(plastic buttons?|botones? de plastico)\b"),
            opcion("boton_metal", "Button of base metal, not covered with textile", re_=r"\b(metal buttons?|botones? metalicos?|jeans? buttons?)\b"),
            opcion("boton_otro", "Other button (wood, coconut, covered with textile)"),
            opcion("gancho_ojete", "Hook, eye or eyelet of base metal", re_=r"\b(eyelets?|ojetes?|grommets?|hooks?|ganchos?)\b"),
            opcion("remache", "Tubular or bifurcated rivet", re_=r"\b(rivets?|remaches?)\b"),
            opcion("hebilla", "Buckle, clasp or other base metal fastener", re_=r"\b(buckles?|hebillas?|clasps?)\b"),
            opcion("plastico", "Plastic buckle, cord lock or fastener", re_=r"\b(cord locks?|topes?|plastic buckles?|hebillas? plasticas?)\b")],
            ambitos(["avio"], "REQUIRE"), orden=31),
        atributo("polimero", "Polymer", "select", [
            opcion("polietileno", "Polyethylene", terminos="polietileno", re_=r"\b(polyethylene|polietileno|pe|hdpe|ldpe)\b"),
            opcion("polipropileno", "Polypropylene", terminos="polipropileno", re_=r"\b(polypropylene|polipropileno|pp)\b"),
            opcion("eva", "Ethylene-vinyl acetate (EVA)", terminos="acetato de vinilo", re_=r"\b(eva|ethylene vinyl acetate)\b"),
            opcion("poliestireno", "Polystyrene, ABS", terminos="estireno", re_=r"\b(polystyrene|poliestireno|abs|eps)\b"),
            opcion("pvc", "Poly(vinyl chloride)", terminos="cloruro de vinilo", re_=r"\b(pvc|vinyl)\b"),
            opcion("acrilico", "Acrylic polymer", terminos="acrílicos", re_=r"\b(acrylic|acrilic\w*|pmma)\b"),
            opcion("poliester", "Polyester, PET or polycarbonate", terminos="poliésteres", re_=r"\b(pet|polyester|poliester|polycarbonate|policarbonato)\b"),
            opcion("poliamida", "Polyamide (nylon)", terminos="poliamidas", re_=r"\b(polyamide|poliamida|nylon|pa6)\b"),
            opcion("poliuretano", "Polyurethane (incl. TPU)", terminos="poliuretanos", re_=r"\b(polyurethane|poliuretano|pu|tpu)\b"),
            opcion("silicona", "Silicone", terminos="siliconas", re_=r"\b(silicone|silicona)\b"),
            opcion("otro", "Other")],
            ambitos(["resina_plastica", "lamina_plastica"], "REQUIRE"), orden=32),
        atributo("autoadhesiva", "Self-adhesive", "boolean", [], ambitos(["lamina_plastica"]), defecto="false", orden=33),
        atributo("celular", "Cellular (foam)", "boolean", [], ambitos(["lamina_plastica"]), defecto="false", orden=34,
                 patrones=[{"re": r"\b(foam|espuma|cellular|celular|sponge|esponja)\b", "en": "todo"}]),
        atributo("reforzada", "Reinforced, laminated or combined with other materials", "boolean", [],
                 ambitos(["lamina_plastica"], condicion=[cond("celular", False), cond("autoadhesiva", False)]), defecto="false", orden=35),
        atributo("forma_caucho", "Form", "select", [
            opcion("natural", "Natural rubber or latex in primary forms"), opcion("sintetico", "Synthetic rubber in primary forms"),
            opcion("mezcla", "Compounded rubber, unvulcanized"), opcion("lamina_celular", "Vulcanized cellular sheet or strip (sponge)"),
            opcion("lamina", "Vulcanized non-cellular sheet or strip (soling sheet)"), opcion("perfil", "Vulcanized profile or rod")],
            ambitos(["caucho"], "REQUIRE"), orden=36),
        atributo("animal", "Animal", "select", [
            opcion("bovino", "Bovine or equine (cow, buffalo, horse)", re_=r"\b(cow|cowhide|vaca|bovine|bovino|buffalo|bufalo|calf|becerro|vaqueta)\b",
                   defecto=True),
            opcion("ovino", "Sheep or lamb", re_=r"\b(sheep|lamb|oveja|cordero|ovino)\b"), opcion("caprino", "Goat or kid", re_=r"\b(goat|cabra|caprino)\b"),
            opcion("porcino", "Pig", re_=r"\b(pig|pigskin|cerdo|porcino)\b"), opcion("reptil", "Reptile"), opcion("otro", "Other animal")],
            ambitos(["cuero"], "REQUIRE"), orden=37),
        atributo("estado_cuero", "State", "select", [
            opcion("humedo", "Tanned, wet (incl. wet-blue)", re_=r"\b(wet ?blue|wet white)\b"),
            opcion("crust", "Crust (dry, retanned, not finished)", re_=r"\b(crust)\b"),
            opcion("terminado", "Finished after tanning or crusting", defecto=True),
            opcion("agamuzado", "Chamois or oil-tanned"), opcion("charol", "Patent or metallized", re_=r"\b(patent|charol|metalliz\w+|metaliz\w+)\b"),
            opcion("regenerado", "Composition leather (leather fibers)", re_=r"\b(bonded leather|regenerated|regenerado|reconstituido)\b")],
            ambitos(["cuero"], "REQUIRE"), orden=38),
        atributo("tipo_papel", "What it is", "select", [
            opcion("caja_corrugada", "Box of corrugated paperboard", re_=r"\b(corrugated|corrugad\w*|master cartons?|cajas? master)\b"),
            opcion("caja_plegable", "Folding box or carton of non-corrugated board (shoe box)", re_=r"\b(shoe ?box(es)?|cajas? de zapato|folding)\b"),
            opcion("bolsa", "Paper bag or sack", re_=r"\b(paper bags?|bolsas? de papel|sacks?)\b"),
            opcion("papel", "Paper or paperboard in rolls or sheets (tissue, kraft, wrapping)", defecto=True)],
            ambitos(["papel_carton"], "REQUIRE"), orden=39),
        atributo("metal_base", "Metal", "select", [
            opcion("acero", "Iron or steel (incl. stainless)", re_=r"\b(steel|acero|iron|hierro|stainless|inoxidable)\b"),
            opcion("aluminio", "Aluminum", re_=r"\b(alumin(i)?um|aluminio)\b"),
            opcion("cobre", "Copper or brass", re_=r"\b(copper|cobre|brass|laton|bronze|bronce)\b")],
            ambitos(["metal"], "REQUIRE"), orden=40),
        atributo("forma_metal", "Form", "select", [
            opcion("lamina", "Sheet, plate, strip or foil"), opcion("alambre", "Wire"), opcion("barra", "Bar, rod or profile")],
            ambitos(["metal"], "REQUIRE"), orden=41),
    ]
    comunes = {
        "comp.material": ambitos(TEXTILES[:5] + ["tela_recubierta"], "REQUIRE"),
        "fibra": ambitos(TEXTILES),
    }
    R = regla
    reglas = []
    # Fibras (capítulos 50–55)
    for f, cods in (("algodon", partidas("5201", "5203")), ("lana", partidas("5101", "5105")), ("seda", partidas("5001", "5003")),
                    ("vegetal", partidas("5301", "5305"))):
        reglas.append(R(f"R-NE-MP-FIBRA-{f.upper()}", "fibra_textil", si(fibra=f), cods, f"Textile fiber, not spun, of {f} → its chapter"))
    reglas += [
        R("R-NE-MP-FIBRA-SINTFIL", "fibra_textil", si(fibra="sintetica", filamento="filamento"), ["5501"], "Synthetic filament tow → 55.01"),
        R("R-NE-MP-FIBRA-SINTDIS", "fibra_textil", si(fibra="sintetica", filamento="discontinua"), ["5503", "5506"],
          "Synthetic staple fibers → 55.03 (not carded) or 55.06 (carded or combed)"),
        R("R-NE-MP-FIBRA-ARTFIL", "fibra_textil", si(fibra="artificial", filamento="filamento"), ["5502"], "Artificial filament tow → 55.02"),
        R("R-NE-MP-FIBRA-ARTDIS", "fibra_textil", si(fibra="artificial", filamento="discontinua"), ["5504", "5507"],
          "Artificial staple fibers → 55.04 or 55.07"),
    ]
    # Hilados
    reglas += [
        R("R-NE-MP-HILO-COSER-ALG", "hilado", si(uso_hilado="hilo_coser", fibra="algodon"), ["5204"], "Cotton sewing thread → 52.04 (Section XI Note 5)"),
        R("R-NE-MP-HILO-COSER-FIL", "hilado", si(uso_hilado="hilo_coser", fibra=["sintetica", "artificial"], filamento="filamento"), ["5401"],
          "Sewing thread of man-made filaments → 54.01"),
        R("R-NE-MP-HILO-COSER-DIS", "hilado", si(uso_hilado="hilo_coser", fibra=["sintetica", "artificial"], filamento="discontinua"), ["5508"],
          "Sewing thread of man-made staple fibers → 55.08"),
        R("R-NE-MP-HILO-MENOR-ALG", "hilado", si(uso_hilado="venta_menor", fibra="algodon"), ["5207"], "Cotton yarn for retail sale → 52.07"),
        R("R-NE-MP-HILO-MENOR-LANA", "hilado", si(uso_hilado="venta_menor", fibra="lana"), ["5109"], "Wool yarn for retail sale → 51.09"),
        R("R-NE-MP-HILO-MENOR-FIL", "hilado", si(uso_hilado="venta_menor", fibra=["sintetica", "artificial"], filamento="filamento"), ["5406"],
          "Man-made filament yarn for retail sale → 54.06"),
        R("R-NE-MP-HILO-MENOR-DIS", "hilado", si(uso_hilado="venta_menor", fibra=["sintetica", "artificial"], filamento="discontinua"), ["5511"],
          "Man-made staple yarn for retail sale → 55.11"),
        R("R-NE-MP-HILO-IND-ALG85", "hilado", si(uso_hilado="industrial", fibra="algodon", predominio85=True), ["5205"],
          "Cotton yarn, 85 % or more cotton → 52.05"),
        R("R-NE-MP-HILO-IND-ALG", "hilado", si(uso_hilado="industrial", fibra="algodon", predominio85=False), ["5206"],
          "Cotton yarn, under 85 % cotton → 52.06"),
        R("R-NE-MP-HILO-IND-LANA", "hilado", si(uso_hilado="industrial", fibra="lana"), partidas("5106", "5108"), "Wool yarn → 51.06–51.08"),
        R("R-NE-MP-HILO-IND-SEDA", "hilado", si(uso_hilado=["industrial", "venta_menor"], fibra="seda"), ["5004", "5005", "5006"], "Silk yarn → 50.04–50.06"),
        R("R-NE-MP-HILO-IND-SFIL", "hilado", si(uso_hilado="industrial", fibra="sintetica", filamento="filamento"), ["5402", "5404"],
          "Synthetic filament yarn (incl. textured, high tenacity) → 54.02; monofilament → 54.04"),
        R("R-NE-MP-HILO-IND-AFIL", "hilado", si(uso_hilado="industrial", fibra="artificial", filamento="filamento"), ["5403", "5405"],
          "Artificial filament yarn → 54.03"),
        R("R-NE-MP-HILO-IND-SDIS", "hilado", si(uso_hilado="industrial", fibra="sintetica", filamento="discontinua"), ["5509"],
          "Synthetic staple yarn → 55.09"),
        R("R-NE-MP-HILO-IND-ADIS", "hilado", si(uso_hilado="industrial", fibra="artificial", filamento="discontinua"), ["5510"],
          "Artificial staple yarn → 55.10"),
        R("R-NE-MP-HILO-IND-VEG", "hilado", si(uso_hilado=["industrial", "venta_menor"], fibra="vegetal"), partidas("5306", "5308"),
          "Yarn of other vegetable fibers → 53.06–53.08"),
    ]
    # Tejidos planos (Nota 2 de la Sección XI, peso por m²)
    reglas += [
        R("R-NE-MP-TEJ-ALG85-L", "tejido_plano", si(fibra="algodon", predominio85=True) + [cond("peso_g_m2", 200, "LTE")], ["5208"],
          "Woven cotton, 85 % or more, up to 200 g/m² → 52.08"),
        R("R-NE-MP-TEJ-ALG85-P", "tejido_plano", si(fibra="algodon", predominio85=True) + [cond("peso_g_m2", 200, "GT")], ["5209"],
          "Woven cotton, 85 % or more, over 200 g/m² (denim) → 52.09"),
        R("R-NE-MP-TEJ-ALGMM-L", "tejido_plano", si(fibra="algodon", predominio85=False, mezcla_con="artificiales_sinteticas")
          + [cond("peso_g_m2", 200, "LTE")], ["5210"], "Woven cotton under 85 %, mixed with man-made fibers, up to 200 g/m² → 52.10"),
        R("R-NE-MP-TEJ-ALGMM-P", "tejido_plano", si(fibra="algodon", predominio85=False, mezcla_con="artificiales_sinteticas")
          + [cond("peso_g_m2", 200, "GT")], ["5211"], "Woven cotton under 85 %, mixed with man-made fibers, over 200 g/m² → 52.11"),
        R("R-NE-MP-TEJ-ALGOT", "tejido_plano", si(fibra="algodon", predominio85=False, mezcla_con=["algodon", "lana", "otras"]), ["5212"],
          "Other woven fabrics of cotton → 52.12"),
        R("R-NE-MP-TEJ-LANA", "tejido_plano", si(fibra="lana"), partidas("5111", "5113"), "Woven wool or fine animal hair → 51.11–51.13"),
        R("R-NE-MP-TEJ-SEDA", "tejido_plano", si(fibra="seda"), ["5007"], "Woven silk → 50.07"),
        R("R-NE-MP-TEJ-VEG", "tejido_plano", si(fibra="vegetal"), partidas("5309", "5311"), "Woven linen, jute or other vegetable fiber → 53.09–53.11"),
        R("R-NE-MP-TEJ-SFIL", "tejido_plano", si(fibra="sintetica", filamento="filamento"), ["5407"],
          "Woven synthetic filament yarn (nylon, polyester ripstop, taffeta) → 54.07"),
        R("R-NE-MP-TEJ-AFIL", "tejido_plano", si(fibra="artificial", filamento="filamento"), ["5408"], "Woven artificial filament yarn → 54.08"),
        R("R-NE-MP-TEJ-SDIS85", "tejido_plano", si(fibra="sintetica", filamento="discontinua", predominio85=True), ["5512"],
          "Woven synthetic staple, 85 % or more → 55.12"),
        R("R-NE-MP-TEJ-SDISALG-L", "tejido_plano", si(fibra="sintetica", filamento="discontinua", predominio85=False, mezcla_con="algodon")
          + [cond("peso_g_m2", 170, "LTE")], ["5513"], "Woven synthetic staple under 85 %, mixed with cotton, up to 170 g/m² → 55.13"),
        R("R-NE-MP-TEJ-SDISALG-P", "tejido_plano", si(fibra="sintetica", filamento="discontinua", predominio85=False, mezcla_con="algodon")
          + [cond("peso_g_m2", 170, "GT")], ["5514"], "Woven synthetic staple under 85 %, mixed with cotton, over 170 g/m² → 55.14"),
        R("R-NE-MP-TEJ-SDISOT", "tejido_plano", si(fibra="sintetica", filamento="discontinua", predominio85=False,
                                                   mezcla_con=["artificiales_sinteticas", "lana", "otras"]), ["5515"],
          "Other woven synthetic staple → 55.15"),
        R("R-NE-MP-TEJ-ADIS", "tejido_plano", si(fibra="artificial", filamento="discontinua"), ["5516"], "Woven artificial staple → 55.16"),
    ]
    # Punto (capítulo 60)
    pref6006 = {"lana": "600610", "algodon": "60062", "sintetica": "60063", "artificial": "60064", "seda": "600690", "vegetal": "600690",
                "otra": "600690", "cuero": "600690", "": "6006"}
    reglas += [
        R("R-NE-MP-PUNTO-PELO", "tejido_punto", si(tipo_punto="pelo"), ["6001"], "Pile, long pile or looped knitted fabric → 60.01"),
        R("R-NE-MP-PUNTO-ANGEL", "tejido_punto", si(tipo_punto="angosto_elastico"), ["6002"],
          "Knitted fabric up to 30 cm wide with 5 % or more elastomeric yarn → 60.02"),
        R("R-NE-MP-PUNTO-ANG", "tejido_punto", si(tipo_punto="angosto"), ["6003"], "Knitted fabric up to 30 cm wide → 60.03"),
        R("R-NE-MP-PUNTO-EL", "tejido_punto", si(tipo_punto="elastico"), ["6004"],
          "Knitted fabric over 30 cm wide with 5 % or more elastomeric yarn → 60.04"),
        R("R-NE-MP-PUNTO-URD", "tejido_punto", si(tipo_punto="urdimbre"), ["6005"], "Warp knit fabric (tricot, raschel, mesh) → 60.05"),
        R("R-NE-MP-PUNTO-OTRO", "tejido_punto", si(tipo_punto="otro"), efecto="Other knitted fabric → 60.06 by fiber", por="fibra", mapa=pref6006),
    ]
    # No tejidos, telas recubiertas, cintas y etiquetas
    reglas += [
        R("R-NE-MP-NOTEJ-FIL", "no_tejido", si(tipo_no_tejido="filamentos"), ["56031"], "Nonwoven of man-made filaments → 5603.1x by weight"),
        R("R-NE-MP-NOTEJ-OTRO", "no_tejido", si(tipo_no_tejido="otro"), ["56039"], "Other nonwovens → 5603.9x by weight"),
        R("R-NE-MP-NOTEJ-FIELTRO", "no_tejido", si(tipo_no_tejido="fieltro"), ["5602"], "Felt → 56.02"),
        *[R(f"R-NE-MP-NOTEJ-P{n}", "no_tejido", si(tipo_no_tejido=["filamentos", "otro"]) + [cond("peso_g_m2", lo, "GT"), cond("peso_g_m2", hi, "LTE")],
            [f"56031{n}", f"56039{n}"], f"Nonwoven, {txt} → 5603.1{n} or 5603.9{n}")
          for n, lo, hi, txt in ((1, 0, 25, "up to 25 g/m²"), (2, 25, 70, "over 25 and up to 70 g/m²"), (3, 70, 150, "over 70 and up to 150 g/m²"),
                                 (4, 150, 100000, "over 150 g/m²"))],
        R("R-NE-MP-RECUB-PVC", "tela_recubierta", si(soporte="tejido", recubrimiento="pvc"), ["590310"], "Fabric coated with PVC → 5903.10"),
        R("R-NE-MP-RECUB-PU", "tela_recubierta", si(soporte="tejido", recubrimiento="pu"), ["590320"], "Fabric coated with polyurethane → 5903.20"),
        R("R-NE-MP-RECUB-OPL", "tela_recubierta", si(soporte="tejido", recubrimiento="otro_plastico"), ["590390"],
          "Fabric coated with other plastics → 5903.90"),
        R("R-NE-MP-RECUB-CAU", "tela_recubierta", si(soporte="tejido", recubrimiento="caucho"), ["590691", "590699"],
          "Rubberized fabric → 59.06 (5906.91 if knitted)"),
        R("R-NE-MP-RECUB-OTRO", "tela_recubierta", si(soporte="tejido", recubrimiento="otro"), ["590700"], "Fabric otherwise coated → 5907.00"),
        R("R-NE-MP-RECUB-SINSOP", "tela_recubierta", si(soporte="sin_soporte"), ["3921"],
          "Plastic sheet where the textile only reinforces it → 39.21 (chapter 59 Note 2)"),
        R("R-NE-MP-RECUB-NOTEJ", "tela_recubierta", si(soporte="no_tejido"), ["5603", "3921"],
          "Coated nonwoven → 56.03, or 39.21 if the plastic gives it its character", revision=True),
        R("R-NE-MP-CINTA-ELAST", "cinta_etiqueta", si(tipo_cinta="elastico"), ["580620"],
          "Narrow woven fabric with 5 % or more elastomeric yarn → 5806.20"),
        R("R-NE-MP-CINTA-VELCRO", "cinta_etiqueta", si(tipo_cinta="velcro"), ["580610"], "Hook-and-loop and pile narrow fabrics → 5806.10"),
        R("R-NE-MP-CINTA-OTRA", "cinta_etiqueta", si(tipo_cinta="cinta"), efecto="Other narrow woven fabrics → 5806.3x by fiber", por="fibra",
          mapa={"algodon": "580631", "sintetica": "580632", "artificial": "580632", "lana": "580639", "seda": "580639", "vegetal": "580639",
                "otra": "580639", "cuero": "580639", "": "58063"}),
        R("R-NE-MP-ETQ-TEJ", "cinta_etiqueta", si(tipo_cinta="etiqueta_tejida"), ["580710"], "Woven textile labels and badges → 5807.10"),
        R("R-NE-MP-ETQ-TEX", "cinta_etiqueta", si(tipo_cinta="etiqueta_textil"), ["580790"], "Other textile labels → 5807.90"),
        R("R-NE-MP-ETQ-PAP-IMP", "cinta_etiqueta", si(tipo_cinta="etiqueta_papel", impresa=True), ["482110"], "Printed paper labels and tags → 4821.10"),
        R("R-NE-MP-ETQ-PAP", "cinta_etiqueta", si(tipo_cinta="etiqueta_papel", impresa=False), ["482190"], "Other paper labels → 4821.90"),
        R("R-NE-MP-ENCAJE", "cinta_etiqueta", si(tipo_cinta="encaje"), ["5804"], "Lace → 58.04"),
        R("R-NE-MP-TRENZA", "cinta_etiqueta", si(tipo_cinta="trenza"), ["5808"], "Braids and ornamental trimmings in the piece → 58.08"),
        R("R-NE-MP-BORDADO", "cinta_etiqueta", si(tipo_cinta="bordado"), ["5810"], "Embroidery in the piece, strips or motifs → 58.10"),
    ]
    # Avíos
    reglas += [R(f"R-NE-MP-AVIO-{k.upper()}", "avio", si(tipo_avio=k), [c], t) for k, c, t in (
        ("cierre_metal", "960711", "Zipper with base metal teeth → 9607.11"), ("cierre_otro", "960719", "Other zippers → 9607.19"),
        ("cierre_parte", "960720", "Parts of zippers → 9607.20"), ("broche_presion", "960610", "Press-fasteners and snaps → 9606.10"),
        ("boton_plastico", "960621", "Plastic buttons → 9606.21"), ("boton_metal", "960622", "Base metal buttons → 9606.22"),
        ("boton_otro", "960629", "Other buttons → 9606.29"), ("gancho_ojete", "830810", "Hooks, eyes and eyelets of base metal → 8308.10"),
        ("remache", "830820", "Tubular or bifurcated rivets → 8308.20"), ("hebilla", "830890", "Buckles and other base metal fasteners → 8308.90"),
        ("plastico", "392690", "Plastic buckles and cord locks → 3926.90"))]
    # Plástico
    resinas = {"polietileno": ["3901"], "eva": ["390130"], "polipropileno": ["3902"], "poliestireno": ["3903"], "pvc": ["3904"],
               "acrilico": ["3906"], "poliester": ["3907"], "poliamida": ["3908"], "poliuretano": ["390950"], "silicona": ["3910"],
               "otro": partidas("3905", "3914")}
    reglas += [R(f"R-NE-MP-RESINA-{k.upper()}", "resina_plastica", si(polimero=k), v, f"{k} in primary forms → {', '.join(v)} (chapter 39 Note 6)")
               for k, v in resinas.items()]
    laminas = {"polietileno": ["392010"], "eva": ["392010"], "polipropileno": ["392020"], "poliestireno": ["392030"], "pvc": ["39204"],
               "acrilico": ["39205"], "poliester": ["39206"], "poliamida": ["392092"], "poliuretano": ["392099"], "silicona": ["392099"],
               "otro": ["3920"]}
    reglas += [R(f"R-NE-MP-LAMINA-{k.upper()}", "lamina_plastica", si(polimero=k, autoadhesiva=False, celular=False, reforzada=False), v,
                 f"Non-cellular, unreinforced plastic sheet of {k} → {', '.join(v)}") for k, v in laminas.items()]
    reglas += [
        R("R-NE-MP-LAMINA-AUTOAD", "lamina_plastica", si(autoadhesiva=True), ["3919"], "Self-adhesive plastic sheet or tape → 39.19"),
        R("R-NE-MP-LAMINA-CEL", "lamina_plastica", si(autoadhesiva=False, celular=True), ["39211"], "Cellular plastic sheet (foam) → 3921.1x"),
        R("R-NE-MP-LAMINA-REF", "lamina_plastica", si(autoadhesiva=False, celular=False, reforzada=True), ["392190"],
          "Reinforced or laminated plastic sheet → 3921.90"),
    ]
    # Caucho
    reglas += [R(f"R-NE-MP-CAUCHO-{k.upper()}", "caucho", si(forma_caucho=k), v, t) for k, v, t in (
        ("natural", ["4001"], "Natural rubber in primary forms → 40.01"), ("sintetico", ["4002"], "Synthetic rubber → 40.02 (chapter 40 Note 4)"),
        ("mezcla", ["4005"], "Compounded rubber, unvulcanized → 40.05 (chapter 40 Note 5)"),
        ("lamina_celular", ["400811"], "Cellular rubber sheet → 4008.11"), ("lamina", ["400821"], "Non-cellular rubber sheet → 4008.21"),
        ("perfil", ["400819", "400829"], "Rubber rods and profiles → 4008.19/29"))]
    # Cuero
    curtido = {"bovino": {"humedo": ["41041"], "crust": ["41044"], "terminado": ["4107"]},
               "ovino": {"humedo": ["410510"], "crust": ["410530"], "terminado": ["411200"]},
               "caprino": {"humedo": ["410621"], "crust": ["410622"], "terminado": ["411310"]},
               "porcino": {"humedo": ["410631"], "crust": ["410632"], "terminado": ["411320"]},
               "reptil": {"humedo": ["410640"], "crust": ["410640"], "terminado": ["411330"]},
               "otro": {"humedo": ["410691"], "crust": ["410692"], "terminado": ["411390"]}}
    for a, estados in curtido.items():
        for e, v in estados.items():
            reglas.append(R(f"R-NE-MP-CUERO-{a.upper()}-{e.upper()}", "cuero", si(animal=a, estado_cuero=e), v,
                            f"{a.capitalize()} leather, {e} → {', '.join(v)} (chapter 41)"))
    reglas += [
        R("R-NE-MP-CUERO-AGAM", "cuero", si(estado_cuero="agamuzado"), ["411410"], "Chamois leather → 4114.10"),
        R("R-NE-MP-CUERO-CHAROL", "cuero", si(estado_cuero="charol"), ["411420"], "Patent and metallized leather → 4114.20"),
        R("R-NE-MP-CUERO-REGEN", "cuero", si(estado_cuero="regenerado"), ["411510"],
          "Composition leather (chapter 41 Note 3) → 4115.10"),
        R("R-NE-MP-SINT-TEJ-PVC", "cuero_sintetico", si(soporte="tejido", recubrimiento="pvc"), ["590310"],
          "Synthetic leather of PVC on fabric → 5903.10"),
        R("R-NE-MP-SINT-TEJ-PU", "cuero_sintetico", si(soporte="tejido", recubrimiento="pu"), ["590320"], "Synthetic leather of PU on fabric → 5903.20"),
        R("R-NE-MP-SINT-TEJ-OTRO", "cuero_sintetico", si(soporte="tejido", recubrimiento=["otro_plastico", "otro", "caucho"]), ["590390", "590699"],
          "Synthetic leather of other coatings on fabric → 5903.90 / 59.06"),
        R("R-NE-MP-SINT-NOTEJ", "cuero_sintetico", si(soporte="no_tejido"), ["392113", "392112", "392190", "5603"],
          "Synthetic leather on nonwoven or microfiber → 39.21 or 56.03 by which gives the character", revision=True),
        R("R-NE-MP-SINT-SIN", "cuero_sintetico", si(soporte="sin_soporte"), ["3921", "3920"], "Plastic sheet imitating leather → 39.20/39.21"),
        # Papel
        R("R-NE-MP-PAPEL-CORR", "papel_carton", si(tipo_papel="caja_corrugada"), ["481910"], "Boxes of corrugated paperboard → 4819.10"),
        R("R-NE-MP-PAPEL-PLEG", "papel_carton", si(tipo_papel="caja_plegable"), ["481920"], "Folding boxes of non-corrugated board → 4819.20"),
        R("R-NE-MP-PAPEL-BOLSA", "papel_carton", si(tipo_papel="bolsa"), ["481930", "481940"], "Paper sacks and bags → 4819.30/40"),
        R("R-NE-MP-PAPEL-ROLLO", "papel_carton", si(tipo_papel="papel"), partidas("4801", "4811"),
          "Paper and paperboard in rolls or sheets → 48.01–48.11 (the text finds the heading)"),
    ]
    metales = {"acero": {"lamina": partidas("7208", "7212") + partidas("7219", "7220"), "alambre": ["7217", "7223"], "barra": partidas("7213", "7216")},
               "aluminio": {"lamina": ["7606", "7607"], "alambre": ["7605"], "barra": ["7604"]},
               "cobre": {"lamina": ["7409", "7410"], "alambre": ["7408"], "barra": ["7407"]}}
    for m, formas in metales.items():
        for f, v in formas.items():
            reglas.append(R(f"R-NE-MP-METAL-{m.upper()}-{f.upper()}", "metal", si(metal_base=m, forma_metal=f), v, f"{m} {f} → {', '.join(v)}"))
    casos = [
        caso("tejido_plano", "5209", **{"comp.material": "100% cotton"}, predominio85=True, peso_g_m2=380),
        caso("tejido_plano", "5407", **{"comp.material": "100% nylon ripstop"}, filamento="filamento"),
        caso("tejido_punto", "6005", **{"comp.material": "100% polyester mesh"}, tipo_punto="urdimbre"),
        caso("tejido_punto", "6001", **{"comp.material": "100% polyester"}, tipo_punto="pelo"),
        caso("hilado", "5401", **{"comp.material": "100% polyester"}, uso_hilado="hilo_coser", filamento="filamento"),
        caso("hilado", "5205", **{"comp.material": "100% cotton"}, uso_hilado="industrial", predominio85=True),
        caso("no_tejido", "560313", **{"comp.material": "100% polypropylene"}, tipo_no_tejido="filamentos", peso_g_m2=100),
        caso("tela_recubierta", "590320", **{"comp.material": "100% polyester"}, soporte="tejido", recubrimiento="pu"),
        caso("cinta_etiqueta", "580620", tipo_cinta="elastico"),
        caso("cinta_etiqueta", "580710", tipo_cinta="etiqueta_tejida"),
        caso("cinta_etiqueta", "482110", tipo_cinta="etiqueta_papel", impresa=True),
        caso("avio", "960719", tipo_avio="cierre_otro"),
        caso("avio", "830810", tipo_avio="gancho_ojete"),
        caso("resina_plastica", "390130", polimero="eva"),
        caso("lamina_plastica", "39211", polimero="poliuretano", autoadhesiva=False, celular=True),
        caso("caucho", "400821", forma_caucho="lamina"),
        caso("cuero", "4107", animal="bovino", estado_cuero="terminado"),
        caso("cuero", "41041", animal="bovino", estado_cuero="humedo"),
        caso("cuero_sintetico", "590320", soporte="tejido", recubrimiento="pu"),
        caso("papel_carton", "481920", tipo_papel="caja_plegable"),
    ]
    return {"dominio": {"codigo": DOM, "nombre": "Raw materials", "orden": 50,
                        "descripcion": "Inputs for making footwear, apparel and accessories: textiles, plastics, rubber, leather, paper, metals and trims.",
                        "capitulos": [{"capitulo": c, "relevancia": "PRIMARY"} for c in
                                      ("39", "40", "41", "48", "50", "51", "52", "53", "54", "55", "56", "58", "59", "60", "83", "96")]
                        + [{"capitulo": c, "relevancia": "SECONDARY"} for c in ("72", "74", "76")]},
            "fuente": NE, "categorias": cats, "atributos": atrs, "ambitos_comunes": comunes, "reglas": reglas, "casos": casos}
