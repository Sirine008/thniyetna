"""Equipment agent: proposed actions and their human decision (propose → confirm → execute)

Revision ID: 0008_agent_actions
Revises: 0007_places_index
Create Date: 2026-11-07

Additive. During an agent run the action tools never write to business tables: they only insert a row here
(status 'proposed', with the French summary, what will change and the evidence to check). The equipment supervisor
confirms or ignores it (POST /assistant/agent/actions/{id}/confirm | reject); confirmation runs the existing code
once, as that user, and stores the result. A proposal expires 30 min after `proposed_at`.
"""
from alembic import op

revision = "0008_agent_actions"
down_revision = "0007_places_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS agent_actions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id UUID NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('plan_intervention', 'notify_transport', 'generate_full_sheet',
                                           'propose_validation')),
        arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
        proposal JSONB NOT NULL DEFAULT '{}'::jsonb,
        status TEXT NOT NULL DEFAULT 'proposed'
            CHECK (status IN ('proposed', 'confirmed', 'rejected', 'expired', 'failed')),
        proposed_by TEXT,
        proposed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        decided_by TEXT,
        decided_at TIMESTAMPTZ,
        result JSONB
    );
    CREATE INDEX IF NOT EXISTS idx_agent_actions_run ON agent_actions(run_id);
    CREATE INDEX IF NOT EXISTS idx_agent_actions_status ON agent_actions(status, proposed_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_actions;")
