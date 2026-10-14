"""M2 risk model: accident history, admin areas, governorate forecasts, richer risk_scores

Revision ID: 0003_m2_risk_model
Revises: 0002_bootstrap_accounts
Create Date: 2026-10-11

Additive only: existing columns keep their meaning, so M3 (routing) and M4
(platform) keep working unchanged. `risk_scores.risk_category` keeps the 3
legacy values (low/medium/high); the 4-level contract value goes to the new
`risk_level` column (critical is stored as risk_category='high').
"""
from alembic import op

revision = "0003_m2_risk_model"
down_revision = "0002_bootstrap_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS accident_records (
        accident_id TEXT PRIMARY KEY,
        occurred_on DATE NOT NULL,
        hour SMALLINT,
        gov_code TEXT NOT NULL,
        delegation TEXT,
        place TEXT,
        road_class TEXT,
        cause_group TEXT,
        killed INTEGER NOT NULL DEFAULT 0,
        injured INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'open-data',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS accident_records_gov_date_idx ON accident_records(gov_code, occurred_on)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS admin_areas (
        code TEXT PRIMARY KEY,
        name TEXT,
        level TEXT NOT NULL DEFAULT 'governorate',
        geom geometry(MultiPolygon, 4326) NOT NULL
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS admin_areas_geom_gix ON admin_areas USING GIST (geom)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS governorate_risk_forecasts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        gov_code TEXT NOT NULL,
        forecast_date DATE NOT NULL,
        p_accident DOUBLE PRECISION NOT NULL CHECK (p_accident BETWEEN 0 AND 1),
        alert BOOLEAN NOT NULL DEFAULT FALSE,
        expected_accidents DOUBLE PRECISION NOT NULL DEFAULT 0,
        p_fatal_accident DOUBLE PRECISION,
        top_factors JSONB NOT NULL DEFAULT '[]'::jsonb,
        history_staleness_days INTEGER NOT NULL DEFAULT 0,
        model_version TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (gov_code, forecast_date, model_version)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS gov_risk_forecasts_date_idx ON governorate_risk_forecasts(forecast_date, gov_code)")

    for col, typ in [
        ("risk_level", "TEXT"), ("horizon_days", "INTEGER"), ("components", "JSONB"),
        ("top_factors", "JSONB"), ("valid_until", "TIMESTAMPTZ"), ("mlflow_run_id", "TEXT"),
        ("maintenance_priority", "TEXT"), ("predicted_condition", "TEXT"),
    ]:
        op.execute(f"ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS {col} {typ}")


def downgrade() -> None:
    for col in ("risk_level", "horizon_days", "components", "top_factors", "valid_until",
                "mlflow_run_id", "maintenance_priority", "predicted_condition"):
        op.execute(f"ALTER TABLE risk_scores DROP COLUMN IF EXISTS {col}")
    for t in ("governorate_risk_forecasts", "admin_areas", "accident_records"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
