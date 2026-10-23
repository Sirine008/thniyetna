from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RoadEventIn(BaseModel):
    source: str = "inspection_vehicle"
    latitude: float
    longitude: float
    timestamp: datetime
    defect_type: str = "pothole"
    severity: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.8, ge=0, le=1)
    image_url: Optional[str] = None
    video_ref: Optional[str] = None
    text_description: Optional[str] = None
    session_id: Optional[str] = None


class RoadEventOut(BaseModel):
    id: str
    segment_id: Optional[str] = None
    defect_type: str
    severity: float
    confidence: float
    latitude: float
    longitude: float
    source: str
    timestamp: datetime
    validated: bool
    media_uri: Optional[str] = None
    demo: bool = False  # demo data (scripts/seed_demo.py), shown as "DÉMO — données fictives"


class InspectionStart(BaseModel):
    vehicle_code: str = "TRUCK-BIZ-01"
    video_uri: Optional[str] = None
    video_storage_key: Optional[str] = None
    mode: Literal["live", "video", "image"] = "video"


class InspectionSessionOut(BaseModel):
    id: str
    vehicle_code: str
    status: str
    started_at: datetime
    video_uri: Optional[str] = None
    video_storage_key: Optional[str] = None


class VehicleHeartbeat(BaseModel):
    latitude: float
    longitude: float
    timestamp: datetime
    speed_kmh: Optional[float] = Field(default=None, ge=0)
    heading_deg: Optional[float] = Field(default=None, ge=0, le=360)
    accuracy_m: Optional[float] = Field(default=None, ge=0)


class PerceptionJobCreate(BaseModel):
    job_type: Literal["image", "video"]
    storage_key: str
    media_uri: Optional[str] = None
    session_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    captured_at: Optional[datetime] = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_location(self):
        if self.job_type == "image" and (self.latitude is None or self.longitude is None):
            raise ValueError("Image jobs require latitude and longitude")
        if self.job_type == "video" and not self.session_id:
            raise ValueError("Video jobs require session_id so GPS can be aligned to frames")
        return self


class PerceptionJobOut(BaseModel):
    id: str
    job_type: str
    source: str
    storage_key: str
    media_uri: Optional[str] = None
    session_id: Optional[str] = None
    status: str
    progress: float
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ObservationOut(BaseModel):
    id: str
    event_id: Optional[str] = None
    session_id: Optional[str] = None
    source: str
    defect_type: str
    confidence: float
    severity_proxy: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    captured_at: datetime
    frame_index: Optional[int] = None
    frame_time_s: Optional[float] = None
    bbox_xyxy: Optional[list[float]] = None
    media_uri: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    demo: bool = False
