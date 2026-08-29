FROM python:3.11-slim

ARG DUCKDB_VERSION=1.5.5

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dùng chung crawler config và analytics source thay vì tạo một runtime rỗng
# chỉ in phiên bản DuckDB.
COPY crawler/pyproject.toml /app/crawler/pyproject.toml
COPY crawler/src/ /app/crawler/src/
COPY analytics/ /app/analytics/

RUN pip install --no-cache-dir \
    -e /app/crawler \
    duckdb==${DUCKDB_VERSION} \
    pyarrow \
    pandas

ENV PYTHONPATH=/app:/app/crawler/src

CMD ["python", "-m", "analytics.duckdb.bootstrap"]
