"""Auto-detect imperial/non-SI units and convert to SI."""

import re
from typing import Optional

# Imperial -> SI conversions
LENGTH_SI = {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001}
LENGTH_IMPERIAL = {
    "ft": 0.3048,
    "in": 0.0254,
    "mi": 1609.34,
    "feet": 0.3048,
    "inch": 0.0254,
    "inches": 0.0254,
}
WEIGHT_SI = {"kg": 1, "g": 0.001}
WEIGHT_IMPERIAL = {
    "lb": 0.453592,
    "lbs": 0.453592,
    "oz": 0.0283495,
    "pound": 0.453592,
    "pounds": 0.453592,
}


def _to_si_length(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    if meters >= 1:
        return f"{meters:.2f} m"
    if meters >= 0.01:
        return f"{meters * 100:.2f} cm"
    return f"{meters * 1000:.2f} mm"


def _to_si_weight(kg: float) -> str:
    if kg >= 1:
        return f"{kg:.2f} kg"
    return f"{kg * 1000:.0f} g"


def _to_si_temp(f: float) -> str:
    c = (f - 32) * 5 / 9
    return f"{c:.1f} °C"


# Regex patterns: (pattern, unit_key, converter_func)
# Match: 10 lb, 5.5 lbs, 10lb
PATTERNS = [
    (
        re.compile(r"\b(\d+\.?\d*)\s*(lb|lbs|pound|pounds)\b", re.I),
        "weight_imperial",
        WEIGHT_IMPERIAL,
        _to_si_weight,
        "kg",
    ),
    (
        re.compile(r"\b(\d+\.?\d*)\s*(oz)\b", re.I),
        "weight_imperial",
        WEIGHT_IMPERIAL,
        _to_si_weight,
        "kg",
    ),
    (
        re.compile(r"\b(\d+\.?\d*)\s*(ft|feet)\b", re.I),
        "length_imperial",
        LENGTH_IMPERIAL,
        _to_si_length,
        "m",
    ),
    (
        re.compile(r"\b(\d+)\s*['′]\s*(\d+)\s*(?:[\"″]|in|inches)?\b", re.I),
        "ft_in",
        None,
        None,
        None,
    ),  # 5'10"
    (
        re.compile(r"\b(\d+\.?\d*)\s*(in|inch|inches)\b", re.I),
        "length_imperial",
        LENGTH_IMPERIAL,
        _to_si_length,
        "m",
    ),
    (
        re.compile(r"\b(\d+\.?\d*)\s*(mi)\b", re.I),
        "length_imperial",
        LENGTH_IMPERIAL,
        _to_si_length,
        "m",
    ),
    (re.compile(r"\b(\d+\.?\d*)\s*[°º]\s*[Ff]\b"), "temp_f", None, _to_si_temp, None),
    (re.compile(r"\b(\d+\.?\d*)\s*[Ff](?:\s|$|,|\.)"), "temp_f", None, _to_si_temp, None),
]


def detect_and_convert(text: str) -> Optional[str]:
    for pat, kind, units, conv, _ in PATTERNS:
        m = pat.search(text)
        if not m:
            continue

        if kind == "ft_in":
            ft, inch = float(m.group(1)), float(m.group(2))
            meters = ft * LENGTH_IMPERIAL["ft"] + inch * LENGTH_IMPERIAL["in"]
            return _to_si_length(meters)
        if kind == "temp_f":
            f = float(m.group(1))
            return _to_si_temp(f)
        if kind in ("weight_imperial", "length_imperial") and units:  # pragma: no branch
            amount = float(m.group(1))
            u = m.group(2).lower()
            if u in units:  # pragma: no branch
                if kind == "weight_imperial":
                    kg = amount * units[u]
                    return _to_si_weight(kg)
                meters = amount * units[u]
                return _to_si_length(meters)
    return None
