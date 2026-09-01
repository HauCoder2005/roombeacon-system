#!/bin/sh
set -eu

alias_name="roombeacon"
crawler_alias="roombeacon-crawler"
assets_policy="roombeacon-assets-writer"
policy_file="/bootstrap/policies/roombeacon-assets-writer.json"
verification_file="/tmp/roombeacon-minio-permission-check"
verification_key=".roombeacon-bootstrap/permission-check"

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

/usr/bin/mc alias set \
    "${crawler_alias}" \
    "http://minio:9000" \
    "${MINIO_CRAWLER_ACCESS_KEY}" \
    "${MINIO_CRAWLER_SECRET_KEY}" >/dev/null

cleanup_verification_objects() {
    /usr/bin/mc rm --force \
        "${alias_name}/${MINIO_BUCKET_ASSETS}/${verification_key}" \
        >/dev/null 2>&1 || true
    /usr/bin/mc rm --force \
        "${alias_name}/${MINIO_BUCKET_RAW}/${verification_key}" \
        >/dev/null 2>&1 || true
}

cleanup_verification() {
    cleanup_verification_objects
    rm -f "${verification_file}"
}

verify_crawler_permissions() {
    # Some mc releases print an S3 error while still returning success for ls,
    # so reject error output explicitly as well as non-zero exit codes.
    list_output=$(
        /usr/bin/mc ls "${crawler_alias}/${MINIO_BUCKET_ASSETS}" 2>&1
    ) || return 1
    case "${list_output}" in
        *"<ERROR>"*|*"Access Denied"*) return 1 ;;
    esac

    for bucket_name in "${MINIO_BUCKET_ASSETS}" "${MINIO_BUCKET_RAW}"; do
        /usr/bin/mc pipe \
            "${crawler_alias}/${bucket_name}/${verification_key}" \
            < "${verification_file}" >/dev/null 2>&1 || return 1

        # Root stat proves PutObject created the canary. Crawler cat proves
        # GetObject can read it without requiring ListBucket or DeleteObject.
        /usr/bin/mc stat \
            "${alias_name}/${bucket_name}/${verification_key}" \
            >/dev/null 2>&1 || return 1
        /usr/bin/mc cat \
            "${crawler_alias}/${bucket_name}/${verification_key}" \
            >/dev/null 2>&1 || return 1
    done
}

trap cleanup_verification EXIT INT TERM
printf 'RoomBeacon MinIO permission verification.\n' > "${verification_file}"

# Verify only the permissions used by the crawler storage flow. Root credentials
# remove the temporary objects because the crawler policy intentionally excludes
# DeleteObject.
verification_attempt=1
verification_succeeded=false
while [ "${verification_attempt}" -le 10 ]; do
    cleanup_verification_objects
    if verify_crawler_permissions; then
        verification_succeeded=true
        break
    fi
    verification_attempt=$((verification_attempt + 1))
    sleep 1
done

if [ "${verification_succeeded}" != "true" ]; then
    echo "Crawler credentials or MinIO policy verification failed." >&2
    exit 1
fi

cleanup_verification
trap - EXIT INT TERM

echo "MinIO buckets and scoped crawler asset policy provisioned successfully."
