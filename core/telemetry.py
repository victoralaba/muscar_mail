import logging
from typing import Optional
import sentry_sdk

logger = logging.getLogger("muscar_mail.telemetry")


def init_telemetry(dsn: Optional[str], environment: str = "production") -> bool:
    """Initializes Sentry telemetry SDK with fail-open resilience.

    Returns:
        True if Sentry was initialized, False otherwise.
    """
    if not dsn or not dsn.strip():
        logger.debug("Sentry DSN not provided. Telemetry disabled.")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn.strip(),
            environment=environment,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.0,
            send_default_pii=False,
            attach_stacktrace=True,
        )
        logger.info("Sentry telemetry successfully initialized.", extra={"environment": environment})
        return True
    except Exception as exc:
        # Invariant INV-OPS-1: Telemetry must fail open
        logger.warning(f"Failed to initialize Sentry telemetry: {exc}. Continuing without telemetry.")
        return False
