"""Calzado: capítulo 64 según sus Notas Explicativas.

- Nota 4 a): la materia del corte es la de mayor superficie exterior, sin
  accesorios ni refuerzos (ribetes, protectores de tobillo, adornos, hebillas,
  ojetes); la lengüeta cuenta (nota nacional 3).
- Nota 4 b): la materia de la suela es la de mayor superficie en contacto con el suelo.
- Nota 3 a): caucho y plástico incluyen el textil con una capa exterior de caucho
  o plástico perceptible a simple vista (cuero sintético, PU, PVC).
- Nota de subpartida 1: calzado de deporte es solo el que tiene o puede tener
  clavos, tacos, fijaciones o barras, y el de esquí, snowboard, lucha, boxeo o
  ciclismo. El de tenis, básquetbol, gimnasia o entrenamiento solo cuenta en la 6404.11.
- Nota 1: fuera del capítulo el calzado con patines fijos (95.06), el
  ortopédico (90.21) y los patucos textiles sin suela aplicada (61/62).
- Árbol vigente: 6401.91 pasó a 6401.99 (cubren la rodilla), 6402.30 y 6403.30
  ya no existen (puntera metálica y plataforma de madera van a 6402.9x y
  6403.9x) y 6406.91/99 son hoy 6406.90.
"""
from base import ambitos, atributo, bloqueo, caso, categoria, cond, opcion, regla, si

DOM = "FOOTWEAR"
NE = "Explanatory Notes, chapter 64"

CORTE = {"plastico": "CAUCHO O PLÁSTICO", "cuero": "CUERO", "textil": "TEXTIL", "otro": "OTRAS MATERIAS"}
SUELA = {"caucho": "CAUCHO O PLÁSTICO", "cuero": "CUERO", "otro": "OTRAS MATERIAS"}


