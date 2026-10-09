"""Números y montos en letras para los documentos («SAY: …» / «SON: …»).

Son reglas de cada idioma, no textos traducibles: el inglés agrupa por miles
con «HUNDRED», y el español tiene formas propias (quinientos, veintiún,
millones) y acorta «uno» a «un» antes de mil, millón o el nombre de la moneda.
"""
from app.modulos.documentos.idioma_doc import actual as idioma_actual

# ---- Inglés -------------------------------------------------------------------
_EN_UNIDADES = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE",
                "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
_EN_DECENAS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]


def _en_centenas(n: int) -> str:
    c, r = divmod(n, 100)
    palabras = [f"{_EN_UNIDADES[c]} HUNDRED"] if c else []
    if r < 20:
        palabras.append(_EN_UNIDADES[r])
    else:
        d, u = divmod(r, 10)
        palabras.append(_EN_DECENAS[d] + (f"-{_EN_UNIDADES[u]}" if u else ""))
    return " ".join(p for p in palabras if p)


def _en(n: int) -> str:
    """4850 → FOUR THOUSAND EIGHT HUNDRED FIFTY."""
    if n == 0:
        return "ZERO"
    grupos = []
    for divisor, nombre in ((10**9, "BILLION"), (10**6, "MILLION"), (10**3, "THOUSAND")):
        q, n = divmod(n, divisor)
        if q:
            grupos.append(f"{_en_centenas(q)} {nombre}")
    if n:
        grupos.append(_en_centenas(n))
    return " ".join(grupos)


# ---- Español ------------------------------------------------------------------
_ES_UNIDADES = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE",
                "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE",
                "VEINTIUNO", "VEINTIDÓS", "VEINTITRÉS", "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE",
                "VEINTIOCHO", "VEINTINUEVE"]
_ES_DECENAS = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_ES_CENTENAS = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS",
                "OCHOCIENTOS", "NOVECIENTOS"]


def _es_centenas(n: int) -> str:
    if n == 100:
        return "CIEN"
    c, r = divmod(n, 100)
    palabras = [_ES_CENTENAS[c]] if c else []
    if r < 30:
        palabras.append(_ES_UNIDADES[r])
    else:
        d, u = divmod(r, 10)
        palabras.append(_ES_DECENAS[d] + (f" Y {_ES_UNIDADES[u]}" if u else ""))
    return " ".join(p for p in palabras if p)


def _apocope(texto: str) -> str:
    """«uno» se acorta delante de un sustantivo: un millón, veintiún mil, un dólar."""
    if texto.endswith("VEINTIUNO"):
        return texto[:-len("VEINTIUNO")] + "VEINTIÚN"
    if texto.endswith("UNO"):
        return texto[:-3] + "UN"
    return texto


def _es(n: int) -> str:
    """4850 → CUATRO MIL OCHOCIENTOS CINCUENTA (termina en «UNO» si corresponde)."""
    if n == 0:
        return "CERO"
    palabras = []
    millones, resto = divmod(n, 10**6)
    if millones:
        palabras.append("UN MILLÓN" if millones == 1 else f"{_apocope(_es(millones))} MILLONES")
    miles, unidades = divmod(resto, 1000)
    if miles:
        palabras.append("MIL" if miles == 1 else f"{_apocope(_es_centenas(miles))} MIL")
    if unidades:
        palabras.append(_es_centenas(unidades))
    return " ".join(palabras)


# ---- Uso en los documentos ----------------------------------------------------
def numero_en_letras(n: int) -> str:
    """Número entero en letras, en el idioma de la petición."""
    return _es(n) if idioma_actual() == "es" else _en(n)


def cantidad_en_letras(n: int) -> str:
    """Número en letras para acompañar a un sustantivo (un bulto, veintiún bultos)."""
    return _apocope(_es(n)) if idioma_actual() == "es" else _en(n)


# Nombre de cada moneda (singular, plural) por idioma; otra moneda se escribe con su código
MONEDAS = {
    "en": {"USD": ("US DOLLAR", "US DOLLARS"), "EUR": ("EURO", "EUROS"), "GTQ": ("QUETZAL", "QUETZALES"),
           "CRC": ("COLON", "COLONES"), "HNL": ("LEMPIRA", "LEMPIRAS"), "NIO": ("CORDOBA", "CORDOBAS"),
           "PAB": ("BALBOA", "BALBOAS"), "MXN": ("MEXICAN PESO", "MEXICAN PESOS")},
    "es": {"USD": ("DÓLAR", "DÓLARES"), "EUR": ("EURO", "EUROS"), "GTQ": ("QUETZAL", "QUETZALES"),
           "CRC": ("COLÓN", "COLONES"), "HNL": ("LEMPIRA", "LEMPIRAS"), "NIO": ("CÓRDOBA", "CÓRDOBAS"),
           "PAB": ("BALBOA", "BALBOAS"), "MXN": ("PESO MEXICANO", "PESOS MEXICANOS")},
}


def monto_en_letras(valor: float, moneda: str) -> str:
    """4850.00 USD → «FOUR THOUSAND … US DOLLARS AND 00/100» o «CUATRO MIL … DÓLARES CON 00/100»."""
    idioma = idioma_actual()
    entero, centavos = divmod(int(round(valor * 100)), 100)
    sing, plur = MONEDAS.get(idioma, MONEDAS["en"]).get((moneda or "").upper(), (moneda, moneda))
    nombre = sing if entero == 1 else plur
    letras = cantidad_en_letras(entero)
    if idioma == "es":
        if entero and entero % 10**6 == 0:
            letras += " DE"  # «un millón de dólares»
        return f"{letras} {nombre} CON {centavos:02d}/100"
    return f"{letras} {nombre} AND {centavos:02d}/100"
