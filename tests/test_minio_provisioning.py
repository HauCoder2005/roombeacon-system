"""Verify least-privilege MinIO provisioning without runtime credentials."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "infrastructure/minio/policies/roombeacon-assets-writer.json"
BOOTSTRAP_PATH = ROOT / "infrastructure/minio/bootstrap.sh"
COMPOSE_PATH = ROOT / "docker-compose.yml"


def test_asset_policy_is_scoped_to_runtime_operations():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    statements = policy["Statement"]
    assert len(statements) == 2
    listing, objects = statements
    assert listing == {
        "Effect": "Allow", "Action": ["s3:ListBucket"],
        "Resource": ["arn:aws:s3:::roombeacon-assets"],
    }
    assert objects["Effect"] == "Allow"
    assert set(objects["Action"]) == {"s3:GetObject", "s3:PutObject"}
    assert set(objects["Resource"]) == {
        "arn:aws:s3:::roombeacon-assets/*", "arn:aws:s3:::roombeacon-raw/*",
    }


def test_asset_policy_grants_no_admin_or_delete_actions():
    text = POLICY_PATH.read_text(encoding="utf-8")
    for forbidden in ("s3:*", "DeleteObject", "CreateBucket", "arn:aws:s3:::*"):
        assert forbidden not in text


def test_bootstrap_provisions_existing_runtime_identity_without_printing_secrets():
    script = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    assert "mc admin user info" in script
    assert "mc admin user add" in script
    assert "mc admin policy create" in script
    assert "mc admin policy attach" in script
    assert "roombeacon-assets-writer.json" in script
    assert "echo \"${MINIO_CRAWLER" not in script
    assert "set -x" not in script


def test_compose_mounts_source_controlled_bootstrap_and_passes_existing_variables():
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    assert '"./infrastructure/minio:/bootstrap:ro"' in compose
    assert '["/bin/sh", "/bootstrap/bootstrap.sh"]' in compose
    assert 'MINIO_CRAWLER_ACCESS_KEY: "${MINIO_CRAWLER_ACCESS_KEY}"' in compose
    assert 'MINIO_CRAWLER_SECRET_KEY: "${MINIO_CRAWLER_SECRET_KEY}"' in compose
