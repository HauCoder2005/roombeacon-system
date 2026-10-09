#!/bin/sh
# Create (or update) the read-only MinIO account the REST API uses for listing images.
# Additive: does not touch the existing bootstrap, buckets or the crawler account.
#
# Run once via the bootstrap image (root credentials come from Compose; the
# reader credentials from your shell, e.g. after `set -a; . ./.env.local; set +a`):
#   docker compose run --rm --no-deps -e MINIO_API_READER_ACCESS_KEY -e MINIO_API_READER_SECRET_KEY \
#     --entrypoint /bin/sh minio-bootstrap /bootstrap/create_api_reader.sh
set -eu

: "${MINIO_ROOT_USER:?MINIO_ROOT_USER is unset}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is unset}"
: "${MINIO_API_READER_ACCESS_KEY:?MINIO_API_READER_ACCESS_KEY is unset}"
: "${MINIO_API_READER_SECRET_KEY:?MINIO_API_READER_SECRET_KEY is unset}"

alias_name="roombeacon"
policy_name="roombeacon-assets-reader"
policy_file="/bootstrap/policies/roombeacon-assets-reader.json"

until mc alias set "${alias_name}" "http://minio:9000" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null 2>&1; do
    echo "Waiting for MinIO endpoint..."
    sleep 2
done

if ! mc admin user info "${alias_name}" "${MINIO_API_READER_ACCESS_KEY}" >/dev/null 2>&1; then
    mc admin user add "${alias_name}" "${MINIO_API_READER_ACCESS_KEY}" "${MINIO_API_READER_SECRET_KEY}" >/dev/null
fi
mc admin policy create "${alias_name}" "${policy_name}" "${policy_file}" >/dev/null
mc admin policy attach "${alias_name}" "${policy_name}" --user "${MINIO_API_READER_ACCESS_KEY}" >/dev/null 2>&1 || true

# Verify: the reader can list the assets bucket but cannot write.
mc alias set roombeacon-api-reader "http://minio:9000" "${MINIO_API_READER_ACCESS_KEY}" "${MINIO_API_READER_SECRET_KEY}" >/dev/null
mc ls "roombeacon-api-reader/roombeacon-assets" >/dev/null
if echo probe | mc pipe "roombeacon-api-reader/roombeacon-assets/.api-reader-write-probe" >/dev/null 2>&1; then
    mc rm "${alias_name}/roombeacon-assets/.api-reader-write-probe" >/dev/null 2>&1 || true
    echo "ERROR: the API reader account can write to the assets bucket" >&2
    exit 1
fi
echo "API reader account ready (read-only on roombeacon-assets)."
