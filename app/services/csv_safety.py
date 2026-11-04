"""Preserve trusted numeric scores and neutralize formula-like text cells."""

import math


def safe_cell(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ValueError("Non-finite numeric CSV value.")
        return value
    text = "" if value is None else str(value)
    trimmed = text.lstrip(" \t\r\n\ufeff")
    if text.startswith(("\t", "\r", "\n")) or trimmed.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
