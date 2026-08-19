from datetime import datetime, timedelta, timezone
import re


class NhatotDateInterpreter:
    """Phiên dịch chuỗi thời gian đăng tin thô thành datetime tạm phục vụ điều khiển phân trang."""

    @staticmethod
    def interpret(
        posted_at_raw: str | None,
        reference_now: datetime | None = None,
    ) -> datetime | None:
        """Chuyển đổi chuỗi thời gian hiển thị thành datetime (UTC) để DateCutoffPolicy đánh giá."""
        if not posted_at_raw:
            return None

        if reference_now is None:
            reference_now = datetime.now(timezone.utc)

        text = posted_at_raw.strip().lower()

        # 1. "vừa xong", "hôm nay"
        if "vừa xong" in text or "hôm nay" in text:
            return reference_now

        # 2. "hôm qua"
        if "hôm qua" in text:
            return reference_now - timedelta(days=1)

        # 3. "\d+ phút trước"
        m_min = re.search(r"(\d+)\s*phút\s*trước", text)
        if m_min:
            return reference_now - timedelta(minutes=int(m_min.group(1)))

        # 4. "\d+ giờ trước"
        m_hour = re.search(r"(\d+)\s*giờ\s*trước", text)
        if m_hour:
            return reference_now - timedelta(hours=int(m_hour.group(1)))

        # 5. "\d+ ngày trước"
        m_day = re.search(r"(\d+)\s*ngày\s*trước", text)
        if m_day:
            return reference_now - timedelta(days=int(m_day.group(1)))

        # 6. "\d+ tháng trước"
        m_month = re.search(r"(\d+)\s*tháng\s*trước", text)
        if m_month:
            return reference_now - timedelta(days=int(m_month.group(1)) * 30)

        # 7. Định dạng ngày cụ thể: DD/MM/YYYY hoặc YYYY-MM-DD
        m_date = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text)
        if m_date:
            try:
                day, month, year = int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))
                return datetime(year, month, day, tzinfo=timezone.utc)
            except Exception:
                pass

        return None
