from dataclasses import dataclass
from urllib.parse import quote_plus
from roombeacon_crawler.config.env.loader import get_int, get_str


@dataclass(frozen=True, slots=True)
class BronzeMySQLEnv:
    host: str
    port: int
    database: str
    user: str
    password: str
    sqlalchemy_url: str
    charset: str = "utf8mb4"
    collation: str = "utf8mb4_unicode_ci"


def load_bronze_mysql_env() -> BronzeMySQLEnv:
    host = get_str("BRONZE_MYSQL_HOST", default="mysql-bronze") or "mysql-bronze"
    port = get_int("BRONZE_MYSQL_PORT", default=3306) or 3306
    database = get_str("BRONZE_MYSQL_DATABASE", default="roombeacon_bronze") or "roombeacon_bronze"
    user = get_str("BRONZE_MYSQL_USER", default="roombeacon_bronze_user") or "roombeacon_bronze_user"
    password = get_str("BRONZE_MYSQL_PASSWORD", default="") or ""
    charset = get_str("MYSQL_CHARSET", default="utf8mb4") or "utf8mb4"
    collation = get_str("MYSQL_COLLATION", default="utf8mb4_unicode_ci") or "utf8mb4_unicode_ci"

    encoded_user = quote_plus(user)
    encoded_pass = quote_plus(password)
    sqlalchemy_url = (
        f"mysql+pymysql://{encoded_user}:{encoded_pass}@{host}:{port}/{database}"
        f"?charset={charset}"
    )

    return BronzeMySQLEnv(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        sqlalchemy_url=sqlalchemy_url,
        charset=charset,
        collation=collation,
    )
