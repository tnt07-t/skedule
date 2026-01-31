from datetime import datetime, timedelta
from fastapi import HTTPException


def parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def clamp_range(start: str, end: str, max_days: int = 7) -> tuple[datetime, datetime]:
    start_dt = parse_iso(start)
    end_dt = parse_iso(end)
    max_end = start_dt + timedelta(days=max_days)
    if end_dt > max_end:
        end_dt = max_end
    if end_dt <= start_dt:
        raise HTTPException(400, "end must be after start")
    return start_dt, end_dt
