"""Structured logging configuration.

Uses structlog so every log line is JSON in non-local environments (easy to
ship to a log aggregator) and human-readable in local dev.
"""

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    # Note: we use structlog's own PrintLoggerFactory (not stdlib logging), so
    # only processors compatible with a plain structlog logger belong here —
    # `structlog.stdlib.add_logger_name` requires a stdlib logger and would
    # crash on `PrintLogger`. The event name is bound explicitly instead via
    # `get_logger(__name__)`.
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.ENV in ("local", "test"):
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.DEBUG else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "finsight") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
