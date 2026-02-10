def extract_resume_ticks(item: dict) -> int:
    """Best-effort extraction of resume position in ticks from an item."""
    try:
        ud = item.get("UserData") or {}
        ticks = ud.get("PlaybackPositionTicks") or ud.get("ResumePositionTicks") or 0
        return int(ticks or 0)
    except Exception:
        return 0


def ticks_to_seconds(ticks: int) -> float:
    try:
        return float(ticks) / 10_000_000.0
    except Exception:
        return 0.0
