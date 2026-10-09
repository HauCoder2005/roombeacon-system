FROM python:3.12.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 roombeacon \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin roombeacon

WORKDIR /app
COPY api/pyproject.toml /app/api/pyproject.toml
COPY api/src/ /app/api/src/
RUN pip install /app/api

USER 10001:10001
EXPOSE 8000

# One worker: the rate limiter keeps its state in process memory.
CMD ["uvicorn", "roombeacon_api.main:app_factory", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--no-server-header", "--no-access-log", \
     "--timeout-keep-alive", "5", "--limit-concurrency", "100"]
