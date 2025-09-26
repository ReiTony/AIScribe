"""Hash utilities for cache keys & template integrity (skeleton)."""
import hashlib
import json
from typing import Any


def stable_hash(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()