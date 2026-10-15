from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class RiskRequest(BaseModel):
    segment_id: str
    horizon_hours: int = Field(default=6, ge=1, le=168)


class RiskFactor(BaseModel):
    feature: str
    contribution: float
    value: Any = None


class RiskResponse(BaseModel):
    """Backward compatible with contextual-v1; M2 model fields are optional."""
    segment_id: str
    segment_code: Optional[str] = None
    risk_score: float
    risk_category: str                       # legacy 3 levels: low / medium / high
    risk_level: Optional[str] = None         # contract 4 levels: low / medium / high / critical
    predicted_condition: Optional[str] = None
    maintenance_priority: Optional[str] = None
    horizon_days: Optional[int] = None
    components: Optional[dict] = None
    exposure_percentile: Optional[float] = None  # within-governorate rank of risk_score (display aid, not a probability)
    top_factors: List[RiskFactor] = []
    contributing_factors: List[str] = []
    model_version: str = "contextual-v1"
    source: str = "contextual-fallback"      # "m2-model" when served from a model batch
    computed_at: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class GovernorateForecast(BaseModel):
    gov_code: str
    governorate: Optional[str] = None
    forecast_date: date
    p_accident: float
    alert: bool
    expected_accidents: float
    p_fatal_accident: Optional[float] = None
    top_factors: List[RiskFactor] = []
    history_staleness_days: int = 0
    model_version: str


class WeatherIn(BaseModel):
    area_code: str = "BIZERTE"
    observed_at: datetime
    precipitation_mm: float = 0
    precipitation_probability: Optional[float] = None
    wind_kmh: Optional[float] = None
    temperature_c: Optional[float] = None
    weather_code: Optional[str] = None
    source: str = "manual"
