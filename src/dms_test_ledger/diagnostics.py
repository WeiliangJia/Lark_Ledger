from __future__ import annotations

from typing import Any

from .errors import AuthenticationError
from .lark import LarkBaseClient
from .schema import SchemaManager
from .state import StateStore


def run_doctor(
    *,
    state: StateStore,
    lark: LarkBaseClient,
    schema: SchemaManager,
) -> dict[str, Any]:
    """Verify OAuth, target access and ledger schema without changing Lark data."""
    tokens = state.load_tokens()
    if tokens is None:
        raise AuthenticationError("No Lark OAuth token found; run auth first")
    # This also verifies refresh-token rotation while holding the shared lock.
    lark.token_manager.get_access_token()
    app_token, table_id = lark.resolve_target()
    plan = schema.plan(app_token, table_id)
    return {
        "connection_ok": True,
        "authorized": True,
        "refresh_expires_at": tokens.refresh_expires_at,
        "target_accessible": True,
        "table_id": table_id,
        "record_count": lark.record_count(app_token, table_id),
        "schema_ready": plan.valid,
        "schema": plan.to_dict(),
        "ready": plan.valid,
    }
