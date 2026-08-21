from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
import time
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

    def __init__(self, groups: list[dict], crawl_delays: dict[str, float] | None = None) -> None:
        self.groups = groups
        self.crawl_delays = crawl_delays or {}

    @classmethod
    def parse_text(cls, text: str) -> "RobotsDocument":
        groups: list[dict] = []
        crawl_delays: dict[str, float] = {}
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
            elif directive == "crawl-delay":
                # Politeness extension (không thuộc RFC 9309 bắt buộc, không can thiệp rule matching)
                try:
                    delay_val = float(value)
                    for ua in current_uas:
                        crawl_delays[ua.lower()] = delay_val
                except ValueError:
                    pass

        if current_uas or current_rules:
            groups.append({"user_agents": current_uas, "rules": current_rules})

        return cls(groups=groups, crawl_delays=crawl_delays)

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
                if ua != "*" and (ua.lower() == product or ua.lower() in product):
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

        # 3. Áp dụng thuật toán Longest Match RFC 9309 (Most specific rule wins, Allow wins ties)
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


@dataclass(frozen=True, slots=True)
class RobotsEvaluationResult:
    """Kết quả thẩm định robots.txt theo tiêu chuẩn RFC 9309."""

    decision: str  # "ALLOWED" | "DENIED" | "UNAVAILABLE" | "UNREACHABLE" | "ERROR"
    robots_url: str
    http_status: int | None = None
    robots_state: str = "OK"  # "OK" | "UNAVAILABLE" | "UNREACHABLE" | "ERROR"
    explicit_denial: bool = False
    decision_source: str = "RFC_9309"
    matched_rule: str = "None"
    matched_ua_group: str = "*"
    rule_type: str = "DEFAULT_ALLOW"
    error_reason: str | None = None

    def __iter__(self):
        """Hỗ trợ unpacking dạng tuple `(decision, robots_url)` cho backward compatibility."""
        return iter((self.decision, self.robots_url))

    def __getitem__(self, index):
        return (self.decision, self.robots_url)[index]


@dataclass
class CachedRobotsEntry:
    """Bản ghi lưu trữ tạm thời robots.txt theo từng domain / origin."""

    document: RobotsDocument | None
    robots_state: str  # "OK" | "UNAVAILABLE" | "UNREACHABLE" | "ERROR"
    http_status: int | None
    final_robots_url: str
    error_reason: str | None
    cached_at: float  # time.time()
    ttl_seconds: float = 3600.0  # 1 hour


