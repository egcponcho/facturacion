import json
import re

lineas = open('sac.txt', encoding='utf-8').read().split('\n')
RE_COD = re.compile(r'(\d{2}\.\d{2}|\d{4}\.\d{1,2}|\d{4}\.\d{2}\.\d{2}\.\d{2})')
RE_OTRO = re.compile(r'\d{4}\.\d{2}\.\d{2}(\.\d{1,3})?')
codigos, actual, desc, dai = [], None, [], None
inicio = next(i for i, l in enumerate(lineas) if l.strip() == 'SECCIÓN I' and i > 700)
def cerrar():
    global actual, desc, dai
    if actual:
        d = re.sub(r'\s+', ' ', ' '.join(desc)).strip()
        codigos.append({"codigo": actual, "descripcion": d, "dai": dai})
    actual, desc, dai = None, [], None
en_tabla = False
L = [x.strip() for x in lineas[inicio:]]
L0 = [x for x in L if x and not x.startswith('<<<PAG')]
L = []
for x in L0:
    m = re.fullmatch(r'(\d{4}\.\d{2}\.\d{2}\.\d{2}|\d{4}\.\d{1,2}|\d{2}\.\d{2})\s+([-A-ZÁÉÍÓÚÑ\"(].*)', x)
    if m:
        L += [m.group(1), m.group(2)]
    else:
        L.append(x)
def mayus(x):
    letras = [ch for ch in x if ch.isalpha()]
    return letras and sum(ch.isupper() for ch in letras) / len(letras) > 0.8
for i, t in enumerate(L):
    if t == 'CÓDIGO':
        en_tabla = True; cerrar(); continue
    if re.fullmatch(r'(SECCI[OÓ]N [IVX]+|CAP[IÍ]TULO \d{1,2})', t):
        cerrar(); en_tabla = False; continue
    if not en_tabla:
        continue
    if t in ('DESCRIPCIÓN', 'DAI', '%', 'DAI %', 'DAI  %') or re.fullmatch(r'DAI\s*%?', t):
        continue
    if RE_COD.fullmatch(t):
        if len(t) == 5 and not (i + 1 < len(L) and mayus(L[i + 1])):
            if actual: desc.append(t)
            continue
        cerrar(); actual = t; continue
    if RE_OTRO.fullmatch(t):
        cerrar(); continue
    if actual and len(actual) == 13 and re.fullmatch(r'(I{1,3}|IV)\s*\*?', t):
        dai = 'Parte ' + t; continue
    if actual and re.fullmatch(r'\d{1,3}(\.\d+)?', t) and len(actual) == 13:
        dai = t; continue
    if actual:
        desc.append(t)
cerrar()
# Limpieza: pie de página numérico dentro de la descripción
for c in codigos:
    c["descripcion"] = re.sub(r'\s+\d{1,3}$', '', c["descripcion"]).strip()
    c["suprimida"] = 'SUPRIMIDA' in c["descripcion"]
codigos = [c for c in codigos if not c["suprimida"]]
json.dump(codigos, open('codigos_aci.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
from collections import Counter

print(len(codigos), Counter(len(c['codigo']) for c in codigos))
print([c for c in codigos if c['codigo'].startswith('6404')])
sin = [c['codigo'] for c in codigos if len(c['codigo']) == 13 and c['dai'] is None]
print('10dig sin DAI:', len(sin), sin[:10])
