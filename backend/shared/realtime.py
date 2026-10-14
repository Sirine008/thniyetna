"""Database-backed realtime notification helpers.

The outbox is durable. SSE clients poll it once per second, so events survive API
restarts and the frontend gets near-real-time updates without a separate broker.
A broker (Redis/NATS/Kafka) can replace this transport later without changing the
actor APIs.
"""
import json
from sqlalchemy import text


def publish(db, topic: str, payload: dict, recipient_ref: str | None = None):
    row = db.execute(text("""
        INSERT INTO notification_outbox(topic, recipient_ref, payload)
        VALUES (:topic, :recipient, CAST(:payload AS jsonb))
        RETURNING id::text, created_at
    """), {"topic": topic, "recipient": recipient_ref, "payload": json.dumps(payload)}).mappings().one()
    return dict(row)
