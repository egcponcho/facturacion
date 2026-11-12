"""Integración con sistemas externos (ERP u otros), desacoplada del núcleo.

- adaptadores.py: formatos de intercambio (archivo tabular, JSON). Un ERP nuevo
  que exporte o importe en uno de estos formatos se conecta con un mapeo; uno
  con otro formato o con conexión directa necesita un adaptador nuevo con el
  mismo contrato.
- entidades.py: qué datos del sistema se intercambian (órdenes de compra de
  entrada, facturas de salida), sus campos y cómo se aplican, siempre por los
  servicios del núcleo con sus validaciones y permisos.
- servicio.py: integraciones, mapeos versionados, ejecuciones (bitácora),
  huellas para no repetir y referencias externas.

Ningún adaptador es propio de un ERP concreto: no se declara compatibilidad
con SAP, Oracle, Dynamics u Odoo sin un adaptador implementado y probado.
"""
