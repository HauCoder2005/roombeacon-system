#!/bin/bash
# Runs once, on first start with an empty data volume, as the bootstrap admin
# (CLICKHOUSE_USER from .env.local). Creates the least-privilege loader account
# and an optional read-only account, both scoped to CLICKHOUSE_DB only.
# Re-run manually after changing these passwords (see docs runbook).
set -euo pipefail

identifier='^[A-Za-z_][A-Za-z0-9_]{0,62}$'
safe_secret='^[A-Za-z0-9._~+=@%^-]{16,128}$'

require_identifier() {
    [[ "$2" =~ $identifier ]] || { echo "$1 must be a plain identifier" >&2; exit 64; }
}
require_secret() {
    [[ "$2" =~ $safe_secret ]] || {
        echo "$1 must be 16-128 chars of [A-Za-z0-9._~+=@%^-]" >&2; exit 64;
    }
}

: "${CLICKHOUSE_DB:?CLICKHOUSE_DB must be set in .env.local}"
: "${WAREHOUSE_CLICKHOUSE_USER:?WAREHOUSE_CLICKHOUSE_USER must be set in .env.local}"
: "${WAREHOUSE_CLICKHOUSE_PASSWORD:?WAREHOUSE_CLICKHOUSE_PASSWORD must be set in .env.local}"
require_identifier CLICKHOUSE_DB "$CLICKHOUSE_DB"
require_identifier WAREHOUSE_CLICKHOUSE_USER "$WAREHOUSE_CLICKHOUSE_USER"
require_secret WAREHOUSE_CLICKHOUSE_PASSWORD "$WAREHOUSE_CLICKHOUSE_PASSWORD"

sql="CREATE DATABASE IF NOT EXISTS \`${CLICKHOUSE_DB}\`;
CREATE USER IF NOT EXISTS \`${WAREHOUSE_CLICKHOUSE_USER}\` IDENTIFIED WITH sha256_password BY '${WAREHOUSE_CLICKHOUSE_PASSWORD}' DEFAULT DATABASE \`${CLICKHOUSE_DB}\`;
GRANT SELECT, INSERT, CREATE TABLE, DROP TABLE, TRUNCATE ON \`${CLICKHOUSE_DB}\`.* TO \`${WAREHOUSE_CLICKHOUSE_USER}\`;"

if [[ -n "${WAREHOUSE_READER_USER:-}" ]]; then
    : "${WAREHOUSE_READER_PASSWORD:?WAREHOUSE_READER_PASSWORD must be set when WAREHOUSE_READER_USER is}"
    require_identifier WAREHOUSE_READER_USER "$WAREHOUSE_READER_USER"
    require_secret WAREHOUSE_READER_PASSWORD "$WAREHOUSE_READER_PASSWORD"
    sql="${sql}
CREATE USER IF NOT EXISTS \`${WAREHOUSE_READER_USER}\` IDENTIFIED WITH sha256_password BY '${WAREHOUSE_READER_PASSWORD}' DEFAULT DATABASE \`${CLICKHOUSE_DB}\` SETTINGS PROFILE 'roombeacon_reader';
GRANT SELECT ON \`${CLICKHOUSE_DB}\`.* TO \`${WAREHOUSE_READER_USER}\`;"
fi

# Pass credentials through the environment, never on the command line.
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD}" clickhouse client \
    --user "${CLICKHOUSE_USER}" --multiquery <<<"${sql}"
echo "RoomBeacon ClickHouse accounts provisioned for database ${CLICKHOUSE_DB}"
