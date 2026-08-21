"""Domain & Application Exception Hierarchy.

Định nghĩa phân cấp lỗi nghiệp vụ tường minh cho RoomBeacon,
tách biệt lỗi hạ tầng (Network, Database, Playwright) khỏi trạng thái nghiệp vụ.
"""


class DomainError(Exception):
    """Lỗi gốc của tầng Domain/Nghiệp vụ RoomBeacon."""


class SourceAccessError(DomainError):
    """Lỗi khi thẩm định hoặc truy cập nguồn dữ liệu."""


class RobotsDeniedError(SourceAccessError):
    """Lỗi khi URL bị từ chối bởi RobotsPolicy theo RFC 9309."""


class FetchError(DomainError):
    """Lỗi trong quá trình thu thập trang web qua HTTP hoặc Browser."""


class ParseError(DomainError):
    """Lỗi khi bóc tách cấu trúc HTML hoặc JSON của nguồn dữ liệu."""


class PersistenceError(DomainError):
    """Lỗi trong quá trình lưu trữ dữ liệu (Bronze filesystem hoặc Database)."""


class DatabaseConnectionError(PersistenceError):
    """Lỗi kết nối cơ sở dữ liệu (MySQL / ClickHouse)."""


class ObservationConflictError(PersistenceError):
    """Lỗi xung đột hoặc toàn vẹn dữ liệu khi ghi nhận bản ghi quan sát."""


class AnalyticsError(DomainError):
    """Lỗi trong tầng phân tích dữ liệu DuckDB."""


class DuckDBAttachError(AnalyticsError):
    """Lỗi khi gắn (attach) database nguồn vào DuckDB analytical engine."""
