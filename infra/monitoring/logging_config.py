"""
Structured logging config shared across the API. Import and call
`configure_logging()` once at app startup (main.py).
"""
import logging


def configure_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
