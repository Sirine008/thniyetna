from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backend_files_exist():
    for path in [
        "backend/auth/router.py",
        "backend/perception/router.py",
        "backend/realtime/router.py",
        "backend/media/router.py",
        "backend/routing/router.py",
        "docs/architecture-v2.md",
    ]:
        assert (ROOT / path).exists(), path


def test_main_mounts_routers():
    source = (ROOT / "backend/main.py").read_text()
    for prefix in ["/auth", "/perception", "/prediction", "/routing", "/platform", "/realtime", "/media"]:
        assert prefix in source


def test_routing_has_real_next_best_without_synthetic_scenario():
    router = (ROOT / "backend/routing/router.py").read_text().lower()
    schemas = (ROOT / "backend/routing/schemas.py").read_text().lower()
    assert "safer_pair" in router
    assert "_detour_routes" in router
    assert "demo_scenario" not in router
    assert "synthetic_potholes" not in router
    assert "demo_scenario" not in schemas


def test_frontend_has_no_hardcoded_auto_login():
    api = (ROOT / "frontend/src/lib/api.js").read_text().lower()
    assert "demo123" not in api
    assert "citizen.demo" not in api
    assert "/auth/login" in api
