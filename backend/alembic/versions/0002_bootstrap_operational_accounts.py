"""bootstrap operational accounts

Revision ID: 0002_bootstrap_accounts
Revises: 0001_initial
Create Date: 2026-10-08

These are minimum local operational identities, not demo domain data. The
password is read from BOOTSTRAP_PASSWORD when this migration is first applied.
Citizens create their own accounts through POST /auth/register.
"""
import os

from alembic import op
from sqlalchemy import text

revision = "0002_bootstrap_accounts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


ACCOUNTS = (
    ("driver.srtb", "SRTB Driver", "bus_driver", "SRTB"),
    ("equipment.supervisor", "Equipment Supervisor", "equipment_supervisor", "Ministry of Equipment"),
    ("transport.supervisor", "Transport Supervisor", "transport_supervisor", "Ministry of Transport"),
    ("inspection.vehicle", "Inspection Vehicle", "inspection_vehicle", "Ministry of Equipment"),
)


def upgrade() -> None:
    password = os.getenv("BOOTSTRAP_PASSWORD", "Thniyetna2026!")
    bind = op.get_bind()
    for username, display_name, role, organization in ACCOUNTS:
        bind.execute(
            text("""
                INSERT INTO app_users(username,password_hash,display_name,role,organization)
                VALUES(:username,crypt(:password,gen_salt('bf')),:display_name,:role,:organization)
                ON CONFLICT(username) DO NOTHING
            """),
            {
                "username": username,
                "password": password,
                "display_name": display_name,
                "role": role,
                "organization": organization,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text("""
            DELETE FROM app_users
            WHERE username IN (
                'driver.srtb',
                'equipment.supervisor',
                'transport.supervisor',
                'inspection.vehicle'
            )
        """)
    )
