#!/usr/bin/env bash
set -euo pipefail

# Execute where RoomBeacon runtime config, Airflow CLI, and /data are active.
container_name="roombeacon-airflow-scheduler"
container_script="/tmp/reset_roombeacon_data.py"

docker cp "$(dirname "$0")/reset_roombeacon_data.py" "${container_name}:${container_script}"
docker exec "${container_name}" python "${container_script}" "$@"
