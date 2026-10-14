from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

StaffRole = Literal["bus_driver", "transport_supervisor", "inspection_vehicle", "equipment_supervisor"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class CitizenRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=120)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str


class StaffCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=120)
    role: StaffRole
    organization: Optional[str] = Field(default=None, max_length=120)


class StaffPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class StaffActiveUpdate(BaseModel):
    active: bool


class StaffOut(BaseModel):
    username: str
    display_name: str
    role: str
    organization: Optional[str] = None
    active: bool
    created_at: datetime
