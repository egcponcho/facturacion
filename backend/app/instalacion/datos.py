"""Dónde vive cada capa de datos incluidos (nunca se mezclan):

- data/oficial: lo publicado por fuentes oficiales (paquetes 01 y 03, árbol del
  ACI de SIECA, notas legales). Solo se carga como dato oficial.
- data/motor: configuración del motor de clasificación (paquete 02, atributos,
  reglas, categorías técnicas, guía del clasificador y la interpretación que el
  clasificador hace del texto oficial). Nunca es dato oficial.
- data/demo: la empresa de demostración (historial, palabras clave, acuerdos
  de referencia). Solo se carga con SEED_DEMO=1.
"""
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
OFICIAL = DATA / "oficial"
MOTOR = DATA / "motor"
DEMO = DATA / "demo"
