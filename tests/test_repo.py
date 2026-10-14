from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_foundation_files():
    for path in [
        "docker-compose.yml",
        "backend/alembic.ini",
        "backend/alembic/versions/0001_initial_schema.py",
        "backend/alembic/versions/0002_bootstrap_operational_accounts.py",
        "backend/Dockerfile",
        "frontend/Dockerfile",
        "infra/mlflow/Dockerfile",
        "ml/perception/worker.py",
    ]:
        assert (ROOT / path).exists(), path


def test_runtime_stack_has_no_object_store_or_seed_service():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").lower()
    assert "minio" not in compose
    assert "seed-demo" not in compose
    assert "seed_demo" not in compose
    assert "  migrate:" not in compose


def test_normal_backend_frontend_layout():
    assert (ROOT / "backend").is_dir()
    assert (ROOT / "frontend").is_dir()
    assert not (ROOT / "apps").exists()


def test_json_examples():
    for path in (ROOT / "data/schemas").glob("*.json"):
        json.loads(path.read_text())
