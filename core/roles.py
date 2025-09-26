from enum import Enum


class UserRole(str, Enum):
    client = "client"
    lawyer = "lawyer"
    admin = "admin"

    @classmethod
    def list(cls) -> list[str]:  # convenience for validation
        return [r.value for r in cls]