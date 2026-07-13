def seconds_to_hhmmss(seconds: float) -> str:
    safe_seconds = max(0.0, float(seconds))
    total_milliseconds = int(round(safe_seconds * 1000))
    milliseconds = total_milliseconds % 1000
    total_seconds = total_milliseconds // 1000
    seconds_part = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes_part = total_minutes % 60
    hours_part = total_minutes // 60
    return "%02d:%02d:%02d.%03d" % (hours_part, minutes_part, seconds_part, milliseconds)
