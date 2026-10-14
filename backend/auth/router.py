"""Authentication endpoints.

Citizens can self-register. Operational staff accounts are created by the
Alembic bootstrap migration using the password configured in .env.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .schemas import CitizenRegisterRequest, LoginRequest, TokenResponse
from shared.auth import create_access_token, get_current_user
from shared.db import get_db

router = APIRouter()


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
