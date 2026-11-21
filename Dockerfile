# Radar innowacji: konektory, baza SQLite, przeglądarka danych i harmonogram odświeżania.
# Jeden obraz, komenda wybiera rolę (patrz radar/container.py i docker-compose.yml).
FROM python:3.12-slim

# 1 = z biblioteką anthropic (karty przez Claude, gdy jest ANTHROPIC_API_KEY); 0 = tylko tryb offline
ARG WITH_LLM=1

ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Warsaw \
    HOME=/tmp \
    RADAR_DB=/app/data/radar.db \
    PORT=8765

RUN if [ "$WITH_LLM" = "1" ]; then pip install anthropic; fi \
 && useradd --create-home --uid 1000 radar \
 && mkdir -p /app/data && chown radar:radar /app/data

WORKDIR /app
COPY radar/ ./radar/
COPY pyproject.toml ./

USER radar
VOLUME /app/data
EXPOSE 8765

ENTRYPOINT ["python", "-m", "radar.container"]
CMD ["gui"]
