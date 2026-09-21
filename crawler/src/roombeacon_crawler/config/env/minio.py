from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_bool, get_int, get_str


@dataclass(frozen=True, slots=True)
class MinIOEnv:
    endpoint: str
    access_key: str
    secret_key: str
    secure: bool
    bucket_raw: str
    bucket_assets: str
    bucket_quarantine: str
    bucket_exports: str
    host: str = "minio"
    port: int = 9000
    root_user: str = ""
    root_password: str = ""
    raw_mirror_enabled: bool = True


def load_minio_env() -> MinIOEnv:
    endpoint = get_str("MINIO_ENDPOINT", default="minio:9000") or "minio:9000"

    # Parse host & port fallback from endpoint
    ep_host = endpoint.split(":")[0] if ":" in endpoint else endpoint
    ep_port = int(endpoint.split(":")[1]) if ":" in endpoint and endpoint.split(":")[1].isdigit() else 9000

    host = get_str("MINIO_HOST", default=ep_host) or ep_host
    port = get_int("MINIO_PORT", default=ep_port) or get_int("MINIO_API_PORT", default=ep_port) or ep_port

    return MinIOEnv(
        endpoint=endpoint,
        access_key=get_str("MINIO_CRAWLER_ACCESS_KEY", default="") or "",
        secret_key=get_str("MINIO_CRAWLER_SECRET_KEY", default="") or "",
        secure=get_bool("MINIO_SECURE", default=False),
        bucket_raw=get_str("MINIO_BUCKET_RAW", default="roombeacon-raw") or "roombeacon-raw",
        bucket_assets=get_str("MINIO_BUCKET_ASSETS", default="roombeacon-assets") or "roombeacon-assets",
        bucket_quarantine=get_str("MINIO_BUCKET_QUARANTINE", default="roombeacon-quarantine") or "roombeacon-quarantine",
        bucket_exports=get_str("MINIO_BUCKET_EXPORTS", default="roombeacon-exports") or "roombeacon-exports",
        host=host,
        port=port,
        root_user=get_str("MINIO_ROOT_USER", default="") or "",
        root_password=get_str("MINIO_ROOT_PASSWORD", default="") or "",
        raw_mirror_enabled=get_bool("MINIO_RAW_MIRROR_ENABLED", default=True),
    )
