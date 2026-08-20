FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Cài đặt Playwright dependencies nếu chạy browser trong container
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY src/ /app/src/

RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir playwright httpx python-dotenv \
    && playwright install --with-deps chromium

CMD ["python", "-m", "roombeacon_crawler.main"]
