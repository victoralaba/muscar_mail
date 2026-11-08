import logging
import sys
from typing import Any, MutableMapping
import structlog

SENSITIVE_KEYS = {
    "authorization",
    "x-api-key",
    "password",
    "verifalia_password",
    "mcp_api_keys",
    "secret",
    "token",
}


def redact_sensitive_data(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that recursively redacts sensitive headers and credentials."""

    def _sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            sanitized = {}
            for k, v in value.items():
                if isinstance(k, str) and k.lower() in SENSITIVE_KEYS:
                    sanitized[k] = "[REDACTED]"
                else:
                    sanitized[k] = _sanitize(v)
            return sanitized
        elif isinstance(value, list):
            return [_sanitize(item) for item in value]
        return value

    return _sanitize(event_dict)


def setup_logging(environment: str = "production", debug: bool = False) -> None:
    """Configures structured logging for production (JSON) and development (Console)."""
    log_level = logging.DEBUG if debug else logging.INFO

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        redact_sensitive_data,
    ]

    if environment.lower() == "production":
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    # Intercept standard library logging
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)


def get_logger(name: str = "muscar_mail") -> structlog.BoundLogger:
    return structlog.get_logger(name)
