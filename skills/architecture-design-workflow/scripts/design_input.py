"""Shared validation for numeric geometry inputs."""
import math


def number(value, label, minimum=None):
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or (minimum is not None and value < minimum)
    ):
        raise ValueError(f"{label}: expected a finite number" + (f" >= {minimum}" if minimum is not None else ""))
    return value


def position(values, count, label):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError(f"{label}: expected {count} coordinates")
    return tuple(number(v, label) for v in values)


def keyed(records, label):
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{label}: expected an object")
        key = record.get("id")
        if not isinstance(key, str) or not key.strip() or key in result:
            raise ValueError(f"{label}: missing or duplicate id {key!r}")
        result[key] = record
    return result
