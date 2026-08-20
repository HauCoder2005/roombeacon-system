FROM python:3.11-slim

ARG DUCKDB_VERSION=1.5.5

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Cài đặt DuckDB cùng các thư viện xử lý dữ liệu tabular cốt lõi
RUN pip install --no-cache-dir \
    duckdb==${DUCKDB_VERSION} \
    pyarrow \
    pandas

CMD ["python", "-c", "import duckdb; print('DuckDB version:', duckdb.__version__)"]
