# Radar innowacji: konektory, baza SQLite, przeglądarka danych i harmonogram odświeżania.
# Jeden obraz, komenda wybiera rolę (patrz radar/container.py i docker-compose.yml).
# Obraz bazowy; gdy Docker Hub odpowiada 429 (limit pobrań), ten sam obraz jest w lustrze Google:
#   docker compose build --build-arg BASE_IMAGE=mirror.gcr.io/library/python:3.12-slim
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# 1 = z biblioteką anthropic (karty przez Claude, gdy jest ANTHROPIC_API_KEY); 0 = tylko tryb offline
ARG WITH_LLM=1
# 1 = z biblioteką pypdf (BSD): crawler wyciąga tekst z dokumentów PDF; 0 = PDF-y są pomijane
ARG WITH_PDF=1

ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Warsaw \
    HOME=/tmp \
    RADAR_DB=/app/data/radar.db \
    PORT=8765

RUN if [ "$WITH_LLM" = "1" ]; then pip install anthropic; fi \
 && if [ "$WITH_PDF" = "1" ]; then pip install pypdf; fi \
 && useradd --create-home --uid 1000 radar \
 && mkdir -p /app/data && chown radar:radar /app/data

WORKDIR /app
COPY radar/ ./radar/
COPY config/ ./config/
COPY pyproject.toml ./

USER radar
VOLUME /app/data
EXPOSE 8765

ENTRYPOINT ["python", "-m", "radar.container"]
CMD ["gui"]
