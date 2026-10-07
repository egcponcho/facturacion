# Base oficial del SAC (SIECA)

Genera `app/data/oficial/sac_notas.json`, `sac_oficial.json` y `aci_incisos.json` (y aparte, en `app/data/motor/interpretacion_aci.json`, lo que el clasificador lee del texto) desde el
Arancel Centroamericano de Importación publicado por SIECA
(https://www.sieca.int/producto/arancel-centroamericano-de-importacion/,
VII Enmienda del SAC, versión 6 de agosto de 2025).

1. Descargar el PDF del ACI y extraer su texto a `sac.txt` (por ejemplo con PyMuPDF:
   una línea `<<<PAG n>>>` antes del texto de cada página).
2. En la carpeta de `sac.txt`: `python extraer_notas.py`, `python extraer_codigos.py` y
   `python armar_datos.py`.
3. Subir `ESQUEMA_VERSION` para recargar la base demo, o cargar los archivos desde
   *Tariff schedule* (notas y códigos nacionales por Excel).

Las condiciones de cada inciso se deducen de su texto (puntera metálica, que cubran
el tobillo o la rodilla, cubrecalzado, para hombres/mujeres/bebés, sombreros); las de
la base ADOC se conservan cuando el inciso coincide.
