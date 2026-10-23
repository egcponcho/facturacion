"""Catálogo: familias, atributos, productos y artículos (variantes y packs).

Es el único módulo dueño de esas tablas. Los demás módulos lo leen solo por su
servicio (`catalogo.servicio`), que devuelve fichas ya armadas y consultas de
ids para filtrar; ninguno importa sus modelos (tests/test_arquitectura.py).
"""
