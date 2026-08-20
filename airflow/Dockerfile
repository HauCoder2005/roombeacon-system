ARG AIRFLOW_IMAGE=apache/airflow
ARG AIRFLOW_VERSION=3.3.1

FROM ${AIRFLOW_IMAGE}:${AIRFLOW_VERSION}

USER root

# Cài đặt các gói hệ thống tối thiểu cần thiết để biên dịch mysqlclient và chạy Chromium Playwright
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        gcc \
        pkg-config \
        curl \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2t64 \
        libpango-1.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Cài đặt MySQL provider, driver và crawler dependencies
RUN pip install --no-cache-dir \
    apache-airflow-providers-mysql \
    mysqlclient \
    cryptography \
    playwright \
    httpx \
    beautifulsoup4 \
    pydantic \
    python-dotenv \
    && playwright install chromium
