from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_bool, get_str


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


def load_minio_env() -> MinIOEnv:
    return MinIOEnv(
        endpoint=get_str("MINIO_ENDPOINT", default="minio:9000") or "minio:9000",
        access_key=get_str("MINIO_CRAWLER_ACCESS_KEY", default="") or "",
        secret_key=get_str("MINIO_CRAWLER_SECRET_KEY", default="") or "",
        secure=get_bool("MINIO_SECURE", default=False),
        bucket_raw=get_str("MINIO_BUCKET_RAW", default="roombeacon-raw") or "roombeacon-raw",
        bucket_assets=get_str("MINIO_BUCKET_ASSETS", default="roombeacon-assets") or "roombeacon-assets",
        bucket_quarantine=get_str("MINIO_BUCKET_QUARANTINE", default="roombeacon-quarantine") or "roombeacon-quarantine",
        bucket_exports=get_str("MINIO_BUCKET_EXPORTS", default="roombeacon-exports") or "roombeacon-exports",
    )
