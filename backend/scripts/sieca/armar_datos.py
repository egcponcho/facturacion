import json, re
DATA = str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'app' / 'data' / 'oficial') + '/'
MOTOR = str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'app' / 'data' / 'motor') + '/'
cod = json.load(open('codigos_aci.json', encoding='utf-8'))
d = {c['codigo']: c for c in cod}
dig = lambda s: re.sub(r'\D', '', s)

def limpio(t):
    t = re.sub(r'^[-\s]+', '', t).strip().rstrip(':').strip()
    t = re.sub(r'\s+', ' ', t)
    return t

def frase(t):
    t = limpio(t)
    if t and sum(c.isupper() for c in t if c.isalpha()) > 0.8 * max(1, sum(c.isalpha() for c in t)):
        t = t.lower()
        i = next((j for j, ch in enumerate(t) if ch.isalpha()), 0)
        t = t[:i] + t[i].upper() + t[i + 1:]
        # siglas y referencias frecuentes
        t = re.sub(r'\b(dvd|cd|usb|pvc)\b', lambda m: m.group(0).upper(), t)
    return t

def cadena(c10, con_partida=True):
    """Texto completo del inciso: partida > subpartida de un guion > de dos guiones > inciso."""
    d10 = dig(c10)
    partes = []
    h = d.get(f"{d10[:2]}.{d10[2:4]}")
    if h and con_partida: partes.append(frase(h['descripcion']))
    g1 = d.get(f"{d10[:4]}.{d10[4]}")
    if g1 and d10[5] != '0': partes.append(limpio(g1['descripcion']))
    s6 = d.get(f"{d10[:4]}.{d10[4:6]}")
    if s6: partes.append(limpio(s6['descripcion']))
    propio = d.get(c10) or {}
    if propio: partes.append(limpio(propio['descripcion']))
    vistos = []
    for p in partes:
        if p and p not in vistos: vistos.append(p)
    return ' — '.join(vistos)

# ---- Partidas (4) y subpartidas (6) oficiales con su texto encadenado
sac = {}
for c in cod:
    k = dig(c['codigo'])
    if len(k) == 4:
        sac[k] = frase(c['descripcion'])
for c in cod:
    k = dig(c['codigo'])
    if len(k) == 10:
        s6 = k[:6]
        if s6 not in sac:
            nodo = d.get(f"{k[:4]}.{k[4:6]}")
            base = cadena(f"{k[:4]}.{k[4:6]}.00.00") if not nodo else ' — '.join(x for x in [sac.get(k[:4], ''), limpio(d[f"{k[:4]}.{k[4]}"]['descripcion']) if k[5] != '0' and f"{k[:4]}.{k[4]}" in d else '', limpio(nodo['descripcion'])] if x)
            sac[s6] = base
sac_list = [{"codigo": k, "descripcion": v[:400]} for k, v in sorted(sac.items())]
json.dump(sac_list, open(DATA + 'sac_oficial.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

# ---- Incisos de 10 dígitos (ACI) con DAI y condiciones que se deducen del texto
def condicion(texto):
    t = texto.lower()
    c = {}
    if 'puntera metálica' in t and not re.search(r'\b(sin|ni)\b[^,;]*puntera metálica', t): c['puntera'] = 'metalica'
    if 'que cubran la rodilla' in t: c['altura'] = 'rodilla'
    elif 'que cubran el tobillo' in t and 'sin cubrir' not in t: c['altura'] = 'tobillo'
    if 'cubrecalzado' in t: c['estiloCalz'] = 'cubrecalzado'
    if re.search(r'para hombres( o niños)?\b', t): c['genero'] = 'M'
    elif re.search(r'para mujeres( o niñas)?\b', t): c['genero'] = 'F'
    if 'para bebés' in t: c['edadNac'] = 'bebe'
    if re.search(r'\bsombreros?\b', t) and not re.search(r'\bgorras?\b', t): c['formaTocado'] = 'sombrero'
    return c

incisos, interpretacion = [], {}
for c in cod:
    k = dig(c['codigo'])
    if len(k) != 10: continue
    propio = limpio(c['descripcion'])
    desc = cadena(c['codigo'], con_partida=False)
    dai = c['dai']
    try:
        dai_n = float(dai) if dai and dai.replace('.', '', 1).isdigit() else None
    except ValueError:
        dai_n = None
    # Solo lo que distingue a este inciso de sus hermanos: su propio texto
    incisos.append({"codigo": k, "descripcion": desc[:300], "propio": propio[:200], "dai": dai_n, "dai_txt": dai})
    if c := condicion(propio):  # lo que el clasificador lee del texto: motor, no dato oficial
        interpretacion[k] = c
json.dump(incisos, open(DATA + 'aci_incisos.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
json.dump({"origen": "Classification engine: conditions the classifier reads from the official ACI line text. Engine rules, never official data.",
           "condiciones": interpretacion}, open(MOTOR + 'interpretacion_aci.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---- Notas oficiales con las claves de relevancia de la versión anterior
viejas = {(n['codigo'], n['numero'].split(' (')[0]): n.get('claves', []) for n in json.load(open(DATA + 'sac_notas.json', encoding='utf-8'))}
notas = json.load(open('notas_oficiales.json', encoding='utf-8'))
for n in notas:
    n['claves'] = viejas.get((n['codigo'], n['numero']), [])
json.dump(notas, open(DATA + 'sac_notas.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(sac_list), 'partidas/subpartidas;', len(incisos), 'incisos;', len(notas), 'notas;', sum(1 for n in notas if n['claves']), 'con claves')
x = {i['codigo']: i for i in incisos}
for k in ['6404191000', '6404199000', '6403911000', '6401991000', '6402991000', '6505002000', '6109100000']:
    print(k, x[k])
print(sac['6404'], '|', sac['640419'], '|', sac['620342'])
