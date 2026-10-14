"""Authentication endpoints.

Citizens can self-register (role citizen only). Operational staff accounts are
bootstrapped by Alembic (password from .env), then managed per ministry by its
supervisors through /auth/staff, or by hand with `python -m auth.create_user`.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .schemas import (CitizenRegisterRequest, LoginRequest, StaffActiveUpdate, StaffCreateRequest, StaffOut,
                      StaffPasswordReset, TokenResponse)
from shared.auth import create_access_token, get_current_user
from shared.db import get_db
from shared.realtime import publish

router = APIRouter()

# Which staff roles each supervisor role may manage. Any other role gets 403.
MANAGEABLE_ROLES = {
    "transport_supervisor": {"bus_driver", "transport_supervisor"},
    "equipment_supervisor": {"inspection_vehicle", "equipment_supervisor"},
}
SUPERVISOR_ROLES = set(MANAGEABLE_ROLES)
DEFAULT_ORG = {
    "bus_driver": "SRTB",
    "transport_supervisor": "SRTB",
    "inspection_vehicle": "Ministère de l'Équipement",
    "equipment_supervisor": "Ministère de l'Équipement",
}
_STAFF_COLUMNS = "username, display_name, role, organization, active, created_at"


def _issue(row) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            username=row["username"],
            role=row["role"],
            display_name=row["display_name"],
            organization=row["organization"],
        ),
        role=row["role"],
        display_name=row["display_name"],
    )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
            SELECT username, display_name, role, organization
            FROM app_users
            WHERE lower(username)=lower(:username)
              AND active
              AND password_hash=crypt(:password,password_hash)
        """),
        {"username": req.username.strip(), "password": req.password},
    ).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue(row)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_citizen(req: CitizenRegisterRequest, db: Session = Depends(get_db)):
    try:
        row = db.execute(
            text("""
                INSERT INTO app_users(username,password_hash,display_name,role,organization)
                VALUES(lower(:username),crypt(:password,gen_salt('bf')),:display_name,'citizen','Public')
                RETURNING username,display_name,role,organization
            """),
            {
                "username": req.username.strip(),
                "password": req.password,
                "display_name": req.display_name.strip(),
            },
        ).mappings().one()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    return _issue(row)


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {
        "username": user["sub"],
        "role": user["role"],
        "display_name": user.get("name"),
        "organization": user.get("org"),
    }


# ----------------------------------------------------------------- staff accounts (per ministry)
def _manageable(user: dict) -> set[str]:
    roles = MANAGEABLE_ROLES.get(user.get("role"))
    if not roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return roles


def _target(db: Session, user: dict, username: str):
    """Account the caller may manage; another ministry's account is reported as not found."""
    roles = _manageable(user)
    row = db.execute(
        text(f"SELECT {_STAFF_COLUMNS} FROM app_users WHERE username=lower(:username)"),
        {"username": username.strip()},
    ).mappings().first()
    if not row or row["role"] not in roles:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return row


@router.post("/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def create_staff(req: StaffCreateRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if req.role not in _manageable(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Your ministry cannot create '{req.role}' accounts")
    try:
        row = db.execute(
            text(f"""
                INSERT INTO app_users(username,password_hash,display_name,role,organization)
                VALUES(lower(:username),crypt(:password,gen_salt('bf')),:display_name,:role,:organization)
                RETURNING {_STAFF_COLUMNS}
            """),
            {
                "username": req.username.strip(),
                "password": req.password,
                "display_name": req.display_name.strip(),
                "role": req.role,
                "organization": (req.organization or "").strip() or DEFAULT_ORG[req.role],
            },
        ).mappings().one()
        publish(db, "staff.account.created", {"username": row["username"], "role": row["role"]}, user["role"])
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    return row


@router.get("/staff", response_model=list[StaffOut])
def list_staff(db: Session = Depends(get_db), user=Depends(get_current_user)):
    roles = sorted(_manageable(user))
    return list(db.execute(
        text(f"SELECT {_STAFF_COLUMNS} FROM app_users WHERE role = ANY(CAST(:roles AS text[])) ORDER BY role, username"),
        {"roles": roles},
    ).mappings())


@router.patch("/staff/{username}/active", response_model=StaffOut)
def set_staff_active(username: str, req: StaffActiveUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    target = _target(db, user, username)
    if not req.active and target["username"] == user["sub"].lower():
        raise HTTPException(status_code=422, detail="Vous ne pouvez pas désactiver votre propre compte")
    row = db.execute(
        text(f"UPDATE app_users SET active=:active WHERE username=:username RETURNING {_STAFF_COLUMNS}"),
        {"active": req.active, "username": target["username"]},
    ).mappings().one()
    db.commit()
    return row


@router.post("/staff/{username}/password")
def reset_staff_password(username: str, req: StaffPasswordReset, db: Session = Depends(get_db), user=Depends(get_current_user)):
    target = _target(db, user, username)
    if target["role"] in SUPERVISOR_ROLES:
        # Otherwise a supervisor could take over a peer's account; recovery goes through the CLI.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Password of a supervisor account: use the CLI (auth.create_user --reset-password)")
    db.execute(
        text("UPDATE app_users SET password_hash=crypt(:password,gen_salt('bf')) WHERE username=:username"),
        {"password": req.password, "username": target["username"]},
    )
    db.commit()
    return {"status": "password_reset", "username": target["username"]}
