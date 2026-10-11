import logging

import structlog


def setup_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Logging terstruktur. Bind guild_id/user_id/command lewat structlog.contextvars."""
    logging.basicConfig(format="%(message)s", level=level.upper())
    renderer = structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
    )