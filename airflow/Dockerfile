ARG AIRFLOW_IMAGE=apache/airflow
ARG AIRFLOW_VERSION=3.3.1

FROM ${AIRFLOW_IMAGE}:${AIRFLOW_VERSION}

USER root

# Cài đặt các gói hệ thống cần thiết để biên dịch mysqlclient
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        gcc \
        pkg-config \
        curl \
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
    python-dotenv

USER root

# Cài đặt toàn bộ system dependencies cần thiết của Chromium
RUN playwright install-deps chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Cài đặt trình duyệt Chromium cho user airflow
RUN playwright install chromium