class RobotsPolicy:
    """Chính sách kiểm tra và tuân thủ tệp robots.txt của website nguồn theo chuẩn RFC 9309.

    Phân biệt rạch ròi:
    1. ALLOWED: robots.txt hợp lệ và cho phép đường dẫn (hoặc HTTP 4xx -> không có luật cấm).
    2. DENIED: robots.txt hợp lệ và có chỉ thị Disallow cụ thể khớp với đường dẫn.
    3. UNAVAILABLE: robots.txt trả về HTTP 4xx (401, 403, 404, 410, 429) -> không có luật cấm (Explicit Denial: NO).
    4. UNREACHABLE: robots.txt trả về HTTP 5xx hoặc lỗi mạng / timeout / DNS -> crawler bảo thủ dừng lại.
    """

    def __init__(
        self,
        user_agent: str = "RoomBeaconCrawler/0.1",
        cache_ttl_seconds: float = 3600.0,
    ) -> None:
        self.user_agent = user_agent
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, CachedRobotsEntry] = {}
        self._error_details: dict[str, dict] = {}

    def get_product_token(self) -> str:
        """Trích xuất product token danh tính của crawler (ví dụ: 'RoomBeaconCrawler')."""
        return self.user_agent.split("/")[0].strip()

    def get_error_details(self, domain: str) -> dict | None:
        """Lấy chi tiết mã lỗi HTTP và lý do kỹ thuật khi nạp robots.txt."""
        return self._error_details.get(domain.lower())

    def get_robots_url(self, url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme or "https"
        domain = parsed.netloc
        return f"{scheme}://{domain}/robots.txt"

    def evaluate(self, url: str) -> RobotsEvaluationResult:
        """Đánh giá chi tiết robots preflight cho URL mục tiêu theo RFC 9309.

        Returns:
            RobotsEvaluationResult (có thể unpack như tuple `(decision, robots_url)`)
        """
        parsed = urlsplit(url)
        domain = parsed.netloc.lower()
        scheme = parsed.scheme or "https"
        robots_url = f"{scheme}://{domain}/robots.txt"

        if not domain:
            return RobotsEvaluationResult(
                decision="ALLOWED",
                robots_url=robots_url,
                http_status=None,
                robots_state="OK",
                explicit_denial=False,
                decision_source="RFC_9309_EMPTY_DOMAIN",
                matched_rule="None",
                rule_type="DEFAULT_ALLOW",
            )

        target_path = parsed.path or "/"
        target_query = parsed.query
        target_path_query = target_path + (f"?{target_query}" if target_query else "")

        entry = self._get_or_load_document(domain, scheme)
        robots_url = entry.final_robots_url or robots_url

        # 1. Trường hợp UNREACHABLE (HTTP 5xx, Network Timeout, Connection Error, DNS Failure)
        # RFC 9309 2.3.1.3: Server Error / Unreachable -> crawler assume complete disallow
        if entry.robots_state == "UNREACHABLE":
            logger.info("=" * 60)
            logger.info("ROBOTS DECISION")
            logger.info("Host             : %s", domain)
            logger.info("Robots URL       : %s", robots_url)
            logger.info("HTTP Status      : %s", entry.http_status or "<network_error>")
            logger.info("Robots State     : UNREACHABLE")
            logger.info("Explicit Denial  : NO")
            logger.info("Decision Source  : RFC_9309_UNREACHABLE")
            logger.info("Reason           : %s", entry.error_reason)
            logger.info("=" * 60)
            return RobotsEvaluationResult(
                decision="UNREACHABLE",
                robots_url=robots_url,
                http_status=entry.http_status,
                robots_state="UNREACHABLE",
                explicit_denial=False,
                decision_source="RFC_9309_UNREACHABLE",
                matched_rule="None",
                rule_type="CONSERVATIVE_DISALLOW",
                error_reason=entry.error_reason,
            )

        # 2. Trường hợp UNAVAILABLE (HTTP 4xx: 400, 401, 403, 404, 410, 429 hoặc HTML non-text)
        # RFC 9309 2.3.1.2: Client Error -> crawler MUST assume there are NO restrictions
        if entry.robots_state == "UNAVAILABLE" or entry.document is None:
            logger.info("=" * 60)
            logger.info("ROBOTS DECISION")
            logger.info("Host             : %s", domain)
            logger.info("Robots URL       : %s", robots_url)
            logger.info("HTTP Status      : %s", entry.http_status or 404)
            logger.info("Robots State     : UNAVAILABLE")
            logger.info("Explicit Denial  : NO")
            logger.info("Decision Source  : RFC_9309_UNAVAILABLE")
            logger.info("Reason           : %s", entry.error_reason or "Resource unavailable / 4xx error")
            logger.info("=" * 60)
            return RobotsEvaluationResult(
                decision="UNAVAILABLE",
                robots_url=robots_url,
                http_status=entry.http_status,
                robots_state="UNAVAILABLE",
                explicit_denial=False,
                decision_source="RFC_9309_UNAVAILABLE",
                matched_rule="None",
                rule_type="NO_RESTRICTIONS_ASSUMED",
                error_reason=entry.error_reason,
            )

        # 3. Trường hợp 200 OK -> Phân tích cú pháp và áp dụng quy tắc RFC 9309
        decision, matched_ua, matched_rule, rule_type = entry.document.evaluate(
            target_path_query=target_path_query,
            product_token=self.user_agent,
        )

        explicit_denial = decision == "DENIED"

        logger.info("=" * 60)
        logger.info("ROBOTS DECISION")
        logger.info("Host             : %s", domain)
        logger.info("Robots URL       : %s", robots_url)
        logger.info("HTTP Status      : 200")
        logger.info("Robots State     : OK")
        logger.info("Explicit Denial  : %s", "YES" if explicit_denial else "NO")
        logger.info("Decision Source  : RFC_9309_MATCH")
        logger.info("Applicable Group : %s", matched_ua)
        logger.info("Matched Rule     : %s", matched_rule)
        logger.info("Rule Type        : %s", rule_type)
        logger.info("Decision         : %s", decision)
        logger.info("=" * 60)

        return RobotsEvaluationResult(
            decision=decision,
            robots_url=robots_url,
            http_status=200,
            robots_state="OK",
            explicit_denial=explicit_denial,
            decision_source="RFC_9309_MATCH",
            matched_rule=matched_rule,
            matched_ua_group=matched_ua,
            rule_type=rule_type,
            error_reason=None,
        )

    def is_allowed(self, url: str) -> bool:
        """Kiểm tra xem User-Agent hiện tại có được phép crawl URL này không."""
        res = self.evaluate(url)
        if isinstance(res, tuple) and not hasattr(res, "decision"):
            decision = res[0]
            robots_url = res[1] if len(res) > 1 else ""
        else:
            decision = getattr(res, "decision", "ALLOWED")
            robots_url = getattr(res, "robots_url", "")
        if decision in ("DENIED", "UNREACHABLE"):
            logger.warning("URL %s bị từ chối bởi robots policy (%s, decision=%s)", url, robots_url, decision)
            return False
        return True

    def _get_or_load_document(self, domain: str, scheme: str) -> CachedRobotsEntry:
        """Lấy tài liệu robots từ cache hoặc fetch với User-Agent chuẩn tuân thủ RFC 9309."""
        now_ts = time.time()
        cached = self._cache.get(domain)
        if cached and (now_ts - cached.cached_at < cached.ttl_seconds):
            return cached

        robots_url = f"{scheme or 'https'}://{domain}/robots.txt"
        req = urllib.request.Request(
            robots_url,
            headers={"User-Agent": self.user_agent},
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = getattr(resp, "status", 200)
                final_url = resp.geturl() if hasattr(resp, "geturl") else robots_url
                content_type = str(resp.headers.get("Content-Type", "")).lower()

                # Kiểm tra Content-Type an toàn: Nếu nhận HTML challenge hoặc trang lỗi không phải text
                if "html" in content_type and "text/plain" not in content_type:
                    logger.warning(
                        "Robots.txt trả về HTML thay vì text/plain từ %s (Status: %s)",
                        robots_url,
                        status_code,
                    )
                    self._error_details[domain] = {
                        "status_code": status_code,
                        "reason": "HTML response instead of text/plain",
                        "failure_type": "ROBOTS_UNAVAILABLE",
                    }
                    entry = CachedRobotsEntry(
                        document=None,
                        robots_state="UNAVAILABLE",
                        http_status=status_code,
                        final_robots_url=final_url,
                        error_reason="HTML response instead of text/plain",
                        cached_at=now_ts,
                        ttl_seconds=self.cache_ttl_seconds,
                    )
                    self._cache[domain] = entry
                    return entry

                raw_bytes = resp.read()
                text = raw_bytes.decode("utf-8", errors="surrogateescape")
                doc = RobotsDocument.parse_text(text)
                entry = CachedRobotsEntry(
                    document=doc,
                    robots_state="OK",
                    http_status=status_code,
                    final_robots_url=final_url,
                    error_reason=None,
                    cached_at=now_ts,
                    ttl_seconds=self.cache_ttl_seconds,
                )
                self._cache[domain] = entry
                logger.info("Đã nạp và phân tích thành công robots.txt từ %s", robots_url)
                return entry

        except urllib.error.HTTPError as exc:
            # Phân định rõ 4xx (Client Error) vs 5xx (Server Error)
            if 400 <= exc.code < 500:
                logger.info(
                    "HTTP %d (Client Error) khi nạp robots.txt từ %s. RFC 9309: Coi như không có hạn chế robots.",
                    exc.code,
                    robots_url,
                )
                self._error_details[domain] = {
                    "status_code": exc.code,
                    "reason": str(exc.reason),
                    "failure_type": "ROBOTS_UNAVAILABLE",
                }
                entry = CachedRobotsEntry(
                    document=None,
                    robots_state="UNAVAILABLE",
                    http_status=exc.code,
                    final_robots_url=robots_url,
                    error_reason=f"HTTP {exc.code} Client Error ({exc.reason})",
                    cached_at=now_ts,
                    ttl_seconds=self.cache_ttl_seconds,
                )
                self._cache[domain] = entry
                return entry
            else:
                # 5xx Server Error
                logger.warning(
                    "HTTP %d (Server Error) khi nạp robots.txt từ %s: %s. RFC 9309: Tạm dừng và coi như từ chối hoàn toàn.",
                    exc.code,
                    robots_url,
                    exc.reason,
                )
                self._error_details[domain] = {
                    "status_code": exc.code,
                    "reason": str(exc.reason),
                    "failure_type": "ROBOTS_UNREACHABLE",
                }
                entry = CachedRobotsEntry(
                    document=None,
                    robots_state="UNREACHABLE",
                    http_status=exc.code,
                    final_robots_url=robots_url,
                    error_reason=f"HTTP {exc.code} Server Error ({exc.reason})",
                    cached_at=now_ts,
                    ttl_seconds=self.cache_ttl_seconds,
                )
                self._cache[domain] = entry
                return entry

        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            # Lỗi mạng, timeout, DNS resolution failure
            logger.warning(
                "Lỗi kết nối / timeout khi nạp robots.txt từ %s: %s",
                robots_url,
                exc,
            )
            self._error_details[domain] = {
                "status_code": None,
                "reason": str(exc),
                "failure_type": "ROBOTS_UNREACHABLE",
            }
            entry = CachedRobotsEntry(
                document=None,
                robots_state="UNREACHABLE",
                http_status=None,
                final_robots_url=robots_url,
                error_reason=f"Network/Connection error: {exc}",
                cached_at=now_ts,
                ttl_seconds=self.cache_ttl_seconds,
            )
            self._cache[domain] = entry
            return entry

        except Exception as exc:
            logger.warning(
                "Lỗi không xác định khi nạp robots.txt từ %s: %s",
                robots_url,
                exc,
            )
            self._error_details[domain] = {
                "status_code": None,
                "reason": str(exc),
                "failure_type": "ROBOTS_UNREACHABLE",
            }
            entry = CachedRobotsEntry(
                document=None,
                robots_state="UNREACHABLE",
                http_status=None,
                final_robots_url=robots_url,
                error_reason=f"Unexpected error: {exc}",
                cached_at=now_ts,
                ttl_seconds=self.cache_ttl_seconds,
            )
            self._cache[domain] = entry
            return entry
