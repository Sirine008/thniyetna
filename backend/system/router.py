from fastapi import APIRouter
from sqlalchemy import text

from shared.config import MEDIA_ROOT
from shared.db import engine
from shared.storage import ensure_media_dirs

router = APIRouter(prefix="/system", tags=["M5 system"])


@router.get("/ready")
def ready():
    checks = {"database": False, "postgis": False, "media_storage": False}
    details = {}
    try:
        with engine.connect() as connection:
            checks["database"] = connection.execute(text("SELECT 1")).scalar() == 1
            version = connection.execute(text("SELECT PostGIS_Version()" )).scalar()
            checks["postgis"] = bool(version)
            details["postgis_version"] = version
    except Exception as exc:
        details["database_error"] = str(exc)

    try:
        ensure_media_dirs()
        probe = MEDIA_ROOT / ".ready"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks["media_storage"] = True
        details["media_root"] = str(MEDIA_ROOT)
    except Exception as exc:
        details["media_storage_error"] = str(exc)

    return {
        "status": "ready" if all(checks.values()) else "degraded",
        "checks": checks,
        "details": details,
    }


@router.get("/storage")
def storage():
    ensure_media_dirs()
    folders = sorted(p.name for p in MEDIA_ROOT.iterdir() if p.is_dir())
    return {"backend": "local-volume", "root": str(MEDIA_ROOT), "folders": folders}


@router.get("/database")
def database_info():
    with engine.connect() as connection:
        postgis_version = connection.execute(text("SELECT PostGIS_Version()" )).scalar()
        tables = connection.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)).scalars().all()
        segment_count = connection.execute(text("SELECT count(*) FROM road_segments")).scalar()
        event_count = connection.execute(text("SELECT count(*) FROM road_events")).scalar()
        route_count = connection.execute(text("SELECT count(*) FROM official_routes")).scalar()

    return {
        "postgis_version": postgis_version,
        "tables": list(tables),
        "counts": {
            "road_segments": segment_count,
            "road_events": event_count,
            "official_routes": route_count,
        },
    }


@router.get("/spatial")
def spatial_snapshot():
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT segment_code, name, road_class,
                   ST_AsGeoJSON(geom)::json AS geometry,
                   ST_Length(geom::geography)::int AS length_m
            FROM road_segments
            ORDER BY segment_code
            LIMIT 10
        """)).mappings().all()
    return {"count": len(rows), "segments": [dict(row) for row in rows]}
