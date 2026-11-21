# BoaPauta: app React (compilado) + API FastAPI num container só.
#   docker compose up --build      → http://localhost:8000

# 1) compila o app React
FROM node:20-slim AS app
WORKDIR /app
COPY app/package*.json ./
RUN npm ci
COPY app/ ./
RUN npm run build

# 2) API Python servindo a API e o app compilado
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONPATH=/srv PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
COPY requirements.txt ./
# libatomic1: o Node embutido no Playwright precisa dela e a imagem slim não traz
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m playwright install --with-deps chromium
COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/
COPY --from=app /app/dist app/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/segmentos')"
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
