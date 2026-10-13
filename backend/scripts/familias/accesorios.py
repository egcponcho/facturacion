"""Accesorios: bolsos y marroquinería (42.02), cinturones y guantes (42.03, 61.16,
62.16, 39.26, 40.15), bufandas, pañuelos y corbatas (61.17, 62.13–62.15),
sombrerería (capítulo 65), paraguas (66.01), bisutería (71.17), relojes (91.02,
91.13), lentes de sol (90.04) y accesorios para el cabello (96.15).

- 42.02: la primera parte del texto (maletas, maletines, portafolios) admite
  cualquier materia; la segunda (bolsos, billeteras, mochilas, bolsas de viaje)
  solo cuero, hojas de plástico, textil, fibra vulcanizada o cartón. La
  subpartida la decide la superficie exterior (cuero; hojas de plástico o
  textil; las demás). El cuero sintético es hoja de plástico.
- Nota 3 del capítulo 42: guantes (incluidos los de deporte), cinturones y
  bandoleras de cuero son complementos de la 42.03; las correas de reloj no (91.13).
- Nota 7 del 62: un pañuelo de cuello cuadrado de lado no mayor a 60 cm es pañuelo de bolsillo (62.13).
- Capítulo 65: de punto o de tela en pieza 65.05; trenzado o de tiras 65.04;
  cascos de seguridad 65.06.10; de caucho o plástico 65.06.91 (65.03 ya no existe).
"""
from base import ambitos, atributo, caso, categoria, cond, opcion, por_fibra, regla, si

DOM = "ACCESSORIES"
NE = "Explanatory Notes, chapters 42, 61, 62, 65, 66, 71, 90, 91 and 96"
BOLSOS = {"maleta": "42021", "bolso_mano": "42022", "articulo_bolsillo": "42023", "mochila": "42029", "bolso_viaje": "42029"}
SUP = {"cuero": "1", "plastico": "2", "textil": "2", "otro": "9"}


