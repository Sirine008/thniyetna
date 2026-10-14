"""RiskScore contract (data/schemas/risk_score.schema.json) validation."""
from __future__ import annotations

import json
from functools import lru_cache

from .config import REPO_ROOT

SCHEMA_PATH = REPO_ROOT / "data" / "schemas" / "risk_score.schema.json"


@lru_cache(maxsize=1)
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(record: dict) -> None:
    """Raise ValueError if the record does not satisfy the RiskScore contract."""
    try:
        import jsonschema
    except ImportError:  # minimal fallback
        for k in schema()["required"]:
            if k not in record:
                raise ValueError(f"RiskScore missing required field '{k}'")
        if not 0 <= record["risk_score"] <= 1:
            raise ValueError("risk_score out of [0, 1]")
        return
    try:
        jsonschema.validate(record, schema())
    except jsonschema.ValidationError as exc:
        raise ValueError(f"RiskScore contract violation: {exc.message}") from exc


def validate_many(records: list[dict]) -> int:
    for r in records:
        validate(r)
    return len(records)
