from __future__ import annotations

AVAILABLE_PERMISSION_IDS = (
    "view_dashboard",
    "view_analytics",
    "view_portfolio",
    "view_pair_universe",
    "view_logs",
    "manage_bot",
    "manage_pair_supply",
    "switch_active_pair",
    "view_reports",
    "generate_reports",
    "manage_logs_reports",
    "edit_settings",
    "manage_api",
    "manage_users",
    "manage_roles",
)

BUILTIN_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": list(AVAILABLE_PERMISSION_IDS),
    "trader": [
        "view_dashboard",
        "view_analytics",
        "view_portfolio",
        "view_pair_universe",
        "view_logs",
        "manage_bot",
        "manage_pair_supply",
        "switch_active_pair",
        "view_reports",
        "generate_reports",
    ],
    "viewer": [
        "view_dashboard",
        "view_analytics",
        "view_portfolio",
        "view_pair_universe",
        "view_logs",
        "view_reports",
    ],
}


def normalize_permission_ids(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    allowed = set(AVAILABLE_PERMISSION_IDS)
    for raw in values:
        permission_id = str(raw or "").strip()
        if not permission_id:
            continue
        if permission_id not in allowed:
            raise ValueError(f"Unknown permission: {permission_id}")
        if permission_id in seen:
            continue
        seen.add(permission_id)
        normalized.append(permission_id)
    return normalized
