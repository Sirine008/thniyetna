"""initial THNIYETNA schema

Revision ID: 0001_initial
Revises: None
Create Date: 2026-10-07
"""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("""
    CREATE TABLE road_segments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        segment_code TEXT UNIQUE NOT NULL,
        name TEXT,
        road_class TEXT,
        direction TEXT,
        geom geometry(LineString,4326) NOT NULL,
        properties JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX road_segments_geom_gix ON road_segments USING GIST (geom)")

    op.execute("""
    CREATE TABLE app_users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,
        organization TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE vehicles (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        vehicle_code TEXT UNIQUE NOT NULL,
        vehicle_type TEXT NOT NULL,
        owner_org TEXT NOT NULL,
        label TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE inspection_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'active',
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        ended_at TIMESTAMPTZ,
        video_uri TEXT,
        video_storage_key TEXT,
        last_position geometry(Point,4326),
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """)
    op.execute("CREATE INDEX inspection_sessions_pos_gix ON inspection_sessions USING GIST(last_position)")

    op.execute("""
    CREATE TABLE inspection_positions (
        id BIGSERIAL PRIMARY KEY,
        session_id UUID NOT NULL REFERENCES inspection_sessions(id) ON DELETE CASCADE,
        captured_at TIMESTAMPTZ NOT NULL,
        geom geometry(Point,4326) NOT NULL,
        speed_kmh DOUBLE PRECISION,
        heading_deg DOUBLE PRECISION,
        accuracy_m DOUBLE PRECISION,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(session_id, captured_at)
    )
    """)
    op.execute("CREATE INDEX inspection_positions_geom_gix ON inspection_positions USING GIST(geom)")
    op.execute("CREATE INDEX inspection_positions_session_time_idx ON inspection_positions(session_id, captured_at)")

    op.execute("""
    CREATE TABLE road_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        segment_id UUID REFERENCES road_segments(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        source TEXT NOT NULL,
        severity DOUBLE PRECISION CHECK (severity IS NULL OR severity BETWEEN 0 AND 1),
        confidence DOUBLE PRECISION CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
        geom geometry(Point,4326) NOT NULL,
        observed_at TIMESTAMPTZ NOT NULL,
        media_uri TEXT,
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        status TEXT NOT NULL DEFAULT 'observed',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX road_events_geom_gix ON road_events USING GIST (geom)")
    op.execute("CREATE INDEX road_events_segment_time_idx ON road_events (segment_id, observed_at DESC)")
    op.execute("CREATE INDEX road_events_type_time_idx ON road_events (event_type, observed_at DESC)")

    op.execute("""
    CREATE TABLE road_observations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        event_id UUID REFERENCES road_events(id) ON DELETE SET NULL,
        session_id UUID REFERENCES inspection_sessions(id) ON DELETE SET NULL,
        source TEXT NOT NULL,
        defect_type TEXT NOT NULL,
        confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
        severity_proxy DOUBLE PRECISION CHECK (severity_proxy IS NULL OR severity_proxy BETWEEN 0 AND 1),
        geom geometry(Point,4326),
        captured_at TIMESTAMPTZ NOT NULL,
        frame_index INTEGER,
        frame_time_s DOUBLE PRECISION,
        bbox_xyxy JSONB,
        media_uri TEXT,
        model_name TEXT,
        model_version TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX road_observations_geom_gix ON road_observations USING GIST(geom)")
    op.execute("CREATE INDEX road_observations_event_idx ON road_observations(event_id)")
    op.execute("CREATE INDEX road_observations_session_time_idx ON road_observations(session_id, captured_at)")

    op.execute("""
    CREATE TABLE perception_jobs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        job_type TEXT NOT NULL CHECK (job_type IN ('image','video')),
        source TEXT NOT NULL,
        storage_key TEXT NOT NULL,
        media_uri TEXT,
        session_id UUID REFERENCES inspection_sessions(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed')),
        progress DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
        model_name TEXT,
        model_version TEXT,
        options JSONB NOT NULL DEFAULT '{}'::jsonb,
        result JSONB NOT NULL DEFAULT '{}'::jsonb,
        error TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        claimed_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX perception_jobs_status_created_idx ON perception_jobs(status, created_at)")

    op.execute("""
    CREATE TABLE official_routes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        route_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        owner_org TEXT NOT NULL DEFAULT 'ministry_of_transport',
        geom geometry(MultiLineString,4326) NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX official_routes_geom_gix ON official_routes USING GIST (geom)")

    op.execute("""
    CREATE TABLE route_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        route_id UUID NOT NULL REFERENCES official_routes(id) ON DELETE CASCADE,
        vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
        driver_username TEXT,
        valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
        valid_to TIMESTAMPTZ,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX route_assignments_vehicle_idx ON route_assignments(vehicle_id, active)")

    op.execute("""
    CREATE TABLE risk_scores (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        segment_id UUID REFERENCES road_segments(id) ON DELETE CASCADE,
        risk_score DOUBLE PRECISION NOT NULL CHECK (risk_score BETWEEN 0 AND 1),
        risk_category TEXT,
        model_version TEXT,
        features JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX risk_scores_segment_time_idx ON risk_scores (segment_id, created_at DESC)")

    op.execute("""
    CREATE TABLE actor_profiles (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        external_subject TEXT UNIQUE,
        actor_type TEXT NOT NULL,
        attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE complaints (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        actor_ref TEXT,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        geom geometry(Point,4326) NOT NULL,
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX complaints_geom_gix ON complaints USING GIST (geom)")

    op.execute("""
    CREATE TABLE complaint_status_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        complaint_id UUID NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
        old_status TEXT,
        new_status TEXT NOT NULL,
        changed_by TEXT,
        note TEXT,
        changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE weather_observations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        area_code TEXT NOT NULL DEFAULT 'BIZERTE',
        observed_at TIMESTAMPTZ NOT NULL,
        precipitation_mm DOUBLE PRECISION NOT NULL DEFAULT 0,
        precipitation_probability DOUBLE PRECISION,
        wind_kmh DOUBLE PRECISION,
        temperature_c DOUBLE PRECISION,
        weather_code TEXT,
        source TEXT NOT NULL DEFAULT 'external',
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX weather_observations_area_time_idx ON weather_observations(area_code, observed_at DESC)")

    op.execute("""
    CREATE TABLE risk_forecasts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        segment_id UUID NOT NULL REFERENCES road_segments(id) ON DELETE CASCADE,
        horizon_hours INTEGER NOT NULL DEFAULT 6,
        risk_score DOUBLE PRECISION NOT NULL CHECK (risk_score BETWEEN 0 AND 1),
        risk_category TEXT NOT NULL,
        contributing_factors JSONB NOT NULL DEFAULT '[]'::jsonb,
        model_version TEXT NOT NULL DEFAULT 'contextual-v1',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX risk_forecasts_segment_time_idx ON risk_forecasts(segment_id, created_at DESC)")

    op.execute("""
    CREATE TABLE notification_outbox (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        topic TEXT NOT NULL,
        recipient_ref TEXT,
        payload JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        delivered_at TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX notification_outbox_created_idx ON notification_outbox(created_at)")


def downgrade() -> None:
    for table in [
        "notification_outbox", "risk_forecasts", "weather_observations",
        "complaint_status_history", "complaints", "actor_profiles", "risk_scores",
        "route_assignments", "official_routes", "perception_jobs", "road_observations",
        "road_events", "inspection_positions", "inspection_sessions", "vehicles",
        "app_users", "road_segments"
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