def familia() -> dict:
    cats = [
        categoria("calzado", "Footwear: sneakers, shoes, boots, sandals, slippers", corto="Footwear", aduana="Calzado", grupo="Footwear",
                  dominio=DOM, capitulos=["64"], orden=100, prioridad=36,
                  re_=r"\b(shoes?|sneakers?|zapatos?|zapatillas?|tenis|boots?|botas?|botin(es)?|sandals?|sandalias?|slides?|chanclas?|"
                      r"flip ?flops?|mules?|clogs?|zuecos?|slip-?on|loafers?|mocasin(es)?|moccasins?|slippers?|pantuflas?|heels?|tacon(es)?|"
                      r"pumps|flats|balerinas?|footwear|calzado|chukka|cleats?|tachones|guayos|galoshes?|overshoes?|cubrecalzados?)\b",
                  alias="tenis sneaker zapato bota botín sandalia chancla pantufla zueco mocasín tacón calzado de seguridad",
                  plantilla={"material": "CON CORTE DE {material_corte} Y SUELA DE {material_suela}", "requiere": ["material_corte"],
                             "como": {"material_corte": CORTE, "material_suela": SUELA}, "si_falta": {"material_suela": "caucho"}}),
        categoria("partes_calzado", "Footwear parts: uppers, soles, heels, removable insoles", corto="Footwear part", aduana="Parte de calzado",
                  grupo="Footwear", dominio=DOM, capitulos=["64"], orden=110, prioridad=20,
                  re_=r"\b(insoles?|plantillas?|taloneras?|heel (cushions?|grips?)|footbeds?|outsoles?|suelas?|uppers?|cortes? de calzado|"
                      r"tacones? para calzado|contrafuertes?|punteras?)\b",
                  alias="plantilla suela tacón corte talonera contrafuerte puntera"),
        categoria("polainas", "Gaiters, leggings and spats", corto="Gaiter", aduana="Polaina", grupo="Footwear", dominio=DOM, capitulos=["64"],
                  orden=120, prioridad=18, re_=r"\b(gaiters?|polainas?|spats|leg warmers? with strap)\b", alias="polaina gaiter"),
        categoria("cordones", "Shoelaces", corto="Shoelaces", aduana="Cordones para calzado", grupo="Footwear", dominio=DOM,
                  capitulos=["63", "42", "39"], orden=130, prioridad=17, re_=r"\b(shoe ?laces?|laces|agujetas?|cordones?)\b",
                  alias="cordones agujetas", plantilla={"material": "DE {clase}", "clase": ["material"]}),
    ]
    corte_rigido = [cond("material_corte", ["plastico", "cuero"])]
    atrs = [
        atributo("estilo_calzado", "Footwear style", "select", [
            opcion("tenis", "Sneaker or athletic shoe", re_=r"\b(sneakers?|tenis|trainers?|running|slip-?on|zapatillas?)\b", prioridad=21,
                   texto={"nombre": "TENIS"}, defecto=True),
            opcion("zapato", "Closed shoe (dress, casual, school)", re_=r"\b(shoes?|zapatos?|oxfords?|derbys?|brogues?|flats|balerinas?)\b",
                   prioridad=25, texto={"nombre": "ZAPATO"}),
            opcion("tacon", "High-heeled shoe", re_=r"\b(heels?|tacon(es)?|stilettos?|pumps)\b", prioridad=15, texto={"nombre": "ZAPATO DE TACÓN"}),
            opcion("mocasin", "Moccasin, loafer or boat shoe", re_=r"\b(loafers?|mocasin(es)?|moccasins?|boat shoes?|nauticos?)\b", prioridad=14,
                   texto={"nombre": "MOCASÍN"}),
            opcion("bota", "Boot", re_=r"\b(boots?|botas?)\b", prioridad=12, texto={"nombre": "BOTA"}, implica={"altura": "tobillo"}),
            opcion("botin", "Ankle boot or chukka", re_=r"\b(botin(es)?|ankle boots?|chukkas?|chelsea)\b", prioridad=11, texto={"nombre": "BOTÍN"},
                   implica={"altura": "tobillo"}),
            opcion("sandalia", "Sandal", re_=r"\b(sandals?|sandalias?|huaraches?)\b", prioridad=10, texto={"nombre": "SANDALIA"}),
            opcion("chancla", "Flip-flop or slide", re_=r"\b(flip ?flops?|chanclas?|slides?|thongs?|chinelas?)\b", prioridad=9,
                   texto={"nombre": "SANDALIA"}),
            opcion("pantufla", "Slipper or house shoe", re_=r"\b(slippers?|pantuflas?|house shoes?)\b", prioridad=9, texto={"nombre": "PANTUFLA"}),
            opcion("zueco", "Clog", re_=r"\b(clogs?|zuecos?)\b", prioridad=9, texto={"nombre": "ZUECO"}),
            opcion("bota_lluvia", "Rain or rubber boot", re_=r"\b(rain ?boots?|botas? de (lluvia|hule)|wellingtons?|galoshes?)\b", prioridad=5,
                   texto={"nombre": "BOTA"}, implica={"altura": "tobillo"}),
            opcion("seguridad", "Safety or work footwear", re_=r"\b(safety|steel toe|composite toe|work boots?|industrial|seguridad)\b",
                   prioridad=6, texto={"nombre": "CALZADO DE SEGURIDAD"}),
            opcion("deporte", "With cleats or spikes; for skating, wrestling, boxing or cycling",
                   re_=r"\b(cleats?|spikes?|tachones|guayos|taquetes|football boots?|soccer|futbol|cycling|ciclismo|wrestling|boxing|lucha|box)\b",
                   prioridad=4, texto={"nombre": "CALZADO DEPORTIVO"}, implica={"uso_deportivo": "tacos"}),
            opcion("esqui", "Ski or snowboard boot", re_=r"\b(ski|esqui|snowboard)\b", prioridad=3, texto={"nombre": "BOTA DE ESQUÍ"},
                   implica={"uso_deportivo": "esqui", "altura": "tobillo"}),
            opcion("cubrecalzado", "Overshoe (worn over other footwear)", re_=r"\b(overshoes?|cubrecalzados?)\b", prioridad=3,
                   texto={"nombre": "CUBRECALZADO"}),
            opcion("patines", "With skates attached (ice or roller)", re_=r"\b(skates?|patines?|rollers?|heelys)\b", prioridad=2,
                   texto={"nombre": "CALZADO CON PATINES"}),
        ], ambitos(["calzado"]), control="lista", orden=150),
        atributo("material_corte", "Upper material", "select", [
            opcion("cuero", "Natural leather", texto=None), opcion("textil", "Textile"),
            opcion("plastico", "Rubber or plastics (includes synthetic leather and coated fabric)"), opcion("otro", "Other")],
            ambitos(["calzado"]), seccion="composicion", derivacion={"modo": "material", "parte": "corte", "lectura": "superficie"}, orden=170,
            ayuda="Note 4 a): the material with the largest external surface area, not counting trims or reinforcements; the tongue counts."),
        atributo("material_suela", "Outer sole material", "select", [
            opcion("caucho", "Rubber or plastics (EVA, PU, TPR)"), opcion("cuero", "Natural or regenerated leather"),
            opcion("otro", "Other (wood, cork, textile, jute)")],
            ambitos(["calzado"]), seccion="composicion", derivacion={"modo": "material", "parte": "suela", "lectura": "contacto"}, orden=180,
            ayuda="Note 4 b): the material with the largest surface area in contact with the ground, not counting attachments."),
        atributo("impermeable", "Waterproof, upper not joined to the sole by stitching, rivets, nails, screws or plugs", "boolean", [],
                 ambitos(["calzado"], condicion=[cond("material_corte", "plastico"), cond("material_suela", "caucho")]),
                 defecto="false", orden=190,
                 patrones=[{"re": r"\b(rain ?boots?|botas? de (lluvia|hule)|wellingtons?|galoshes?|waterproof molded|moldead[oa] impermeable)\b",
                            "en": "todo"}],
                 ayuda="Heading 64.01: molded, injected, vulcanized or high-frequency welded in one piece (rain boots, some overshoes)."),
        atributo("uso_deportivo", "Use", "select", [
            opcion("no", "Casual, urban, dress or outdoor", defecto=True),
            opcion("entrenamiento", "Designed for tennis, basketball, gym, training, running or similar",
                   re_=r"\b(running|trail running|basketball|basquet|baloncesto|tennis shoes?|training|entrenamiento|gym|gimnasio|crossfit|"
                       r"court|indoor|futsal)\b", prioridad=8),
            opcion("tacos", "With cleats, spikes or special fixings; for skating, wrestling, boxing or cycling", prioridad=4,
                   re_=r"\b(cleats?|spikes?|tachones|guayos|football boots?|cycling|ciclismo|wrestling|boxing)\b"),
            opcion("esqui", "Ski or snowboard", re_=r"\b(ski|esqui|snowboard)\b", prioridad=3)],
            ambitos(["calzado"], condicion=[cond("material_corte", ["plastico", "cuero", "textil"]), cond("material_suela", ["caucho", "cuero"])]),
            orden=200, ayuda="Subheading Note 1: sports footwear is only footwear with (or able to take) spikes, cleats, special fixings or "
                             "bars, and footwear for skiing, snowboarding, wrestling, boxing or cycling. Tennis, basketball, gym and "
                             "training shoes count only for a textile upper (6404.11); casual sneakers are not sports footwear."),
        atributo("altura", "Height", "select", [
            opcion("bajo", "Does not cover the ankle", texto=None, bloqueo=[bloqueo("A boot covers the ankle.", estilo_calzado=["bota", "botin"])]),
            opcion("tobillo", "Covers the ankle", texto={"frase": "QUE CUBRE EL TOBILLO", "orden": 10}),
            opcion("rodilla", "Also covers the knee", texto={"frase": "QUE CUBRE LA RODILLA", "orden": 10})],
            ambitos(["calzado"], condicion=corte_rigido), defecto="bajo", orden=210),
        atributo("puntera_metalica", "Protective metal toe-cap", "boolean", [], ambitos(["calzado"], condicion=corte_rigido), defecto="false",
                 orden=220, patrones=[{"re": r"\b(steel toe|puntera (de acero|metalica)|metal toe)\b", "en": "todo"}],
                 texto={"frase": "CON PUNTERA METÁLICA DE PROTECCIÓN", "orden": 20}),
        atributo("tiras_tetones", "Upper of straps or thongs fixed to the sole by plugs", "boolean", [],
                 ambitos(["calzado"], condicion=[cond("material_corte", "plastico"), cond("material_suela", "caucho")]), defecto="false",
                 orden=230, patrones=[{"re": r"\b(flip ?flops?|chanclas? de dedo|thongs?|toe post)\b", "en": "todo"}],
                 ayuda="Subheading 6402.20: thong sandals whose straps end in plugs set into holes in the sole."),
        atributo("tiras_dedo", "Upper of leather straps across the instep and around the big toe", "boolean", [],
                 ambitos(["calzado"], condicion=[cond("material_corte", "cuero"), cond("material_suela", "cuero")]), defecto="false",
                 orden=240, ayuda="Subheading 6403.20."),
        atributo("tipo_parte", "Which part", "select", [
            opcion("corte", "Upper or parts of the upper (vamps, quarters, linings)", re_=r"\b(uppers?|cortes?|vamps?|palas?)\b"),
            opcion("suela", "Outer sole or heel", re_=r"\b(outsoles?|soles?|suelas?|heels?|tacones?|tacos)\b"),
            opcion("plantilla", "Removable insole, heel cushion or similar", re_=r"\b(insoles?|plantillas?|taloneras?|footbeds?|heel cushions?)\b"),
            opcion("refuerzo", "Stiffener or toe puff"), opcion("otra", "Other part")],
            ambitos(["partes_calzado"], "REQUIRE"), orden=250),
    ]
    # Atributos comunes y en qué categorías aplican
    comunes = {
        "comp.corte": ambitos(["calzado"], "REQUIRE"),
        "comp.suela": ambitos(["calzado"], "REQUIRE"),
        "comp.material": ambitos(["partes_calzado", "cordones"], "REQUIRE"),
        "material": ambitos(["partes_calzado", "cordones"]),
        "genero": ambitos(["calzado"]),
        "edad": ambitos(["calzado"]),
    }
    deporte = ["tacos", "esqui", "entrenamiento"]
    no_dep = ["no", "entrenamiento"]
    C = "calzado"
    reglas = [
        regla("R-NE-CAL-000", C, si(estilo_calzado_no="patines"), ["64"], f"Footwear → chapter 64 ({NE}, general considerations)"),
        regla("R-NE-CAL-001", C, si(estilo_calzado="patines"), ["950670"],
              "Footwear with skates attached → 9506.70 (chapter 64 Note 1 f)"),
        # 64.01: corte y suela de caucho o plástico, impermeable y sin unir por costura, remaches, clavos, tornillos o espigas
        regla("R-NE-CAL-011", C, si(material_corte="plastico", material_suela="caucho", impermeable=True, puntera_metalica=True), ["640110"],
              "Waterproof rubber or plastic footwear with a protective metal toe-cap → 6401.10"),
        regla("R-NE-CAL-012", C, si(material_corte="plastico", material_suela="caucho", impermeable=True, puntera_metalica=False, altura="tobillo"),
              ["640192"], "Waterproof footwear covering the ankle but not the knee → 6401.92"),
        regla("R-NE-CAL-013", C, si(material_corte="plastico", material_suela="caucho", impermeable=True, puntera_metalica=False,
                                    altura=["bajo", "rodilla"]), ["640199"],
              "Other waterproof footwear (including knee boots, formerly 6401.91) → 6401.99"),
        # 64.02: los demás de caucho o plástico
        regla("R-NE-CAL-021", C, si(material_corte="plastico", material_suela="caucho", impermeable=False, uso_deportivo="esqui"), ["640212"],
              "Rubber or plastic ski or snowboard footwear → 6402.12 (subheading Note 1 b)"),
        regla("R-NE-CAL-022", C, si(material_corte="plastico", material_suela="caucho", impermeable=False, uso_deportivo="tacos"), ["640219"],
              "Rubber or plastic sports footwear with spikes, cleats or fixings → 6402.19 (subheading Note 1 a)"),
        regla("R-NE-CAL-023", C, si(material_corte="plastico", material_suela="caucho", impermeable=False, uso_deportivo=no_dep, tiras_tetones=True),
              ["640220"], "Straps fixed to the sole by plugs (flip-flops) → 6402.20"),
        regla("R-NE-CAL-024", C, si(material_corte="plastico", material_suela="caucho", impermeable=False, uso_deportivo=no_dep, tiras_tetones=False,
                                    altura=["tobillo", "rodilla"]), ["640291"], "Other rubber or plastic footwear covering the ankle → 6402.91"),
        regla("R-NE-CAL-025", C, si(material_corte="plastico", material_suela="caucho", impermeable=False, uso_deportivo=no_dep, tiras_tetones=False,
                                    altura="bajo"), ["640299"], "Other rubber or plastic footwear → 6402.99"),
        # 64.03: corte de cuero natural
        regla("R-NE-CAL-031", C, si(material_corte="cuero", material_suela=["caucho", "cuero"], uso_deportivo="esqui"), ["640312"],
              "Leather ski or snowboard footwear → 6403.12"),
        regla("R-NE-CAL-032", C, si(material_corte="cuero", material_suela=["caucho", "cuero"], uso_deportivo="tacos"), ["640319"],
              "Leather sports footwear with spikes, cleats or fixings → 6403.19"),
        regla("R-NE-CAL-033", C, si(material_corte="cuero", material_suela="cuero", uso_deportivo=no_dep, tiras_dedo=True), ["640320"],
              "Leather sole, leather straps across the instep and around the big toe → 6403.20"),
        regla("R-NE-CAL-034", C, si(material_corte="cuero", material_suela="caucho", uso_deportivo=no_dep, puntera_metalica=True), ["640340"],
              "Leather footwear with a protective metal toe-cap → 6403.40"),
        regla("R-NE-CAL-035", C, si(material_corte="cuero", material_suela="cuero", uso_deportivo=no_dep, tiras_dedo=False, puntera_metalica=True),
              ["640340"], "Leather footwear with a protective metal toe-cap → 6403.40"),
        regla("R-NE-CAL-036", C, si(material_corte="cuero", material_suela="cuero", uso_deportivo=no_dep, tiras_dedo=False, puntera_metalica=False,
                                    altura=["tobillo", "rodilla"]), ["640351"], "Leather sole and upper, covering the ankle → 6403.51"),
        regla("R-NE-CAL-037", C, si(material_corte="cuero", material_suela="cuero", uso_deportivo=no_dep, tiras_dedo=False, puntera_metalica=False,
                                    altura="bajo"), ["640359"], "Leather sole and upper → 6403.59"),
        regla("R-NE-CAL-038", C, si(material_corte="cuero", material_suela="caucho", uso_deportivo=no_dep, puntera_metalica=False,
                                    altura=["tobillo", "rodilla"]), ["640391"], "Leather upper, rubber or plastic sole, covering the ankle → 6403.91"),
        regla("R-NE-CAL-039", C, si(material_corte="cuero", material_suela="caucho", uso_deportivo=no_dep, puntera_metalica=False, altura="bajo"),
              ["640399"], "Leather upper, rubber or plastic sole → 6403.99"),
        # 64.04: corte textil
        regla("R-NE-CAL-041", C, si(material_corte="textil", material_suela="caucho", uso_deportivo=deporte), ["640411"],
              "Textile upper, rubber or plastic sole: sports, tennis, basketball, gym or training footwear → 6404.11"),
        regla("R-NE-CAL-042", C, si(material_corte="textil", material_suela="caucho", uso_deportivo="no"), ["640419"],
              "Textile upper, rubber or plastic sole, casual or other → 6404.19 (casual sneakers are not sports footwear)"),
        regla("R-NE-CAL-043", C, si(material_corte="textil", material_suela="cuero"), ["640420"],
              "Textile upper, leather sole → 6404.20"),
        # 64.05: los demás
        regla("R-NE-CAL-051", C, si(material_corte="cuero", material_suela="otro"), ["640510"],
              "Leather upper with a sole of other material (wood, cork, textile) → 6405.10"),
        regla("R-NE-CAL-052", C, si(material_corte="textil", material_suela="otro"), ["640520"],
              "Textile upper with a sole of other material → 6405.20"),
        regla("R-NE-CAL-053", C, si(material_corte="plastico", material_suela=["cuero", "otro"]), ["640590"],
              "Rubber or plastic upper with a leather or other sole → 6405.90"),
        regla("R-NE-CAL-054", C, si(material_corte="otro"), ["640590"], "Upper of other materials → 6405.90"),
        # 64.06: partes, plantillas amovibles, polainas
        regla("R-NE-CAL-061", "partes_calzado", si(tipo_parte="corte"), ["640610"], "Uppers and their parts (not stiffeners) → 6406.10"),
        regla("R-NE-CAL-062", "partes_calzado", si(tipo_parte="suela", material="plastico"), ["640620"],
              "Outer soles and heels of rubber or plastics → 6406.20"),
        regla("R-NE-CAL-063", "partes_calzado", si(tipo_parte="suela", material_no="plastico"), ["640690"],
              "Outer soles and heels of other materials → 6406.90"),
        regla("R-NE-CAL-064", "partes_calzado", si(tipo_parte=["plantilla", "refuerzo", "otra"]), ["640690"],
              "Removable insoles, heel cushions, stiffeners and other parts → 6406.90"),
        regla("R-NE-CAL-071", "polainas", [], ["640690"], "Gaiters, leggings and similar articles → 6406.90 (heading 64.06, part II)"),
        regla("R-NE-CAL-081", "cordones", si(material=["textil", "otro", "papel"]), ["630790"],
              "Shoelaces follow their own material (chapter 64 Note 2): textile → 6307.90"),
        regla("R-NE-CAL-082", "cordones", si(material="cuero"), ["420500"], "Leather shoelaces → 4205.00"),
        regla("R-NE-CAL-083", "cordones", si(material="plastico"), ["392690"], "Plastic shoelaces → 3926.90"),
    ]
    casos = [
        caso(C, "640419", estilo_calzado="tenis", **{"comp.corte": "100% canvas", "comp.suela": "100% rubber"}, uso_deportivo="no"),
        caso(C, "640411", estilo_calzado="tenis", **{"comp.corte": "80% mesh 20% synthetic", "comp.suela": "rubber"}, uso_deportivo="entrenamiento"),
        caso(C, "640399", estilo_calzado="tenis", **{"comp.corte": "100% leather", "comp.suela": "100% rubber"}, uso_deportivo="no",
             puntera_metalica=False, altura="bajo"),
        caso(C, "640391", estilo_calzado="bota", **{"comp.corte": "100% leather", "comp.suela": "rubber"}, uso_deportivo="no", puntera_metalica=False),
        caso(C, "640340", estilo_calzado="seguridad", **{"comp.corte": "leather", "comp.suela": "PU"}, uso_deportivo="no", puntera_metalica=True),
        caso(C, "640319", estilo_calzado="deporte", **{"comp.corte": "leather", "comp.suela": "TPU"}),
        caso(C, "640359", estilo_calzado="zapato", **{"comp.corte": "leather", "comp.suela": "leather"}, uso_deportivo="no", tiras_dedo=False,
             puntera_metalica=False, altura="bajo"),
        caso(C, "640320", estilo_calzado="sandalia", **{"comp.corte": "leather", "comp.suela": "leather"}, uso_deportivo="no", tiras_dedo=True),
        caso(C, "640299", estilo_calzado="chancla", **{"comp.corte": "PVC", "comp.suela": "EVA"}, impermeable=False, uso_deportivo="no",
             tiras_tetones=False, altura="bajo"),
        caso(C, "640220", estilo_calzado="chancla", **{"comp.corte": "rubber", "comp.suela": "rubber"}, impermeable=False, uso_deportivo="no",
             tiras_tetones=True),
        caso(C, "640291", estilo_calzado="botin", **{"comp.corte": "synthetic leather", "comp.suela": "TPR"}, impermeable=False, uso_deportivo="no",
             tiras_tetones=False),
        caso(C, "640212", estilo_calzado="esqui", **{"comp.corte": "polyurethane", "comp.suela": "rubber"}, impermeable=False),
        caso(C, "640192", estilo_calzado="bota_lluvia", **{"comp.corte": "100% PVC", "comp.suela": "PVC"}, impermeable=True, puntera_metalica=False),
        caso(C, "640110", estilo_calzado="bota_lluvia", **{"comp.corte": "PVC", "comp.suela": "PVC"}, impermeable=True, puntera_metalica=True),
        caso(C, "640420", estilo_calzado="zapato", **{"comp.corte": "textile", "comp.suela": "leather"}),
        caso(C, "640520", estilo_calzado="sandalia", **{"comp.corte": "canvas", "comp.suela": "jute"}),
        caso(C, "640510", estilo_calzado="zueco", **{"comp.corte": "leather", "comp.suela": "wood"}),
        caso(C, "950670", estilo_calzado="patines", **{"comp.corte": "synthetic", "comp.suela": "rubber"}),
        caso("partes_calzado", "640620", tipo_parte="suela", **{"comp.material": "rubber"}),
        caso("partes_calzado", "640690", tipo_parte="plantilla", **{"comp.material": "EVA foam"}),
        caso("partes_calzado", "640610", tipo_parte="corte", **{"comp.material": "leather"}),
        caso("polainas", "640690"),
        caso("cordones", "630790", **{"comp.material": "100% polyester"}),
    ]
    return {"dominio": {"codigo": DOM, "nombre": "Footwear", "orden": 10,
                        "descripcion": "Footwear, gaiters and their parts (chapter 64). The upper and the outer sole decide the heading.",
                        "capitulos": [{"capitulo": "64", "relevancia": "PRIMARY"}, {"capitulo": "95", "relevancia": "SECONDARY"},
                                      {"capitulo": "63", "relevancia": "SECONDARY"}, {"capitulo": "42", "relevancia": "SECONDARY"},
                                      {"capitulo": "39", "relevancia": "SECONDARY"}]},
            "fuente": NE, "categorias": cats, "atributos": atrs, "ambitos_comunes": comunes, "reglas": reglas, "casos": casos}
