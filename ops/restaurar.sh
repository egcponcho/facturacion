#!/usr/bin/env bash
# Restaura un respaldo hecho con ops/respaldo.sh: la base (reemplaza su
# contenido) y los archivos subidos. Detenga la aplicación antes. Guía:
# docs/PRODUCCION.md §7.
#
#   DATABASE_URL=postgresql://usuario:clave@servidor/base \
#   UPLOAD_DIR=/data/archivos ops/restaurar.sh /respaldos/20261009T020000Z
set -euo pipefail

carpeta="${1:?Indique la carpeta del respaldo}"
: "${DATABASE_URL:?Defina DATABASE_URL}"
: "${UPLOAD_DIR:?Defina UPLOAD_DIR}"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
URL="${URL/postgres:\/\//postgresql://}"

(cd "$carpeta" && sha256sum --check --quiet SHA256SUMS)
if [ "${CONFIRMAR:-}" != "si" ]; then
  echo "Esto reemplaza la base y los archivos actuales. Repita con CONFIRMAR=si para continuar." >&2
  exit 1
fi
pg_restore --clean --if-exists --no-owner --single-transaction --dbname "$URL" "$carpeta/base.dump"
if [ -f "$carpeta/archivos.tar.gz" ]; then
  mkdir -p "$UPLOAD_DIR"
  tar -xzf "$carpeta/archivos.tar.gz" -C "$UPLOAD_DIR"
fi
echo "Restaurado desde $carpeta. Arranque la aplicación: aplicará las migraciones que falten."
