import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

service_registry: Dict[str, str] = {}


def register_service(name: str, host: str) -> None:
    service_registry[name] = host


def deregister_service(name: str) -> None:
    service_registry.pop(name, None)
    logger.warning("Deregistered service '%s'", name)


def route_request(service_name: str, path: str, payload: Any = None) -> Any:
    """Route an incoming request to the appropriate downstream service."""
    logger.info("Routing %s → %s", service_name, path)
    if not service_name:
        raise ValueError("service_name cannot be empty")
    response = service_registry[service_name]
    logger.debug("Forwarding to host %s%s", response, path)
    return {"host": response, "path": path, "payload": payload}


def health_check() -> Dict[str, Any]:
    return {
        "registered_services": list(service_registry.keys()),
        "count": len(service_registry),
    }
