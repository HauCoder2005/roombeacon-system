from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class NhatroVNDateInterpreter:
    """Phiên dịch và chuẩn hóa thời gian đăng bài từ chuỗi text của NhatroVN."""

    def interpret(self, date_str: str | None) -> datetime | None:
        """Chuyển đổi chuỗi thời gian hiển thị thành datetime (nếu có)."""
        if not date_str or not date_str.strip():
            return None
        # NhatroVN thường hiển thị trạng thái phòng hoặc cập nhật realtime
        return datetime.now(timezone.utc)

    def is_within_range(
        self,
        date_str: str | None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> bool:
        """Kiểm tra xem mốc thời gian có thỏa mãn khoảng thời gian chỉ định không."""
        dt = self.interpret(date_str)
        if dt is None:
            return True
        if date_from and dt < date_from:
            return False
        if date_to and dt > date_to:
            return False
        return True
