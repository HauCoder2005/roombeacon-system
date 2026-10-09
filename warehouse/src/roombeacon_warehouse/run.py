"""CLI: build the dimensional model from Parquet and load ClickHouse.

    python -m roombeacon_warehouse.run --dry-run   # build and validate only
    python -m roombeacon_warehouse.run             # build and load
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from .config import load_warehouse_settings
from .loader import run_warehouse_load
from .model import build_warehouse_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--curated-dir", type=Path, default=Path("data/curated_observations"))
    parser.add_argument("--silver-dir", type=Path, default=Path("data/silver"))
    parser.add_argument("--env-file", type=Path, default=None, help="defaults to <project>/.env.local")
    parser.add_argument("--dry-run", action="store_true", help="build the model without connecting")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            with tempfile.TemporaryDirectory(prefix=".warehouse_dry_run.") as staging:
                model = build_warehouse_model(args.curated_dir, args.silver_dir, Path(staging))
                summary = {"snapshot_id": model.snapshot_id, "row_counts": model.row_counts(), "dry_run": True}
        else:
            settings = load_warehouse_settings(args.env_file)
            summary = run_warehouse_load(args.curated_dir, args.silver_dir, settings=settings)
    except Exception as exc:
        print(f"Warehouse load FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
