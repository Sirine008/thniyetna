"""JWT authentication and role-based authorization."""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import JWT_ALGORITHM, JWT_SECRET

TOKEN_TTL_HOURS = 12
ROLES = (
    "citizen",
    "bus_driver",
    "equipment_supervisor",
    "transport_supervisor",
    "inspection_vehicle",
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def create_access_token(*, username: str, role: str, display_name: str, organization: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "name": display_name,
        "org": organization,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise credentials_error from exc
    if not payload.get("sub") or payload.get("role") not in ROLES:
        raise credentials_error
    return payload


def require_role(*allowed_roles: str):
    def _checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _checker
