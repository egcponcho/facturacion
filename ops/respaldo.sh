#!/usr/bin/env bash
# Respaldo de la base (pg_dump, formato propio de PostgreSQL) y de los archivos
# subidos (UPLOAD_DIR) en una carpeta con fecha. Borra los respaldos con más
# de RETENCION_DIAS días. Pensado para correr cada noche (cron o el
# programador de tareas del proveedor de nube). Guía: docs/PRODUCCION.md §8.
#
#   DATABASE_URL=postgresql://usuario:clave@servidor/base \
#   UPLOAD_DIR=/data/archivos DESTINO=/respaldos ops/respaldo.sh
set -euo pipefail

: "${DATABASE_URL:?Defina DATABASE_URL (la misma de la aplicación)}"
: "${UPLOAD_DIR:?Defina UPLOAD_DIR (la carpeta de archivos de la aplicación)}"
DESTINO="${DESTINO:-./respaldos}"
RETENCION_DIAS="${RETENCION_DIAS:-14}"

# pg_dump no entiende el prefijo de SQLAlchemy (postgresql+psycopg://)
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
URL="${URL/postgres:\/\//postgresql://}"
case "$URL" in
  postgresql://*) ;;
  *) echo "Solo se respaldan bases PostgreSQL (DATABASE_URL=$DATABASE_URL)." >&2; exit 1 ;;
esac

carpeta="$DESTINO/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$carpeta"
pg_dump --format=custom --no-owner --file "$carpeta/base.dump" "$URL"
if [ -d "$UPLOAD_DIR" ]; then
  tar -czf "$carpeta/archivos.tar.gz" -C "$UPLOAD_DIR" .
fi
# Huella de cada parte: la restauración la verifica antes de tocar nada
(cd "$carpeta" && sha256sum ./* > SHA256SUMS)
echo "Respaldo listo: $carpeta"

find "$DESTINO" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENCION_DIAS" -exec rm -rf {} +
