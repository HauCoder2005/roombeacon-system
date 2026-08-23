from datetime import datetime, timedelta, timezone
import re


class BatDongSanDateInterpreter:
    """Phiên dịch chuỗi thời gian đăng tin từ BatDongSan thành datetime chuẩn."""

    @staticmethod
    def interpret(raw_date_str: str | None) -> datetime | None:
        if not raw_date_str:
            return None

        clean_str = raw_date_str.strip().lower()
        now = datetime.now(timezone.utc)

        if "hôm nay" in clean_str:
            return now
        if "hôm qua" in clean_str:
            return now - timedelta(days=1)

        match = re.search(r"(\d+)\s+ngày\s+trước", clean_str)
        if match:
            days = int(match.group(1))
            return now - timedelta(days=days)

        match = re.search(r"(\d+)\s+giờ\s+trước", clean_str)
        if match:
            hours = int(match.group(1))
            return now - timedelta(hours=hours)

        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", clean_str)
        if match:
            d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime(y, m, d, tzinfo=timezone.utc)

        return None
