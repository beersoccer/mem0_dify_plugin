from __future__ import annotations


def build_user_ids(raw_value: str, default_user: str = "test_user") -> list[str]:
    """Build a user id list from env value.

    - If raw_value is an integer N, generate user1..userN.
    - Otherwise, treat raw_value as a comma-separated list.
    """
    normalized = (raw_value or "").strip()
    if not normalized:
        return [default_user]

    if normalized.isdigit():
        count = int(normalized)
        if count <= 0:
            return ["user1"]
        return [f"user{i}" for i in range(1, count + 1)]

    user_ids = [uid.strip() for uid in normalized.split(",") if uid.strip()]
    return user_ids or [default_user]

