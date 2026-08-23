import argparse
import logging
import sys
from analytics.duckdb.connection import DuckDBConnectionFactory
from analytics.duckdb.bootstrap import bootstrap_analytics

logger = logging.getLogger("DUCKDB_UI")

AVAILABLE_VIEWS = [
    "v_observations",
    "v_latest_posts",
    "v_price_history",
    "v_content_changes",
    "v_source_activity",
    "v_listing_lifetime",
    "v_location_summary",
    "v_data_quality",
]


def launch_ui(view_name: str | None = None, limit: int = 20) -> None:
    """Khởi chạy giao diện dòng lệnh tra cứu phân tích dữ liệu DuckDB."""
    bootstrap_analytics()
    conn = DuckDBConnectionFactory.get_connection()

    if view_name is None:
        print("=" * 70)
        print("ROOMBEACON DUCKDB ANALYTICS CLI")
        print("=" * 70)
        print("Available analytical views:")
        for idx, v in enumerate(AVAILABLE_VIEWS, 1):
            print(f"  [{idx}] {v}")
        print("-" * 70)
        print("\n--- [Overview: v_source_activity] ---")
        df_act = conn.execute("SELECT * FROM v_source_activity ORDER BY date DESC, platform LIMIT 10").df()
        print(df_act.to_string(index=False))

        print("\n--- [Overview: v_data_quality] ---")
        df_dq = conn.execute("SELECT * FROM v_data_quality").df()
        print(df_dq.to_string(index=False))
        return

    # Chuẩn hóa tên view
    v_norm = view_name if view_name.startswith("v_") else f"v_{view_name}"
    if v_norm not in AVAILABLE_VIEWS:
        print(f"Error: Unknown view '{view_name}'. Available: {AVAILABLE_VIEWS}")
        return

    print(f"\n--- [ANALYTICS: {v_norm} (LIMIT {limit})] ---")
    df = conn.execute(f"SELECT * FROM {v_norm} LIMIT {limit}").df()
    print(df.to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RoomBeacon DuckDB Analytics CLI")
    parser.add_argument("--view", "-v", type=str, default=None, help="Tên analytical view (ví dụ: v_source_activity)")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Số dòng giới hạn (mặc định: 20)")
    parser.add_argument("--list", action="store_true", help="Liệt kê danh sách analytical views")

    args = parser.parse_args()
    if args.list:
        print("Available analytical views:")
        for v in AVAILABLE_VIEWS:
            print(f" - {v}")
    else:
        launch_ui(view_name=args.view, limit=args.limit)
