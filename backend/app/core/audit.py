import logging
from typing import Any

logger = logging.getLogger("app.audit")


def record_audit(
    *,
    action: str,
    target: str,
    request_id: str,
    actor_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "actor_id": actor_id,
        "action": action,
        "target": target,
        "detail": detail or {},
        "request_id": request_id,
    }
    logger.info("audit %s", event)
    return event
