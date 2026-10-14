"""Create (or recover) an account by hand: first admin, supervisor recovery.

    docker compose exec api python -m auth.create_user --username X --role equipment_supervisor --name "..."
    docker compose exec api python -m auth.create_user --username X --role equipment_supervisor --name "..." --reset-password

The password is read with getpass (prompted twice). It is never a command-line
argument and never printed. Usernames are stored lowercase, like /auth/register.
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys

from sqlalchemy import text

from shared.auth import ROLES
from shared.db import SessionLocal

from .router import DEFAULT_ORG

USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,80}$")


def _read_password() -> str:
    first = getpass.getpass("Password (min 8 characters): ")
    if not 8 <= len(first) <= 128:
        sys.exit("error: the password must be 8 to 128 characters long")
    if getpass.getpass("Repeat password: ") != first:
        sys.exit("error: the two passwords differ")
    return first


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create a THNIYETNA account (password prompted, never an argument)")
    ap.add_argument("--username", required=True)
    ap.add_argument("--role", required=True, choices=ROLES)
    ap.add_argument("--name", required=True, help="display name")
    ap.add_argument("--org", default=None, help="organization (default depends on the role)")
    ap.add_argument("--reset-password", action="store_true",
                    help="the account exists: set a new password (and reactivate it) instead of failing")
    args = ap.parse_args(argv)

    username = args.username.strip().lower()
    if not USERNAME.match(username):
        sys.exit("error: username must be 3-80 characters among A-Z a-z 0-9 . _ -")
    if not 2 <= len(args.name.strip()) <= 120:
        sys.exit("error: --name must be 2 to 120 characters long")

    with SessionLocal() as db:
        existing = db.execute(text("SELECT role FROM app_users WHERE username=:u"), {"u": username}).scalar()
        if existing and not args.reset_password:
            sys.exit(f"error: '{username}' already exists (role {existing}); use --reset-password to set a new password")
        if not existing and args.reset_password:
            sys.exit(f"error: '{username}' does not exist; run without --reset-password to create it")
        password = _read_password()
        if existing:
            db.execute(text("UPDATE app_users SET password_hash=crypt(:p,gen_salt('bf')), active=true WHERE username=:u"),
                       {"p": password, "u": username})
            db.commit()
            print(f"password reset for '{username}' (role {existing}); account active")
            return 0
        org = args.org or DEFAULT_ORG.get(args.role, "Public")
        db.execute(text("""
            INSERT INTO app_users(username,password_hash,display_name,role,organization)
            VALUES(:u,crypt(:p,gen_salt('bf')),:n,:r,:o)"""),
                   {"u": username, "p": password, "n": args.name.strip(), "r": args.role, "o": org})
        db.commit()
    print(f"created '{username}' (role {args.role}, organization {org})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
