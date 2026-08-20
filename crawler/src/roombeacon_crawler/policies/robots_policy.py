from dataclasses import dataclass
import logging
import re
import urllib.error
from urllib.parse import urlparse, urlsplit
import urllib.request

logger = logging.getLogger(__name__)


def _compile_pattern(pattern: str) -> tuple[re.Pattern, int]:
    """Chuyển đổi pattern robots.txt (hỗ trợ wildcard '*' và '$') sang regex RFC 9309."""
    length = len(pattern)
    res = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            res += ".*"
        elif c == "$" and i == len(pattern) - 1:
            res += "$"
        elif c in r".^$*+?{}[]()|\/":
            res += "\\" + c
        else:
            res += c
        i += 1
    return re.compile("^" + res), length


@dataclass(frozen=True, slots=True)
class RobotsRule:
    """Đại diện cho một dòng chỉ thị Allow hoặc Disallow."""

    pattern: str
    allow: bool
    regex: re.Pattern
    length: int

    @classmethod
    def create(cls, pattern: str, allow: bool) -> "RobotsRule":
        pattern = pattern.strip()
        if not pattern:
            # Giá trị rỗng trong Disallow: nghĩa là Cho phép tất cả (Allow all)
            return cls(pattern="", allow=True, regex=re.compile(r"^.*"), length=0)
        regex, length = _compile_pattern(pattern)
        return cls(pattern=pattern, allow=allow, regex=regex, length=length)

    def matches(self, target: str) -> bool:
        if not self.pattern:
            return True
        return bool(self.regex.search(target))


class RobotsDocument:
    """Tài liệu robots.txt đã được phân tích cú pháp theo tiêu chuẩn RFC 9309."""

    def __init__(self, groups: list[dict]):
        self.groups = groups

    @classmethod
    def parse_text(cls, text: str) -> "RobotsDocument":
        groups: list[dict] = []
        current_uas: list[str] = []
        current_rules: list[RobotsRule] = []

        for line in text.splitlines():
            # Loại bỏ comment
            i = line.find("#")
            if i >= 0:
                line = line[:i]
            line = line.strip()
            if not line:
                continue

            parts = line.split(":", 1)
            if len(parts) != 2:
                continue

            directive = parts[0].strip().lower()
            value = parts[1].strip()

            if directive == "user-agent":
                if current_rules:
                    # Gặp user-agent mới sau các rules -> lưu nhóm trước đó
                    groups.append({"user_agents": current_uas, "rules": current_rules})
                    current_uas = []
                    current_rules = []
                if value:
                    current_uas.append(value)
            elif directive == "allow":
                if current_uas:
                    current_rules.append(RobotsRule.create(value, allow=True))
            elif directive == "disallow":
                if current_uas:
                    current_rules.append(RobotsRule.create(value, allow=False))

        if current_uas or current_rules:
            groups.append({"user_agents": current_uas, "rules": current_rules})

        return cls(groups)

    def evaluate(self, target_path_query: str, product_token: str) -> tuple[str, str, str, str]:
        """Đánh giá đường dẫn mục tiêu dựa trên nhóm User-Agent phù hợp nhất và luật longest match.

        Returns:
            (decision, matched_ua_group, matched_rule_str, rule_type)
        """
        product = product_token.split("/")[0].strip().lower()
        matched_group = None
        matched_ua_name = "*"

        # 1. Tìm nhóm user-agent khớp cụ thể theo tên product token
        for g in self.groups:
            for ua in g["user_agents"]:
                if ua != "*" and ua.lower() in product:
                    matched_group = g
                    matched_ua_name = ua
                    break
            if matched_group:
                break

        # 2. Nếu không có nhóm riêng, fallback về nhóm '*'
        if not matched_group:
            for g in self.groups:
                if "*" in g["user_agents"]:
                    matched_group = g
                    matched_ua_name = "*"
                    break

        if not matched_group or not matched_group["rules"]:
            return "ALLOWED", matched_ua_name, "None", "DEFAULT_ALLOW"

        # 3. Áp dụng thuật toán Longest Match RFC 9309
        best_rule = None
        for rule in matched_group["rules"]:
            if rule.matches(target_path_query):
                if best_rule is None:
                    best_rule = rule
                else:
                    if rule.length > best_rule.length:
                        best_rule = rule
                    elif rule.length == best_rule.length and rule.allow and not best_rule.allow:
                        best_rule = rule

        if best_rule is None:
            return "ALLOWED", matched_ua_name, "None", "DEFAULT_ALLOW"

        decision = "ALLOWED" if best_rule.allow else "DENIED"
        rule_type = "ALLOW" if best_rule.allow else "DISALLOW"
        matched_rule_str = f"{'Allow' if best_rule.allow else 'Disallow'}: {best_rule.pattern}"
        return decision, matched_ua_name, matched_rule_str, rule_type


