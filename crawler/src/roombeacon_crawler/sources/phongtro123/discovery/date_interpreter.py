from datetime import datetime, timedelta, timezone
import re


class Phongtro123DateInterpreter:
    """Phiên dịch chuỗi thời gian tương đối (vd: 'Hôm nay', '4 giờ trước', '2 ngày trước', '15/08/2026') thành datetime UTC."""

    RELATIVE_REGEX = re.compile(
        r"(\d+)\s*(phút|giờ|ngày|tuần|tháng)\s+trước", re.IGNORECASE
    )
    DATE_FORMAT_REGEX = re.compile(
        r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", re.IGNORECASE
    )

    def interpret(self, raw_date_str: str | None) -> datetime | None:
        if not raw_date_str:
            return None

        cleaned = raw_date_str.strip().lower()
        now = datetime.now(timezone.utc)

        if "hôm nay" in cleaned or "vừa xong" in cleaned:
            return now
        if "hôm qua" in cleaned:
            return now - timedelta(days=1)

        rel_match = self.RELATIVE_REGEX.search(cleaned)
        if rel_match:
            val = int(rel_match.group(1))
            unit = rel_match.group(2)
            if "phút" in unit:
                return now - timedelta(minutes=val)
            elif "giờ" in unit:
                return now - timedelta(hours=val)
            elif "ngày" in unit:
                return now - timedelta(days=val)
            elif "tuần" in unit:
                return now - timedelta(weeks=val)
            elif "tháng" in unit:
                return now - timedelta(days=val * 30)

        dt_match = self.DATE_FORMAT_REGEX.search(cleaned)
        if dt_match:
            d, m, y = int(dt_match.group(1)), int(dt_match.group(2)), int(dt_match.group(3))
            try:
                return datetime(y, m, d, tzinfo=timezone.utc)
            except ValueError:
                return None

        return None
