import argparse
import json
import sys

from roombeacon_crawler.services.source_qualifier import SourceQualifier


def build_parser() -> argparse.ArgumentParser:
    """Xây dựng ArgumentParser cho công cụ thẩm định nguồn."""
    parser = argparse.ArgumentParser(
        prog="qualify_source",
        description="Thẩm định độ phù hợp và chính sách robots.txt của một website nguồn ứng viên trước khi viết Adapter.",
    )
    parser.add_argument(
        "url",
        type=str,
        help="Candidate target URL cần thẩm định (ví dụ: https://example.com/rentals)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Xuất kết quả dưới định dạng JSON",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default=None,
        help="Tùy biến User-Agent khi kiểm tra robots.txt (mặc định lấy từ cấu hình crawler)",
    )
    return parser


def main() -> int:
    """CLI Entry point cho công cụ thẩm định nguồn."""
    parser = build_parser()
    args = parser.parse_args()

    qualifier = SourceQualifier()
    result = qualifier.qualify(url=args.url, user_agent=args.user_agent)

    if args.json_output:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.format_human_readable())

    return 0


if __name__ == "__main__":
    sys.exit(main())
