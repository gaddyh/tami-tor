from typing import Optional, Any

def _get(s: Any, key: str, default=None):
    if isinstance(s, dict):
        return s.get(key, default)
    return getattr(s, key, default)

def find_service_id_by_name(services: list[Any], service_name: str) -> Optional[str]:
    needle = (service_name or "").strip()
    if not needle:
        return None

    for s in services:
        name = (_get(s, "name", "") or "").strip()
        if name == needle:
            return _get(s, "id", None)

    # fallback: contains match
    for s in services:
        name = (_get(s, "name", "") or "").strip()
        if needle in name or name in needle:
            return _get(s, "id", None)

    return None
