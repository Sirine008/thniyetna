"""
Thin wrapper around a locally running OSRM instance (M3).

Coordinate order: this client takes and returns (lat, lon), matching
data/schemas/route.schema.json. OSRM itself wants "lon,lat" in the URL and
returns GeoJSON [lon, lat]; the swap happens here and nowhere else.

Port note: MLflow already owns host port 5000, so OSRM is published on 5002
(see docker-compose.yml, service `osrm`). Inside the Docker network use
http://osrm:5000.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

DEFAULT_OSRM_URL = os.getenv("OSRM_URL", "http://localhost:5002")


class OSRMError(RuntimeError):
    """OSRM was unreachable or answered with a non-Ok code."""


@dataclass
class OSRMRoute:
    distance_m: float
    duration_s: float
    polyline: list[list[float]]  # [[lat, lon], ...]

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000

    @property
    def duration_min(self) -> float:
        return self.duration_s / 60


class OSRMClient:
    def __init__(
        self,
        base_url: str = DEFAULT_OSRM_URL,
        profile: str = "driving",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,  # injectable for tests
    ):
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def route(
        self,
        coordinates: list[tuple[float, float]],
        alternatives: int = 0,
    ) -> list[OSRMRoute]:
        """
        Route through `coordinates` given as [(lat, lon), ...] (at least 2).
        Returns the best route first, then up to `alternatives` extra routes.
        """
        if len(coordinates) < 2:
            raise ValueError("need at least an origin and a destination")

        coord_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
        url = f"{self.base_url}/route/v1/{self.profile}/{coord_str}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "alternatives": str(alternatives) if alternatives else "false",
        }

        try:
            resp = self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise OSRMError(f"OSRM unreachable at {self.base_url}: {exc}") from exc

        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code != 200 or body.get("code") != "Ok":
            raise OSRMError(f"OSRM error {resp.status_code}: {body.get('code')} {body.get('message', '')}".strip())

        return [
            OSRMRoute(
                distance_m=r["distance"],
                duration_s=r["duration"],
                polyline=[[lat, lon] for lon, lat in r["geometry"]["coordinates"]],
            )
            for r in body["routes"]
        ]

    def close(self) -> None:
        self._http.close()
