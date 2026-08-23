import ipaddress
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
}


class URLValidator:
    """Generic URL Validator kiểm tra tính hợp lệ và an toàn vận hành (SSRF, scheme) của URL đầu vào.

    Validator KHÔNG chứa allowlist hay phụ thuộc vào bất kỳ Source Adapter cụ thể nào.
    Việc kiểm tra domain có được hỗ trợ hay không do SourceRegistry / SourceResolver đảm nhiệm.
    """

    @classmethod
    def validate(cls, url: str | None) -> tuple[bool, str | None]:
        """Kiểm tra tính an toàn kỹ thuật của URL:

        - URL không rỗng.
        - Cú pháp URL hợp lệ.
        - Scheme bắt buộc phải là http hoặc https (chặn file://, ftp://, gopher://, v.v.).
        - Chặn SSRF (localhost, 127.0.0.1, 0.0.0.0, private IP ranges, link-local, cloud metadata).

        Returns:
            (is_valid, error_reason)
        """
        if not url or not url.strip():
            return False, "URL không được để trống."

        cleaned_url = url.strip()

        try:
            parsed = urlparse(cleaned_url)
        except Exception as exc:
            return False, f"Cú pháp URL không hợp lệ: {exc}"

        # 1. Scheme check
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return (
                False,
                f"Protocol '{parsed.scheme}' không được hỗ trợ (chỉ chấp nhận http/https).",
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "URL không chứa hostname hợp lệ."

        # 2. SSRF / Blocked Hostnames check
        if hostname in _BLOCKED_HOSTNAMES:
            return (
                False,
                f"Hostname '{hostname}' bị từ chối vì lý do an toàn bảo mật (chặn internal/local network).",
            )

        try:
            ip = ipaddress.ip_address(hostname)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return (
                    False,
                    f"IP address '{hostname}' là địa chỉ private/internal, bị từ chối vì lý do bảo mật.",
                )
        except ValueError:
            # Hostname là domain name hợp lệ, không phải IP literal
            pass

        return True, None
