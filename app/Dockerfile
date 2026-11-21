# One image, several roles (api | worker | beat | consumer), chosen by the container command.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY pyproject.toml ./
COPY radar ./radar
RUN pip install ".[gcp,kafka,embed]"

# multilingual-e5-small (ONNX, ~120 MB) baked in at build time: RADAR_EMBEDDER=fastembed works offline, on CPU
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN RADAR_EMBEDDER=fastembed python -c "from radar.basal.embed import FastEmbedEmbedder as F; print(F().name)"     && chmod -R a+rX /opt/fastembed
ENV HF_HUB_OFFLINE=1

COPY sources.yaml ./sources.yaml
COPY samples ./samples
COPY alembic.ini ./alembic.ini
COPY eval ./eval

RUN useradd --uid 10001 --create-home radar && mkdir -p /data && chown radar /data
USER 10001
ENV RADAR_SOURCES_FILE=/app/sources.yaml
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
CMD ["uvicorn", "radar.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
