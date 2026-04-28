# ============================================================
# WorldBox Writer — Production Dockerfile
# Multi-stage build: backend + frontend
# ============================================================

# ---------- Stage 1: Backend dependencies ----------
FROM python:3.11-slim AS backend-deps
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip install --no-cache-dir dist/*.whl

# ---------- Stage 2: Backend runtime ----------
FROM python:3.11-slim AS backend
WORKDIR /app
COPY --from=backend-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY src/ ./src/
COPY assets/ ./assets/
COPY scripts/ ./scripts/
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1
CMD ["python", "-m", "uvicorn", "worldbox_writer.api.server:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------- Stage 3: Frontend build ----------
FROM node:20-slim AS frontend-build
WORKDIR /app
RUN npm install -g pnpm@9.15.9
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

# ---------- Stage 4: Frontend runtime ----------
FROM nginx:alpine AS frontend
COPY --from=frontend-build /app/dist /usr/share/nginx/html
RUN echo 'server { \
    listen 80; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { try_files $uri $uri/ /index.html; } \
    location /api { proxy_pass http://backend:8000; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; } \
}' > /etc/nginx/conf.d/default.conf
EXPOSE 80
