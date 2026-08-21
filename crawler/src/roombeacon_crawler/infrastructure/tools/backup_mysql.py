import gzip
import logging
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
from roombeacon_crawler.config.get_env import env

logger = logging.getLogger("MYSQL_BACKUP")


def backup_mysql_database(
    database_name: str | None = None,
    backup_dir: str | Path | None = None,
    compress: bool = True,
) -> Path:
    """Tạo bản sao lưu logic (mysqldump) an toàn cho MySQL Database.

    - Không in hoặc để lộ mật khẩu ra console/logs.
    - Tạo tệp có gắn nhãn thời gian timestamped (YYYYMMDD_HHMMSS).
    - Tùy chọn nén gzip để tiết kiệm dung lượng đĩa vật lý.
    - Kiểm tra tính toàn vẹn và đảm bảo tệp kết quả không rỗng.
    """
    db_config = env.mysql_bronze
    target_db = database_name or db_config.database
    host = db_config.host
    port = str(db_config.port)
    user = db_config.user
    password = db_config.password

    # Xác định thư mục lưu trữ backup vật lý
    if backup_dir:
        out_dir = Path(backup_dir)
    elif Path("/data/backups/mysql").exists() or Path("/data").exists():
        out_dir = Path("/data/backups/mysql")
    else:
        out_dir = Path("./data/backups/mysql")

    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw_sql_path = out_dir / f"{target_db}_{timestamp}.sql"
    final_path = out_dir / f"{target_db}_{timestamp}.sql.gz" if compress else raw_sql_path

    logger.info("Bắt đầu backup cơ sở dữ liệu '%s' tới '%s'...", target_db, final_path)

    # Sử dụng biến môi trường MYSQL_PWD để mysqldump không lộ pass trên CLI arguments
    proc_env = os.environ.copy()
    proc_env["MYSQL_PWD"] = password

    cmd = [
        "mysqldump",
        f"-h{host}",
        f"-P{port}",
        f"-u{user}",
        "--single-transaction",
        "--routines",
        "--triggers",
        target_db,
    ]

    try:
        with open(raw_sql_path, "wb") as f_out:
            proc = subprocess.run(
                cmd,
                stdout=f_out,
                stderr=subprocess.PIPE,
                env=proc_env,
                check=True,
            )

        # Kiểm tra file đã tạo và có kích thước > 0
        if not raw_sql_path.exists() or raw_sql_path.stat().st_size == 0:
            raise RuntimeError(f"Backup file '{raw_sql_path}' rỗng hoặc không tồn tại.")

        if compress:
            with open(raw_sql_path, "rb") as f_in, gzip.open(final_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            raw_sql_path.unlink(missing_ok=True)

        logger.info(
            "Backup thành công database '%s'! Tệp: %s (Kích thước: %d bytes)",
            target_db,
            final_path,
            final_path.stat().st_size,
        )
        return final_path

    except subprocess.CalledProcessError as err:
        err_msg = err.stderr.decode("utf-8", errors="replace") if err.stderr else str(err)
        logger.error("Lỗi khi chạy mysqldump cho database '%s': %s", target_db, err_msg)
        if raw_sql_path.exists():
            raw_sql_path.unlink(missing_ok=True)
        raise RuntimeError(f"Lỗi mysqldump: {err_msg}") from err
    except Exception as exc:
        logger.exception("Lỗi không xác định khi backup MySQL: %s", exc)
        if raw_sql_path.exists():
            raw_sql_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    backup_mysql_database()
