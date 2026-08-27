#!/bin/sh
set -eu

alias_name="roombeacon"
assets_policy="roombeacon-assets-writer"
policy_file="/bootstrap/policies/roombeacon-assets-writer.json"

required_variables="MINIO_ROOT_USER MINIO_ROOT_PASSWORD MINIO_CRAWLER_ACCESS_KEY MINIO_CRAWLER_SECRET_KEY MINIO_BUCKET_RAW MINIO_BUCKET_ASSETS MINIO_BUCKET_QUARANTINE MINIO_BUCKET_EXPORTS"
for variable_name in ${required_variables}; do
    eval "variable_value=\${${variable_name}:-}"
    if [ -z "${variable_value}" ]; then
        echo "MinIO bootstrap configuration is incomplete: ${variable_name} is unset." >&2
        exit 1
    fi
done

until /usr/bin/mc alias set \
    "${alias_name}" \
    "http://minio:9000" \
    "${MINIO_ROOT_USER}" \
    "${MINIO_ROOT_PASSWORD}" >/dev/null 2>&1; do
    echo "Waiting for MinIO endpoint..."
    sleep 2
done

for bucket_name in \
    "${MINIO_BUCKET_RAW}" \
    "${MINIO_BUCKET_ASSETS}" \
    "${MINIO_BUCKET_QUARANTINE}" \
    "${MINIO_BUCKET_EXPORTS}"; do
    /usr/bin/mc mb --ignore-existing "${alias_name}/${bucket_name}" >/dev/null
done

if ! /usr/bin/mc admin user info \
    "${alias_name}" \
    "${MINIO_CRAWLER_ACCESS_KEY}" >/dev/null 2>&1; then
    /usr/bin/mc admin user add \
        "${alias_name}" \
        "${MINIO_CRAWLER_ACCESS_KEY}" \
        "${MINIO_CRAWLER_SECRET_KEY}" >/dev/null
fi

/usr/bin/mc admin policy create \
    "${alias_name}" \
    "${assets_policy}" \
    "${policy_file}" >/dev/null

/usr/bin/mc admin policy attach \
    "${alias_name}" \
    "${assets_policy}" \
    --user "${MINIO_CRAWLER_ACCESS_KEY}" >/dev/null

echo "MinIO buckets and scoped crawler asset policy provisioned successfully."
