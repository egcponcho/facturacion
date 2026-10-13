"""Tipos comunes de las peticiones: cantidades enteras o con decimales."""
from typing import Annotated

from pydantic import AfterValidator, Field

from app.modelos import cant

Cant = Field(gt=0)
# Cantidad de un artículo: entera para lo que se cuenta, hasta 3 decimales para
# lo que se mide (el servicio valida contra la unidad de la posición)
Cantidad = Annotated[float, Field(gt=0), AfterValidator(cant)]
CantidadCero = Annotated[float, Field(ge=0), AfterValidator(cant)]
