from datetime import datetime, timezone


def iso_utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_iso_utc(dt) -> str:
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
