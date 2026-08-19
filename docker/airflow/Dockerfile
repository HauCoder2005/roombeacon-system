ARG AIRFLOW_IMAGE=apache/airflow
ARG AIRFLOW_VERSION=3.3.1

FROM ${AIRFLOW_IMAGE}:${AIRFLOW_VERSION}

USER root

# Cài đặt các gói hệ thống tối thiểu cần thiết để biên dịch mysqlclient nếu cần
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        gcc \
        pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Cài đặt MySQL provider và MySQL driver dành cho Airflow metadata backend
RUN pip install --no-cache-dir \
    apache-airflow-providers-mysql \
    mysqlclient \
    cryptography
