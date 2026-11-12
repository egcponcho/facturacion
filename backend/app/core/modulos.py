"""Contrato y registro de módulos.

Un módulo es una carpeta `app/modulos/<clave>/` con un archivo `modulo.py`
que expone `MODULO = Modulo(...)`. Ese objeto es lo único que la aplicación
(`app/main.py`) conoce del módulo:

    MODULO = Modulo(
        clave="compras",                                  # la carpeta
        nombre="Órdenes de compra",                       # su sección en la documentación de la API
        descripcion="Órdenes de compra: importación…",
        rutas=lambda: [api.router, api_flujo.router],     # routers de FastAPI, todos bajo /api
        etiqueta="",                                      # otra sección de la documentación, si la comparte
        al_cargar=_registrar,                             # se inscribe en los registros de otros
        tareas=(),                                        # tareas de fondo mientras corre el servidor
    )

Cómo se conectan los módulos sin conocerse: un módulo publica un registro
(por ejemplo `comun.edicion.registrar_documento` o
`catalogo.secciones.registrar_seccion_familia`) y los demás se inscriben en
él desde el `al_cargar` de su `modulo.py`. Así quien publica el registro no
importa a nadie, y agregar o quitar un módulo no toca a los otros.

`core` no conoce ningún módulo: recorre las carpetas y lee su contrato.
Las reglas de dependencias están en tests/test_arquitectura.py.

Qué módulos usa cada empresa se decide aparte, en Configuración → Empresa →
Módulos (`acceso/permisos.py`, MODULOS_ACTIVABLES): el código de todos está
cargado y la empresa apaga los que no usa.
"""
from __future__ import annotations

import importlib
import importlib.util
import pkgutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

PAQUETE = "app.modulos"


@dataclass(frozen=True)
class Modulo:
    clave: str
    nombre: str
    descripcion: str = ""
    # Routers de FastAPI. Es una función para que los routers se importen al cargar, no al leer el contrato
    rutas: Callable[[], list] = field(default=lambda: [])
    # Lo que el módulo inscribe en registros ajenos (secciones de familia, documentos editables…)
    al_cargar: Callable[[], None] | None = None
    # Corrutinas que corren mientras el servidor está arriba (se cancelan al apagarlo)
    tareas: tuple[Callable[[], Awaitable[None]], ...] = ()
    # Sección de la documentación de la API en la que van sus rutas (por omisión, su nombre)
    etiqueta: str = ""

    @property
    def seccion(self) -> str:
        return self.etiqueta or self.nombre

    def resumen(self) -> dict:
        """Lo que se publica del módulo (GET /api/modulos)."""
        return {"clave": self.clave, "nombre": self.nombre, "descripcion": self.descripcion}


def disponibles() -> list[str]:
    """Las carpetas de app/modulos/ que tienen modulo.py."""
    paquete = importlib.import_module(PAQUETE)
    return sorted(m.name for m in pkgutil.iter_modules(paquete.__path__)
                  if m.ispkg and importlib.util.find_spec(f"{PAQUETE}.{m.name}.modulo") is not None)


_CARGADOS: list[Modulo] | None = None


def cargar() -> list[Modulo]:
    """Lee el contrato de cada módulo, corre su `al_cargar` (una sola vez por
    proceso) y los devuelve por clave. Ninguna ruta de un módulo tapa a la de
    otro (lo revisa tests/test_modulos.py), así el orden entre módulos no importa."""
    global _CARGADOS
    if _CARGADOS is None:
        contratos = []
        for clave in disponibles():
            m = importlib.import_module(f"{PAQUETE}.{clave}.modulo").MODULO
            if m.clave != clave:
                raise RuntimeError(f"app/modulos/{clave}/modulo.py declara la clave «{m.clave}».")
            contratos.append(m)
        for m in contratos:
            if m.al_cargar:
                m.al_cargar()
        _CARGADOS = contratos
    return _CARGADOS
