# Compila el frontend y lo sirve desde el mismo contenedor que la API
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist /frontend/dist
# Sin privilegios de administrador dentro del contenedor
RUN useradd --create-home --uid 1000 app && mkdir -p /data/archivos && chown -R app /data /app
USER app
ENV FRONTEND_DIST=/frontend/dist UPLOAD_DIR=/data/archivos PYTHONUNBUFFERED=1
EXPOSE 8000
# PORT lo define la plataforma en la nube (Render, Railway, Cloud Run); 8000 en local.
# --forwarded-allow-ips: solo detrás del proxy de la plataforma (ver docs/PRODUCCION.md).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
