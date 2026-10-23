from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ComplaintIn(BaseModel):
    citizen_id: Optional[str] = None
    description: str = Field(min_length=3, max_length=1000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    category: str = "road_damage"
    image_url: Optional[str] = None
    image_storage_key: Optional[str] = None


class ComplaintOut(BaseModel):
    id: str
    status: str
    description: str
    latitude: float
    longitude: float
    created_at: datetime
    category: Optional[str] = None
    image_url: Optional[str] = None
    demo: bool = False  # demo data (scripts/seed_demo.py), shown as "DÉMO — données fictives"


class ComplaintStatusUpdate(BaseModel):
    status: str
    note: Optional[str] = Field(default=None, max_length=1000)


class VehicleCreate(BaseModel):
    vehicle_code: str = Field(min_length=2, max_length=80)
    vehicle_type: str = Field(min_length=2, max_length=40)
    owner_org: str = Field(min_length=2, max_length=120)
    label: Optional[str] = Field(default=None, max_length=120)


class AlertAck(BaseModel):
    notification_id: str
