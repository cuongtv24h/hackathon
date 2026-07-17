# === TASK:WP-006:START ===
"""Retention sweep for the Foundation data tier.

The retention periods are pinned by ``docs/artifacts/interface/interface-guidelines.md``
(INT-09) — the binding values declared in section *MVP Pilot binding values*:

* context: 30-minute idle / 24-hour maximum
* anonymized conversation: 90 days
* feedback: 180 days
* mock appointment: 90 days
* emergency / security / content audit and aggregate analytics: 365 days
* raw conversation PII is never stored

This module is intentionally small: it calls one SQL function per table
(``fn_delete_overdue_*``) and returns a deterministic report that the
Gateway and the WP-606 release gate can audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

from .connection import DatabaseClient, DatabaseError


# Order matters only for diagnostics — the report is built in this order.
RETENTION_TARGETS: List[Dict[str, str]] = [
    {
        "key": "conversation_sessions",
        "function": "fn_delete_overdue_sessions()",
        "period": "24 hours (context max)",
    },
    {
        "key": "conversation_messages",
        "function": "fn_delete_overdue_messages()",
        "period": "90 days (anonymized conversation)",
    },
    {
        "key": "appointments",
        "function": "fn_delete_overdue_appointments()",
        "period": "90 days (mock appointment)",
    },
    {
        "key": "feedback",
        "function": "fn_delete_overdue_feedback()",
        "period": "180 days (feedback)",
    },
    {
        "key": "analytics_events",
        "function": "fn_delete_overdue_analytics()",
        "period": "365 days (aggregate analytics)",
    },
    {
        "key": "audit_events",
        "function": "fn_delete_overdue_audit()",
        "period": "365 days (emergency/security/content audit)",
    },
]


RETENTION_SUMMARY_KEYS: List[str] = [item["key"] for item in RETENTION_TARGETS]


@dataclass
class RetentionSummary:
    """Result of one retention sweep.

    The dataclass is the public return value of :func:`run_retention_sweep`.
    It is intentionally a plain data container so it can be serialised to
    JSON for the Foundation audit log without further mapping.
    """

    deleted: Dict[str, int] = field(default_factory=dict)
    total_deleted: int = 0
    targets_run: int = 0
    duration_ms: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deleted": dict(self.deleted),
            "total_deleted": self.total_deleted,
            "targets_run": self.targets_run,
            "duration_ms": self.duration_ms,
            "errors": list(self.errors),
        }


def run_retention_sweep(
    client: DatabaseClient,
    *,
    targets: Mapping[str, str] | None = None,
) -> RetentionSummary:
    """Run the retention sweep against ``client``.

    The optional ``targets`` mapping lets callers restrict the sweep to a
    subset of tables (e.g. a cron that only cleans analytics at night). The
    keys must be a subset of :data:`RETENTION_SUMMARY_KEYS`.
    """

    client.ensure_ready()
    started = _now_ms()
    summary = RetentionSummary()

    selected = _resolve_targets(targets)
    for target in selected:
        key = target["key"]
        function = target["function"]
        try:
            deleted = _invoke_retention_function(client, function)
        except DatabaseError as exc:
            summary.errors.append(
                {"key": key, "code": exc.code, "message": exc.message}
            )
            continue
        summary.deleted[key] = deleted
        summary.total_deleted += deleted
        summary.targets_run += 1

    summary.duration_ms = max(0, _now_ms() - started)
    return summary


def _resolve_targets(
    override: Mapping[str, str] | None,
) -> List[Dict[str, str]]:
    if not override:
        return list(RETENTION_TARGETS)
    if not isinstance(override, Mapping):  # type: ignore[redundant-expr]
        raise DatabaseError(
            "INVALID_REQUEST",
            "retention targets override must be a mapping of key -> function",
            category="validation",
            field_errors={"targets": "must be a mapping"},
        )
    unknown = set(override.keys()) - set(RETENTION_SUMMARY_KEYS)
    if unknown:
        raise DatabaseError(
            "INVALID_REQUEST",
            f"unknown retention target(s): {sorted(unknown)}",
            category="validation",
            field_errors={"targets": f"unknown: {sorted(unknown)}"},
        )
    return [
        {"key": key, "function": override[key], "period": "custom"}
        for key in override.keys()
    ]


def _invoke_retention_function(client: DatabaseClient, function: str) -> int:
    """Invoke one of the ``fn_delete_overdue_*`` SQL functions.

    The in-memory driver only supports a small set of statements (see
    :class:`_InMemoryStore`). For retention we therefore translate the
    function call to a ``DELETE FROM ... WHERE expires_at < now()``
    statement that the in-memory store understands, and fall back to
    executing the original statement for real drivers.
    """

    if client.driver == "memory":
        # The in-memory store does not parse function calls, so we map each
        # canonical function name to the DELETE statement the stub knows.
        mapping = {
            "fn_delete_overdue_sessions()":     "conversation_sessions",
            "fn_delete_overdue_messages()":    "conversation_messages",
            "fn_delete_overdue_appointments()": "appointments",
            "fn_delete_overdue_feedback()":    "feedback",
            "fn_delete_overdue_analytics()":    "analytics_events",
            "fn_delete_overdue_audit()":       "audit_events",
        }
        table = mapping.get(function)
        if table is None:
            raise DatabaseError(
                "CONFIG_UNAVAILABLE",
                f"unknown retention function {function!r}",
                category="system",
            )
        store = client.in_memory_store()
        before = store.row_count(table)
        store.execute(f"DELETE FROM {table} WHERE expires_at < now();")
        after = store.row_count(table)
        return max(0, before - after)

    # Real driver path: send the function call verbatim. The driver returns
    # the row count or raises; the Foundation layer surfaces driver errors
    # as DatabaseError so callers can map them to UnifiedErrorEnvelope.
    try:
        results = client.execute_script(f"SELECT {function};")
    except DatabaseError:
        raise
    return int(results[0]) if results else 0


def _now_ms() -> int:
    """Monotonic millisecond clock used for the summary.

    Wrapped in a function so tests can monkeypatch it.
    """

    import time

    return int(time.monotonic() * 1000)


__all__ = [
    "RETENTION_SUMMARY_KEYS",
    "RETENTION_TARGETS",
    "RetentionSummary",
    "run_retention_sweep",
]
# === TASK:WP-006:END ===