class RobotsPolicy:
    """Chính sách kiểm tra và tuân thủ tệp robots.txt của website nguồn tuân thủ RFC 9309."""

    def __init__(self, user_agent: str = "RoomBeaconCrawler/0.1") -> None:
        self.user_agent = user_agent
        self._cache: dict[str, tuple[RobotsDocument | None, str]] = {}

    def get_robots_url(self, url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme or "https"
        domain = parsed.netloc
        return f"{scheme}://{domain}/robots.txt"

    def evaluate(self, url: str) -> tuple[str, str]:
        """Đánh giá chi tiết robots preflight cho URL mục tiêu:

        Returns:
            (decision, robots_url)
            decision: "ALLOWED" | "DENIED" | "UNAVAILABLE" | "ERROR"
        """
        parsed = urlsplit(url)
        domain = parsed.netloc
        scheme = parsed.scheme or "https"
        robots_url = f"{scheme}://{domain}/robots.txt"

        if not domain:
            return "ALLOWED", robots_url

        target_path = parsed.path or "/"
        target_query = parsed.query
        target_path_query = target_path + (f"?{target_query}" if target_query else "")

        document, status = self._get_or_load_document(domain, scheme)

        if status == "ERROR":
            return "ERROR", robots_url
        if status == "UNAVAILABLE" or document is None:
            # 404/410 hoặc không có robots.txt -> Cho phép an toàn
            return "ALLOWED", robots_url

        decision, matched_ua, matched_rule, rule_type = document.evaluate(
            target_path_query=target_path_query,
            product_token=self.user_agent,
        )

        logger.info("=" * 60)
        logger.info("ROBOTS DECISION")
        logger.info("Host               : %s", domain)
        logger.info("Robots URL         : %s", robots_url)
        logger.info("Target path        : %s", target_path)
        logger.info("Target query       : %s", target_query or "<none>")
        logger.info("Crawler product    : %s", self.user_agent)
        logger.info("Applicable UA group: %s", matched_ua)
        logger.info("Matched rule       : %s", matched_rule)
        logger.info("Rule type          : %s", rule_type)
        logger.info("Decision           : %s", decision)
        logger.info("=" * 60)

        return decision, robots_url

    def is_allowed(self, url: str) -> bool:
        """Kiểm tra xem User-Agent hiện tại có được phép crawl URL này không."""
        decision, robots_url = self.evaluate(url)
        if decision == "DENIED":
            logger.warning("URL %s bị cấm bởi robots.txt (%s)", url, robots_url)
            return False
        return True

    def _get_or_load_document(
        self, domain: str, scheme: str
    ) -> tuple[RobotsDocument | None, str]:
        """Lấy tài liệu robots từ cache hoặc fetch với User-Agent chuẩn."""
        if domain in self._cache:
            return self._cache[domain]

        robots_url = f"{scheme or 'https'}://{domain}/robots.txt"
        req = urllib.request.Request(
            robots_url,
            headers={"User-Agent": self.user_agent},
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = getattr(resp, "status", 200)
                content_type = str(resp.headers.get("Content-Type", "")).lower()

                # Kiểm tra Content-Type an toàn: Nếu nhận HTML challenge hoặc trang lỗi không phải text
                if "html" in content_type and "text/plain" not in content_type:
                    logger.warning(
                        "Robots.txt trả về HTML thay vì text/plain từ %s (Status: %s)",
                        robots_url,
                        status_code,
                    )
                    self._cache[domain] = (None, "UNAVAILABLE")
                    return None, "UNAVAILABLE"

                raw_bytes = resp.read()
                text = raw_bytes.decode("utf-8", errors="surrogateescape")
                doc = RobotsDocument.parse_text(text)
                self._cache[domain] = (doc, "OK")
                logger.info("Đã nạp và phân tích thành công robots.txt từ %s", robots_url)
                return doc, "OK"

        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                logger.info("Không tìm thấy robots.txt (HTTP %s) tại %s. Mặc định Allow all.", exc.code, robots_url)
                self._cache[domain] = (None, "UNAVAILABLE")
                return None, "UNAVAILABLE"
            logger.warning(
                "HTTP %s khi nạp robots.txt từ %s: %s",
                exc.code,
                robots_url,
                exc.reason,
            )
            # 401, 403, 429, 5xx KHÔNG được phân loại là explicit DENIED mà là ERROR/UNAVAILABLE
            self._cache[domain] = (None, "ERROR")
            return None, "ERROR"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            logger.warning(
                "Lỗi kết nối khi nạp robots.txt từ %s: %s",
                robots_url,
                exc,
            )
            self._cache[domain] = (None, "ERROR")
            return None, "ERROR"
        except Exception as exc:
            logger.warning(
                "Lỗi không xác định khi nạp robots.txt từ %s: %s",
                robots_url,
                exc,
            )
            self._cache[domain] = (None, "ERROR")
            return None, "ERROR"
