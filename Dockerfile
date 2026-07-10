FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system verdictmesh \
    && useradd --system --gid verdictmesh --home-dir /app verdictmesh

COPY pyproject.toml README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && chown -R verdictmesh:verdictmesh /app

USER verdictmesh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn verdictmesh.api:app --host 0.0.0.0 --port 8000"]
