"""Módulos de negocio. Cada carpeta es un módulo:

- `modulo.py`: su contrato (`MODULO = Modulo(...)`, ver app/core/modulos.py).
  Es lo único que la aplicación lee del módulo: sus rutas, sus tareas de
  fondo y lo que inscribe en los registros de otros módulos.
- Servicios (reglas y consultas) en archivos con nombre de lo que hacen.
- `api*.py`: rutas HTTP. Solo validan, delegan en los servicios y confirman
  la transacción.

Las dependencias permitidas entre módulos las revisa tests/test_dependencias.py.
"""