def familia() -> dict:
    g_bolsos = "Bags and leather goods"
    g_vestir = "Clothing accessories"
    g_otros = "Watches, eyewear and jewelry"
    plant_clase = {"material": "DE {clase}", "clase": ["material"]}
    plant_sup = {"material": "CON SUPERFICIE EXTERIOR DE {superficie_exterior}", "requiere": ["superficie_exterior"],
                 "como": {"superficie_exterior": {"cuero": "CUERO", "plastico": "PLÁSTICO", "textil": "MATERIA TEXTIL", "otro": "OTRAS MATERIAS"}}}
    cats = [
        categoria("maleta", "Suitcase, trolley, briefcase, attaché or vanity case", corto="Suitcase or briefcase", aduana="Maleta", grupo=g_bolsos,
                  dominio=DOM, capitulos=["42"], orden=10, prioridad=30,
                  re_=r"\b(suitcases?|maletas?|trolleys?|luggage|equipaje|carry-?on|briefcases?|maletines?|portafolios?|attache|vanity cases?)\b",
                  alias="maleta trolley maletín portafolio", plantilla=plant_sup),
        categoria("bolso_mano", "Handbag, shoulder bag, crossbody or clutch", corto="Handbag", aduana="Bolso de mano", grupo=g_bolsos, dominio=DOM,
                  capitulos=["42"], orden=20, prioridad=31,
                  re_=r"\b(handbags?|bolsos? de mano|carteras?|purses?|shoulder bags?|crossbody|bandoleras?|clutch(es)?|satchels?|hobo bags?)\b",
                  alias="bolso cartera crossbody clutch", plantilla=plant_sup),
        categoria("articulo_bolsillo", "Wallet, coin purse, card holder, key case or glasses case", corto="Wallet", aduana="Billetera",
                  grupo=g_bolsos, dominio=DOM, capitulos=["42"], orden=30, prioridad=29,
                  re_=r"\b(wallets?|billeteras?|carteras? de bolsillo|coin purses?|monederos?|card ?holders?|tarjeteros?|key cases?|llaveros? de cuero|"
                      r"glasses cases?|estuches? para (gafas|lentes)|passport (holders?|covers?))\b",
                  alias="billetera monedero tarjetero estuche de lentes", plantilla=plant_sup),
        categoria("mochila", "Backpack", corto="Backpack", aduana="Mochila", grupo=g_bolsos, dominio=DOM, capitulos=["42"], orden=40, prioridad=27,
                  re_=r"\b(backpacks?|mochilas?|daypacks?|rucksacks?|bookbags?)\b", alias="mochila backpack", plantilla=plant_sup),
        categoria("bolso_viaje", "Travel, duffel, sports, tote, toiletry, belt or cooler bag; cases", corto="Bag or case", aduana="Bolso",
                  grupo=g_bolsos, dominio=DOM, capitulos=["42"], orden=50, prioridad=26,
                  re_=r"\b(duffels?|duffle|travel bags?|bolsos? de viaje|gym bags?|sports? bags?|totes?|tote bags?|toiletry bags?|neceser|"
                      r"belt bags?|waist bags?|fanny packs?|canguros?|riñoneras?|cooler bags?|loncheras?|lunch bags?|camera (bags?|cases?)|"
                      r"laptop (bags?|sleeves?)|pouch(es)?|cosmetiqueras?)\b",
                  alias="bolso de viaje maletín deportivo tote neceser canguro lonchera funda", plantilla=plant_sup),
        categoria("cinturon", "Belt", corto="Belt", aduana="Cinturón", grupo=g_vestir, dominio=DOM, capitulos=["42", "61", "62", "39", "71"], orden=60,
                  prioridad=39, re_=r"\b(belts?|cinturon(es)?|cinchos?|correas? de vestir)\b", alias="cinturón cincho", plantilla=plant_clase),
        categoria("guantes", "Gloves, mittens or mitts", corto="Gloves", aduana="Guantes", grupo=g_vestir, dominio=DOM,
                  capitulos=["42", "61", "62", "39", "40"], orden=70, prioridad=37, re_=r"\b(gloves?|guantes?|mittens?|manoplas?|mitones?)\b",
                  alias="guantes manoplas", plantilla=plant_clase),
        categoria("bufanda", "Scarf, shawl, neck warmer, bandana or veil", corto="Scarf", aduana="Bufanda", grupo=g_vestir, dominio=DOM,
                  capitulos=["61", "62"], orden=80, prioridad=36,
                  re_=r"\b(scarf|scarves|bufandas?|shawls?|chales?|neck (gaiters?|warmers?)|cuellos?|bandanas?|panuelos? de cuello|veils?|velos?|"
                      r"pashminas?|foulards?)\b", alias="bufanda chal bandana pañuelo de cuello",
                  plantilla={"material": "DE {fibra}", "requiere": ["fibra"], "como": {"fibra": {"cuero": "CUERO", "*": "TEXTIL"}}}),
        categoria("corbata", "Tie, bow tie or cravat", corto="Tie", aduana="Corbata", grupo=g_vestir, dominio=DOM, capitulos=["61", "62"], orden=90,
                  prioridad=35, re_=r"\b(ties|neck ?ties?|corbatas?|bow ?ties?|corbatines?|cravats?)\b", alias="corbata corbatín",
                  plantilla={"material": "DE {fibra}", "requiere": ["fibra"], "como": {"fibra": {"cuero": "CUERO", "*": "TEXTIL"}}}),
        categoria("panuelo", "Pocket handkerchief", corto="Handkerchief", aduana="Pañuelo", grupo=g_vestir, dominio=DOM, capitulos=["62", "61"],
                  orden=100, prioridad=30, re_=r"\b(handkerchiefs?|panuelos?( de bolsillo)?|pocket squares?)\b", alias="pañuelo",
                  plantilla={"material": "DE {fibra}", "requiere": ["fibra"], "como": {"fibra": {"cuero": "CUERO", "*": "TEXTIL"}}}),
        categoria("gorra", "Cap, hat, beanie or helmet", corto="Cap or hat", aduana="Gorra", grupo=g_vestir, dominio=DOM, capitulos=["65"],
                  orden=110, prioridad=40,
                  re_=r"\b(caps?|hats?|beanies?|gorras?|gorros?|sombreros?|bucket hats?|truckers?|visors?|viseras?|balaclavas?|pasamontanas|"
                      r"helmets?|cascos?|boinas?|berets?|headwear)\b", alias="gorra sombrero gorro boina casco", plantilla=plant_clase),
        categoria("paraguas", "Umbrella or sunshade", corto="Umbrella", aduana="Paraguas", grupo=g_vestir, dominio=DOM, capitulos=["66"],
                  orden=120, prioridad=34, re_=r"\b(umbrellas?|paraguas|sombrillas?|parasols?|quitasoles?)\b", alias="paraguas sombrilla"),
        categoria("bisuteria", "Imitation jewelry: necklace, earrings, bracelet, ring, cufflinks", corto="Jewelry", aduana="Bisutería",
                  grupo=g_otros, dominio=DOM, capitulos=["71"], orden=130, prioridad=33,
                  re_=r"\b(jewel(le)?ry|bisuteria|necklaces?|collares?|earrings?|aretes?|aros|pendientes|bracelets?|pulseras?|rings?|anillos?|"
                      r"cufflinks?|gemelos|brooches?|broches?|pins?|charms?|dijes?)\b", alias="bisutería collar aretes pulsera anillo gemelos",
                  plantilla=plant_clase),
        categoria("reloj", "Wrist watch", corto="Watch", aduana="Reloj de pulsera", grupo=g_otros, dominio=DOM, capitulos=["91", "85"], orden=140,
                  prioridad=33, re_=r"\b(watch(es)?|relojes?|smartwatch(es)?|timepieces?)\b", alias="reloj smartwatch"),
        categoria("correa_reloj", "Watch strap or bracelet", corto="Watch strap", aduana="Correa para reloj", grupo=g_otros, dominio=DOM,
                  capitulos=["91"], orden=150, prioridad=22, re_=r"\b(watch ?(straps?|bands?|bracelets?)|correas? (de|para) reloj|extensibles? de reloj)\b",
                  alias="correa de reloj extensible", plantilla=plant_clase),
        categoria("lentes", "Sunglasses or other glasses (not corrective)", corto="Sunglasses", aduana="Anteojos", grupo=g_otros, dominio=DOM,
                  capitulos=["90"], orden=160, prioridad=32, re_=r"\b(sunglasses|lentes de sol|gafas( de sol)?|anteojos|goggles|shades|eyewear)\b",
                  alias="lentes de sol gafas anteojos goggles"),
        categoria("accesorio_pelo", "Hair accessory: clip, comb, hairband, scrunchie, hairpin", corto="Hair accessory", aduana="Accesorio para el cabello",
                  grupo=g_vestir, dominio=DOM, capitulos=["96", "61", "62"], orden=170, prioridad=25,
                  re_=r"\b(hair ?(clips?|ties?|bands?|pins?|slides?|accessor(y|ies))|scrunchies?|headbands?|diademas?|vinchas?|combs?|peines?|"
                      r"peinetas?|pasadores?|horquillas?|ganchos? (para el )?pelo|colitas?|bobby pins?)\b",
                  alias="pasador diadema peine colita scrunchie", plantilla=plant_clase),
    ]
    atrs = [
        atributo("superficie_exterior", "Material of the outer surface", "select", [
            opcion("cuero", "Natural leather (including patent or regenerated leather)"),
            opcion("plastico", "Plastic sheeting (includes synthetic leather and PU)"),
            opcion("textil", "Textile"), opcion("otro", "Other (paperboard, vulcanized fiber, wood, metal, straw)")],
            ambitos(list(BOLSOS)), seccion="composicion", derivacion={"modo": "material", "parte": "exterior", "lectura": "superficie"}, orden=170,
            ayuda="Subheadings of 42.02: the material of the outer surface. Leather with a thin, invisible plastic coating is still leather."),
        atributo("deporte_guante", "Designed specially for sport (e.g. boxing, hockey, golf, cycling)", "boolean", [],
                 ambitos(["guantes"], condicion=[cond("material", "cuero")]), defecto="false", orden=200,
                 patrones=[{"re": r"\b(boxing|box|golf|hockey|cycling|ciclismo|baseball|beisbol|goalkeeper|portero|batting)\b", "en": "todo"}],
                 ayuda="Subheading 4203.21: gloves with a functional design for the sport."),
        atributo("guante_recubierto", "Impregnated, coated or covered with plastics or rubber", "boolean", [],
                 ambitos(["guantes"], condicion=[cond("material", "textil"), cond("tejido", "punto")]), defecto="false", orden=210,
                 patrones=[{"re": r"\b(nitrile|nitrilo|latex|pu (coated|palm)|coated|recubiert[oa]s?)\b", "en": "todo"}]),
        atributo("guante_medico", "For medical, surgical, dental or veterinary use", "boolean", [],
                 ambitos(["guantes"], condicion=[cond("material", "plastico")]), defecto="false", orden=215),
        atributo("cuadrado_60", "Square or nearly square, no side over 60 cm", "boolean", [],
                 ambitos(["bufanda"], condicion=[cond("tejido", "plano")]), defecto="false", orden=220,
                 ayuda="Chapter 62 Note 7: such a neck scarf is treated as a pocket handkerchief (62.13)."),
        atributo("tipo_tocado", "How it is made", "select", [
            opcion("tela", "Knitted, or made up of fabric, felt or lace in the piece (caps, beanies, bucket hats)", defecto=True,
                   re_=r"\b(caps?|gorras?|beanies?|gorros?|bucket|truckers?|baseball|knit|tejid[oa]|boinas?|balaclavas?)\b", prioridad=5),
            opcion("trenzado", "Plaited or made by assembling strips (straw hats)", re_=r"\b(straw|paja|panama|raffia|rafia|plaited|trenzad[oa])\b",
                   prioridad=3),
            opcion("casco", "Safety helmet", re_=r"\b(safety helmets?|cascos? de seguridad|hard hats?|helmets?|cascos?)\b", prioridad=2),
            opcion("caucho_plastico", "Of rubber or plastics (e.g. shower or swim caps)", re_=r"\b(shower caps?|swim caps?|gorros? de (bano|natacion))\b",
                   prioridad=2),
            opcion("otro", "Of other materials (leather, fur)")],
            ambitos(["gorra"], "REQUIRE"), orden=230, ayuda="Chapter 65: the construction decides the heading, not the style."),
        atributo("forma_tocado", "Shape", "select", [
            opcion("gorra", "Cap with a visor", re_=r"\b(caps?|gorras?|truckers?|baseball|snapback|visors?|viseras?)\b", defecto=True),
            opcion("sombrero", "Hat with a brim all around", re_=r"\b(hats?|sombreros?|bucket|fedora|panama)\b", prioridad=5),
            opcion("gorro", "Beanie, beret or hood without a brim", re_=r"\b(beanies?|gorros?|boinas?|berets?|balaclavas?)\b", prioridad=4)],
            ambitos(["gorra"]), seccion="nacional", orden=235,
            ayuda="Some countries split their national codes between hats and caps."),
        atributo("tipo_paraguas", "Type", "select", [
            opcion("jardin", "Garden, beach or market umbrella (sunshade)", re_=r"\b(garden|patio|beach|playa|jardin|market|parasol|toldo)\b"),
            opcion("telescopico", "Telescopic shaft (folding)", re_=r"\b(folding|plegable|compact|telescop\w*|travel|mini)\b", defecto=True),
            opcion("otro", "Other (fixed shaft, walking-stick umbrella)", re_=r"\b(golf|stick|baston|recto)\b")],
            ambitos(["paraguas"], "REQUIRE"), orden=240),
        atributo("material_bisuteria", "Material", "select", [
            opcion("metal_comun", "Base metal, even plated with silver, gold or platinum",
                   re_=r"\b(brass|laton|zinc|alloy|aleacion|stainless|acero|copper|cobre|plated|banad[oa]|bronce)\b"),
            opcion("metal_precioso", "Precious metal or clad with precious metal (jewelry, not imitation)",
                   re_=r"\b(sterling|plata 925|925|gold 14k|oro (de )?\d{2}k|18k|14k|10k|platinum)\b", prioridad=5),
            opcion("otra", "Other (plastic, glass, wood, leather, textile)")],
            ambitos(["bisuteria"], "REQUIRE"), orden=250),
        atributo("gemelos", "Cufflinks or studs", "boolean", [], ambitos(["bisuteria"], condicion=[cond("material_bisuteria", "metal_comun")]),
                 defecto="false", orden=255, patrones=[{"re": r"\b(cufflinks?|gemelos|mancuernillas?)\b", "en": "todo"}]),
        atributo("reloj_inteligente", "Smartwatch (connects to a phone or network)", "boolean", [], ambitos(["reloj"]), defecto="false", orden=260,
                 patrones=[{"re": r"\b(smart ?watch(es)?|reloj inteligente|fitness tracker|bluetooth)\b", "en": "todo"}],
                 ayuda="A smartwatch is a communication apparatus (85.17), not a watch of chapter 91."),
        atributo("reloj_electrico", "Electrically operated (battery or solar)", "boolean", [],
                 ambitos(["reloj"], condicion=[cond("reloj_inteligente", False)]), defecto="true", orden=262,
                 patrones=[{"re": r"\b(quartz|cuarzo|battery|bateria|solar|digital)\b", "en": "todo"}]),
        atributo("pantalla_reloj", "Display", "select", [
            opcion("mecanica", "Hands only (mechanical display)", re_=r"\b(analog|analogico|hands|agujas)\b", defecto=True),
            opcion("digital", "Digital only (optoelectronic)", re_=r"\b(digital|lcd|led)\b"),
            opcion("ambas", "Hands and digital (ana-digi)", re_=r"\b(ana-?digi|analog[- ]digital|dual display)\b", prioridad=5)],
            ambitos(["reloj"], condicion=[cond("reloj_inteligente", False), cond("reloj_electrico", True)]), orden=264),
        atributo("reloj_automatico", "Automatic (self-winding)", "boolean", [],
                 ambitos(["reloj"], condicion=[cond("reloj_inteligente", False), cond("reloj_electrico", False)]), defecto="false", orden=266,
                 patrones=[{"re": r"\b(automatic|automatico|self-?winding)\b", "en": "todo"}]),
        atributo("material_correa", "Material", "select", [
            opcion("metal_precioso", "Precious metal or clad with precious metal"), opcion("metal_comun", "Base metal, even gold- or silver-plated",
                                                                                          re_=r"\b(steel|acero|metal|titanium|titanio)\b"),
            opcion("otro", "Other (leather, rubber, silicone, textile)", defecto=True)],
            ambitos(["correa_reloj"], "REQUIRE"), orden=270),
        atributo("tipo_lentes", "Type", "select", [
            opcion("sol", "Sunglasses", re_=r"\b(sunglasses|lentes de sol|gafas de sol|shades|polarized|polarizad[oa]s?)\b", defecto=True),
            opcion("otros", "Protective or other non-corrective glasses (goggles, safety glasses)",
                   re_=r"\b(goggles|safety glasses|lentes de seguridad|ski goggles|swim goggles)\b", prioridad=5)],
            ambitos(["lentes"], "REQUIRE"), orden=280),
        atributo("tipo_pelo", "Type", "select", [
            opcion("peine", "Comb, hair-slide or similar", re_=r"\b(combs?|peines?|peinetas?|hair ?(clips?|slides?|claws?)|pasadores?|pinzas?|ganchos?)\b"),
            opcion("horquilla", "Hairpin, bobby pin or curler", re_=r"\b(bobby pins?|hair ?pins?|horquillas?|curlers?|rulos?|bigudies)\b"),
            opcion("textil", "Hairband, scrunchie or headband of fabric", re_=r"\b(scrunchies?|headbands?|diademas? de tela|hair ?ties?|colitas?|"
                                                                               r"turbantes?|bandanas?)\b")],
            ambitos(["accesorio_pelo"], "REQUIRE"), orden=290),
    ]
    comunes = {
        "comp.exterior": ambitos(list(BOLSOS) + ["bufanda", "corbata", "panuelo"], "REQUIRE"),
        "comp.material": ambitos(["cinturon", "guantes", "gorra", "bisuteria", "correa_reloj", "accesorio_pelo"], "REQUIRE"),
        "material": ambitos(["cinturon", "guantes", "gorra", "accesorio_pelo"]),
        "fibra": ambitos(["bufanda", "corbata", "panuelo", "guantes"]),
        "tejido": ambitos(["bufanda", "corbata", "panuelo"], "REQUIRE") + ambitos(["cinturon", "guantes", "accesorio_pelo"], "REQUIRE",
                                                                                 condicion=[cond("material", "textil")]),
        "edad": ambitos(["guantes"]),
    }
    R = regla
    reglas = []
    for cat, pref in BOLSOS.items():
        for mat, dig in SUP.items():
            reglas.append(R(f"R-NE-ACC-{cat.upper()}-{mat[:3].upper()}", cat, si(superficie_exterior=mat), [pref + dig],
                            f"{next(c['nombre_corto'] for c in cats if c['codigo'] == cat)}, outer surface "
                            f"{dict(cuero='of leather', plastico='of plastic sheeting', textil='of textile', otro='of other materials')[mat]} "
                            f"→ {pref[:4]}.{pref[4:]}{dig} (heading 42.02 and its subheading notes)"))
    reglas += [
        # Cinturones
        R("R-NE-ACC-CINTURON-CUE", "cinturon", si(material="cuero"), ["420330"], "Leather belt → 4203.30 (chapter 42 Note 3)"),
        R("R-NE-ACC-CINTURON-PU", "cinturon", si(material="textil", tejido="punto"), ["611780"], "Knitted belt → 6117.80"),
        R("R-NE-ACC-CINTURON-PL", "cinturon", si(material="textil", tejido=["plano", "no_tejido"]), ["621710"], "Woven belt → 6217.10"),
        R("R-NE-ACC-CINTURON-PLA", "cinturon", si(material="plastico"), ["392620"], "Plastic belt (incl. synthetic leather) → 3926.20"),
        R("R-NE-ACC-CINTURON-MET", "cinturon", si(material="metal"), ["711719"], "Base metal chain belt worn as jewelry → 7117.19", revision=True),
        # Guantes
        R("R-NE-ACC-GUANTES-BEBEPU", "guantes", si(material="textil", edad="bebe", tejido="punto"), efecto="Knitted baby gloves → 61.11",
          por="fibra", mapa=por_fibra("6111")),
        R("R-NE-ACC-GUANTES-BEBEPL", "guantes", si(material="textil", edad="bebe", tejido=["plano", "no_tejido"]), efecto="Woven baby gloves → 62.09",
          por="fibra", mapa=por_fibra("6209")),
        R("R-NE-ACC-GUANTES-DEP", "guantes", si(material="cuero", deporte_guante=True), ["420321"], "Leather gloves designed for sport → 4203.21"),
        R("R-NE-ACC-GUANTES-CUE", "guantes", si(material="cuero", deporte_guante=False), ["420329"], "Other leather gloves → 4203.29"),
        R("R-NE-ACC-GUANTES-REC", "guantes", si(material="textil", edad_no="bebe", tejido="punto", guante_recubierto=True), ["611610"],
          "Knitted gloves coated with plastics or rubber → 6116.10"),
        R("R-NE-ACC-GUANTES-PU", "guantes", si(material="textil", edad_no="bebe", tejido="punto", guante_recubierto=False),
          efecto="Knitted gloves → 6116.9x by fiber", por="fibra", mapa=por_fibra("61169")),
        R("R-NE-ACC-GUANTES-PL", "guantes", si(material="textil", edad_no="bebe", tejido=["plano", "no_tejido"]), ["621600"],
          "Gloves of fabric, not knitted → 6216.00"),
        R("R-NE-ACC-GUANTES-MED", "guantes", si(material="plastico", guante_medico=True), ["401512"],
          "Rubber gloves for medical, surgical, dental or veterinary use → 4015.12"),
        R("R-NE-ACC-GUANTES-PLA", "guantes", si(material="plastico", guante_medico=False), ["392620", "401519"],
          "Gloves of plastics → 3926.20; of vulcanized rubber → 4015.19 (say which)"),
        # Bufandas, pañuelos, corbatas
        R("R-NE-ACC-BUFANDA-PU", "bufanda", si(tejido="punto"), ["611710"], "Knitted scarf or shawl → 6117.10"),
        R("R-NE-ACC-BUFANDA-CUA", "bufanda", si(tejido="plano", cuadrado_60=True), efecto="Square scarf, no side over 60 cm → 62.13 (chapter 62 Note 7)",
          por="fibra", mapa=por_fibra("6213")),
        R("R-NE-ACC-BUFANDA-PL", "bufanda", si(tejido=["plano", "no_tejido"], cuadrado_60_no=True), efecto="Woven scarf or shawl → 62.14 by fiber",
          por="fibra", mapa=por_fibra("6214")),
        R("R-NE-ACC-CORBATA-PU", "corbata", si(tejido="punto"), ["611780"], "Knitted tie → 6117.80 (6117.20 no longer exists)"),
        R("R-NE-ACC-CORBATA-PL", "corbata", si(tejido=["plano", "no_tejido"]), efecto="Woven tie → 62.15 by fiber", por="fibra", mapa=por_fibra("6215")),
        R("R-NE-ACC-PANUELO-PU", "panuelo", si(tejido="punto"), ["611780"], "Knitted handkerchief → 6117.80"),
        R("R-NE-ACC-PANUELO-PL", "panuelo", si(tejido=["plano", "no_tejido"]), efecto="Handkerchief → 62.13 by fiber", por="fibra",
          mapa=por_fibra("6213")),
        # Sombrerería
        R("R-NE-ACC-GORRA-TELA", "gorra", si(tipo_tocado="tela"), ["650500"], "Hat of knitted or fabric in the piece → 6505.00 (heading 65.05)"),
        R("R-NE-ACC-GORRA-TREN", "gorra", si(tipo_tocado="trenzado"), ["650400"], "Plaited hat or made of strips → 6504.00"),
        R("R-NE-ACC-GORRA-CASCO", "gorra", si(tipo_tocado="casco"), ["650610"], "Safety helmet → 6506.10"),
        R("R-NE-ACC-GORRA-PLA", "gorra", si(tipo_tocado="caucho_plastico"), ["650691"], "Headgear of rubber or plastics → 6506.91"),
        R("R-NE-ACC-GORRA-OTRO", "gorra", si(tipo_tocado="otro"), ["650699"], "Headgear of other materials → 6506.99"),
        # Paraguas
        R("R-NE-ACC-PARAGUAS-JAR", "paraguas", si(tipo_paraguas="jardin"), ["660110"], "Garden or similar umbrellas → 6601.10"),
        R("R-NE-ACC-PARAGUAS-TEL", "paraguas", si(tipo_paraguas="telescopico"), ["660191"], "Umbrella with a telescopic shaft → 6601.91"),
        R("R-NE-ACC-PARAGUAS-OTRO", "paraguas", si(tipo_paraguas="otro"), ["660199"], "Other umbrellas → 6601.99"),
        # Bisutería
        R("R-NE-ACC-BISU-GEM", "bisuteria", si(material_bisuteria="metal_comun", gemelos=True), ["711711"], "Base metal cufflinks and studs → 7117.11"),
        R("R-NE-ACC-BISU-MET", "bisuteria", si(material_bisuteria="metal_comun", gemelos=False), ["711719"], "Other base metal imitation jewelry → 7117.19"),
        R("R-NE-ACC-BISU-OTRA", "bisuteria", si(material_bisuteria="otra"), ["711790"], "Imitation jewelry of other materials → 7117.90"),
        R("R-NE-ACC-BISU-PREC", "bisuteria", si(material_bisuteria="metal_precioso"), ["7113"],
          "Of precious metal it is jewelry, not imitation jewelry → 71.13", revision=True),
        # Relojes
        R("R-NE-ACC-RELOJ-SMART", "reloj", si(reloj_inteligente=True), ["851762"], "Smartwatch → 8517.62 (communication apparatus)", revision=True),
        R("R-NE-ACC-RELOJ-MEC", "reloj", si(reloj_inteligente=False, reloj_electrico=True, pantalla_reloj="mecanica"), ["910211"],
          "Electric wrist watch with mechanical display only → 9102.11"),
        R("R-NE-ACC-RELOJ-DIG", "reloj", si(reloj_inteligente=False, reloj_electrico=True, pantalla_reloj="digital"), ["910212"],
          "Electric wrist watch with optoelectronic display only → 9102.12"),
        R("R-NE-ACC-RELOJ-AMB", "reloj", si(reloj_inteligente=False, reloj_electrico=True, pantalla_reloj="ambas"), ["910219"],
          "Other electric wrist watches → 9102.19"),
        R("R-NE-ACC-RELOJ-AUTO", "reloj", si(reloj_inteligente=False, reloj_electrico=False, reloj_automatico=True), ["910221"],
          "Automatic (self-winding) wrist watch → 9102.21"),
        R("R-NE-ACC-RELOJ-CUERDA", "reloj", si(reloj_inteligente=False, reloj_electrico=False, reloj_automatico=False), ["910229"],
          "Other mechanical wrist watches → 9102.29"),
        R("R-NE-ACC-CORREA-PREC", "correa_reloj", si(material_correa="metal_precioso"), ["911310"], "Watch strap of precious metal → 9113.10"),
        R("R-NE-ACC-CORREA-MET", "correa_reloj", si(material_correa="metal_comun"), ["911320"], "Watch strap of base metal → 9113.20"),
        R("R-NE-ACC-CORREA-OTRO", "correa_reloj", si(material_correa="otro"), ["911390"], "Watch strap of other materials → 9113.90"),
        # Lentes y cabello
        R("R-NE-ACC-LENTES-SOL", "lentes", si(tipo_lentes="sol"), ["900410"], "Sunglasses → 9004.10"),
        R("R-NE-ACC-LENTES-OTROS", "lentes", si(tipo_lentes="otros"), ["900490"], "Other glasses and goggles → 9004.90"),
        R("R-NE-ACC-PELO-PEINEPL", "accesorio_pelo", si(tipo_pelo="peine", material="plastico"), ["961511"],
          "Combs and hair-slides of hard rubber or plastics → 9615.11"),
        R("R-NE-ACC-PELO-PEINEOT", "accesorio_pelo", si(tipo_pelo="peine", material_no="plastico"), ["961519"],
          "Combs and hair-slides of other materials → 9615.19"),
        R("R-NE-ACC-PELO-HORQ", "accesorio_pelo", si(tipo_pelo="horquilla"), ["961590"], "Hairpins, curling pins and curlers → 9615.90"),
        R("R-NE-ACC-PELO-TEXPU", "accesorio_pelo", si(tipo_pelo="textil", tejido="punto"), ["611780"], "Knitted hairband or headband → 6117.80"),
        R("R-NE-ACC-PELO-TEXPL", "accesorio_pelo", si(tipo_pelo="textil", tejido=["plano", "no_tejido"]), ["621710"], "Woven hairband → 6217.10"),
    ]
    casos = [
        caso("mochila", "420292", **{"comp.exterior": "100% polyester"}),
        caso("mochila", "420291", **{"comp.exterior": "100% leather"}),
        caso("bolso_mano", "420222", **{"comp.exterior": "PU synthetic leather"}),
        caso("bolso_mano", "420221", **{"comp.exterior": "cowhide leather"}),
        caso("articulo_bolsillo", "420231", **{"comp.exterior": "leather"}),
        caso("maleta", "420212", **{"comp.exterior": "polycarbonate"}),
        caso("bolso_viaje", "420292", **{"comp.exterior": "nylon"}),
        caso("cinturon", "420330", **{"comp.material": "leather"}),
        caso("cinturon", "621710", **{"comp.material": "100% polyester webbing"}, tejido="plano"),
        caso("guantes", "611693", **{"comp.material": "100% polyester"}, tejido="punto", guante_recubierto=False, **{"comp.exterior": "100% polyester"}),
        caso("guantes", "420321", **{"comp.material": "leather"}, deporte_guante=True),
        caso("bufanda", "611710", **{"comp.exterior": "100% acrylic"}, tejido="punto"),
        caso("bufanda", "621420", **{"comp.exterior": "100% wool"}, tejido="plano", cuadrado_60=False),
        caso("corbata", "621510", **{"comp.exterior": "100% silk"}, tejido="plano"),
        caso("gorra", "650500", **{"comp.material": "100% cotton"}, tipo_tocado="tela"),
        caso("gorra", "650400", **{"comp.material": "paper straw"}, tipo_tocado="trenzado"),
        caso("paraguas", "660191", tipo_paraguas="telescopico"),
        caso("bisuteria", "711719", **{"comp.material": "zinc alloy"}, material_bisuteria="metal_comun", gemelos=False),
        caso("reloj", "910211", reloj_inteligente=False, reloj_electrico=True, pantalla_reloj="mecanica"),
        caso("reloj", "910221", reloj_inteligente=False, reloj_electrico=False, reloj_automatico=True),
        caso("correa_reloj", "911390", **{"comp.material": "silicone"}, material_correa="otro"),
        caso("lentes", "900410", tipo_lentes="sol"),
        caso("accesorio_pelo", "961511", **{"comp.material": "plastic"}, tipo_pelo="peine"),
    ]
    return {"dominio": {"codigo": DOM, "nombre": "Accessories", "orden": 30,
                        "descripcion": "Bags and leather goods, belts, gloves, scarves, ties, headwear, umbrellas, imitation jewelry, watches, "
                                       "sunglasses and hair accessories.",
                        "capitulos": [{"capitulo": c, "relevancia": "PRIMARY"} for c in ("42", "65", "66", "71", "91")]
                        + [{"capitulo": c, "relevancia": "SECONDARY"} for c in ("61", "62", "39", "40", "85", "90", "96")]},
            "fuente": NE, "categorias": cats, "atributos": atrs, "ambitos_comunes": comunes, "reglas": reglas, "casos": casos}
