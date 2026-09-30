import json, re

ROMANOS = "I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX XXI".split()
lineas = open('sac.txt', encoding='utf-8').read().split('\n')

def limpia(ls):
    out = []
    for l in ls:
        t = l.strip()
        if t.startswith('<<<PAG') or re.fullmatch(r'\d{1,3}|[IVX]{1,5}', t) or t.startswith('Anexo 1 de la Resolución'):
            continue
        out.append(t)
    return out

def unir(ls):
    txt = ' '.join(x for x in ls if x)
    txt = re.sub(r'\s+', ' ', txt).strip()
    txt = re.sub(r'(\w)- (\w)', r'\1\2', txt)  # guiones de corte de línea
    return txt

notas = []
def agregar(ambito, codigo, numero, texto, caps):
    texto = unir(texto) if isinstance(texto, list) else texto
    if texto:
        notas.append({"ambito": ambito, "codigo": codigo, "numero": numero, "texto": texto, "capitulos": caps, "claves": []})

# ---- Reglas generales (entre "C. REGLAS GENERALES" y "D.")
i0 = next(i for i, l in enumerate(lineas) if 'REGLAS GENERALES PARA LA INTERPRETACIÓN' in l)
i1 = next(i for i in range(i0, i0 + 400) if lineas[i].strip() == 'D.')
bloque = limpia(lineas[i0 + 2:i1])
actual, buf = None, []
for l in bloque:
    m = re.fullmatch(r'([1-6])\.', l)
    if m:
        if actual: agregar("reglas", "RGI", actual, buf, [])
        actual, buf = m.group(1), []
    elif actual:
        buf.append(l)
agregar("reglas", "RGI", actual, buf, [])

# ---- Secciones y capítulos
cuerpo_ini = next(i for i, l in enumerate(lineas) if l.strip() == 'SECCIÓN I' and i > 700)
seccion, capitulo = None, None
caps_seccion = {}
tipo_bloque, buf = None, []
RE_SEC = re.compile(r'SECCI[OÓ]N ([IVX]+)$')
RE_CAP = re.compile(r'CAP[IÍ]TULO (\d{1,2})$')
RE_BLOQUE = re.compile(r'(NOTAS?|NOTAS? DE SUBPARTIDA|NOTAS? COMPLEMENTARIAS? CENTROAMERICANAS?)\.$')

bloques = []  # (ambito, codigo, tipo, lineas)
def cerrar():
    global tipo_bloque, buf
    if tipo_bloque:
        bloques.append((tipo_bloque[0], tipo_bloque[1], tipo_bloque[2], buf))
    tipo_bloque, buf = None, []

for l in limpia(lineas[cuerpo_ini:]):
    m = RE_SEC.fullmatch(l)
    if m and m.group(1) in ROMANOS:
        cerrar(); seccion, capitulo = m.group(1), None; continue
    m = RE_CAP.fullmatch(l)
    if m:
        cerrar(); capitulo = m.group(1).zfill(2); caps_seccion.setdefault(seccion, []).append(capitulo); continue
    m = RE_BLOQUE.fullmatch(l)
    if m:
        cerrar()
        clase = 'subpartida' if 'SUBPARTIDA' in l else 'complementaria' if 'COMPLEMENTARIA' in l else 'nota'
        tipo_bloque = (('capitulo' if capitulo else 'seccion'), capitulo or seccion, clase)
        continue
    if tipo_bloque and (l.startswith('CÓDIGO') or l == 'CÓDIGO'):
        cerrar(); continue
    if tipo_bloque:
        buf.append(l)
cerrar()

for ambito, codigo, clase, ls in bloques:
    caps = [codigo] if ambito == 'capitulo' else caps_seccion.get(codigo, [])
    sec_de = {c: s for s, cs in caps_seccion.items() for c in cs}
    patron = re.compile(r'([A-Z])\.\s+(.*)') if clase == 'complementaria' else re.compile(r'(\d{1,2})\.\s+(.*)')
    actual, cuerpo = None, []
    def emitir():
        if actual is None: return
        numero = {'nota': actual, 'subpartida': f'Subp. {actual}', 'complementaria': f'NCC {actual}'}[clase]
        amb = 'subpartida' if clase == 'subpartida' else ('complementaria' if clase == 'complementaria' else ambito)
        agregar(amb, codigo, numero, cuerpo, caps)
    for l in ls:
        # Una nota nueva empieza con el número (o letra) siguiente al de la actual
        m = patron.fullmatch(l)
        m2 = re.fullmatch(r'(\d{1,2})\.$', l) if clase != 'complementaria' else re.fullmatch(r'([A-Z])\.$', l)
        if m or m2:
            g = (m or m2).group(1)
            if actual is None or (g.isdigit() and actual.isdigit() and int(g) == int(actual) + 1) or (g.isalpha() and actual.isalpha() and ord(g) == ord(actual) + 1):
                emitir(); actual, cuerpo = g, ([m.group(2)] if m else [])
                continue
        cuerpo.append(l)
    emitir()

json.dump(notas, open('notas_oficiales.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump(caps_seccion, open('caps_seccion.json', 'w'), indent=0)
from collections import Counter
print(len(notas), Counter(n['ambito'] for n in notas))
print(len(bloques), 'bloques')
