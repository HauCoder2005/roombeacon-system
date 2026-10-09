"""Static contracts for the API image and its disabled-by-default Compose service."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
DOCKERFILE = ROOT / "api/Dockerfile"
PYPROJECT = ROOT / "api/pyproject.toml"


def _service_block(name: str) -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|^[a-z]|\Z)", text, re.S | re.M)
    assert match, name
    return match.group(1)


def test_api_service_is_profiled_local_only_and_hardened():
    block = _service_block("api")

    assert re.search(r"profiles:\n\s+- api\n", block)
    assert '"127.0.0.1:8000:8000"' in block
    assert "read_only: true" in block
    assert '"no-new-privileges:true"' in block
    assert re.search(r"cap_drop:\n\s+- ALL", block)
    assert re.search(r'user: "(\d+):(\d+)"', block) and 'user: "0' not in block
    assert "mem_limit:" in block and "cpus:" in block
    assert "healthcheck:" in block
    assert "mysql" not in block.lower()


def test_api_image_is_pinned_and_runs_as_non_root():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert re.search(r"^FROM python:\d+\.\d+\.\d+-slim-\w+", dockerfile, re.M)
    assert re.search(r"^USER \d+:\d+", dockerfile, re.M)
    assert "--workers" in dockerfile and "--proxy-headers" not in dockerfile


def test_api_dependencies_are_pinned():
    text = PYPROJECT.read_text(encoding="utf-8")
    dependencies = re.search(r"dependencies = \[(.*?)\]", text, re.S).group(1)

    for line in re.findall(r'"([^"]+)"', dependencies):
        assert "==" in line, line
