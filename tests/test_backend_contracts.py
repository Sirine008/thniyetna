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


def test_sql_parameters_are_typed_where_postgres_cannot_infer_them():
    """psycopg 3 sends text/None parameters untyped; PostgreSQL then cannot infer them
    inside jsonb_build_object(...) or in a bare `:param IS NULL` (500 on every write)."""
    import re
    for path in [*ROOT.glob("backend/**/*.py"), *ROOT.glob("ml/perception/*.py")]:
        source = path.read_text(encoding="utf-8")
        for call in re.findall(r"jsonb_build_object\((?:[^()]|\([^()]*\))*\)", source):
            bare = re.findall(r"(?<!CAST\():[a-z_]+\b", call)
            if path.name == "router.py" and "prediction" in path.parts:
                continue  # numeric parameters only: psycopg sends them typed
            assert not bare, f"{path.relative_to(ROOT)}: untyped {bare} in {call}"
        assert not re.search(r"\(:[a-z_]+ IS NULL", source), f"{path.relative_to(ROOT)}: untyped ':param IS NULL'"


def test_sql_case_when_parameter_is_null_is_typed():
    """`CASE WHEN :lat IS NULL` fails (AmbiguousParameter) when the value is None."""
    import re
    for path in [*ROOT.glob("backend/**/*.py"), *ROOT.glob("ml/perception/*.py")]:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"WHEN :[a-z_]+ IS (NOT )?NULL", source), f"{path.relative_to(ROOT)}: untyped 'WHEN :param IS NULL'"


def test_realtime_publish_serialises_dates():
    source = (ROOT / "backend/shared/realtime.py").read_text()
    assert "json.dumps(payload, default=str)" in source
