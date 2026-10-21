"""Writes to the app's own tables. Every write is idempotent ("insert ... on conflict update"), so
saving the same session twice (a retry, a repeated request) updates rows instead of duplicating them.
"""

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert

from ai_decision_arena.db.engine import session_factory
from ai_decision_arena.db.models import DecisionReport, DecisionSession, EvidenceRecord

EVIDENCE_COLUMNS = {"evidence_id", "perspective", "source_url", "source_title", "source_type",
                    "relevant_excerpt", "verification_status", "retrieved_at"}


def _upsert_session(db, thread_id: str, state: dict, status: str, metrics: dict | None):
    values = {
        "thread_id": thread_id,
        "question": state.get("question", ""),
        "condition_name": state.get("condition_name"),
        "condition_category": state.get("condition_category"),
        "status": status,
        "red_flags": state.get("red_flags", []),
        "metrics": metrics or {},
        "completed_at": datetime.now(timezone.utc) if metrics is not None else None,
    }
    stmt = insert(DecisionSession).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["thread_id"],
        set_={k: stmt.excluded[k] for k in values if k != "thread_id"} | {"updated_at": datetime.now(timezone.utc)},
    ).returning(DecisionSession.id)
    return db.execute(stmt).scalar_one()


def save_session_status(thread_id: str, state: dict, status: str) -> None:
    """The API (Phase 8) calls this when a session starts and at every pause, so decision_sessions shows
    live statuses, not only finished sessions. Leaves metrics / completed_at alone: completion owns those."""
    values = {
        "thread_id": thread_id,
        "question": state.get("question", ""),
        "condition_name": state.get("condition_name"),
        "condition_category": state.get("condition_category"),
        "status": status,
        "red_flags": state.get("red_flags", []),
    }
    with session_factory().begin() as db:
        stmt = insert(DecisionSession).values(**values)
        db.execute(stmt.on_conflict_do_update(
            index_elements=["thread_id"],
            set_={k: stmt.excluded[k] for k in values if k != "thread_id"} | {"updated_at": datetime.now(timezone.utc)},
        ))


def save_completion(thread_id: str, state: dict, status: str, metrics: dict) -> None:
    """Session + evidence + report in ONE transaction: all saved, or nothing (rollback on any error)."""
    with session_factory().begin() as db:
        session_id = _upsert_session(db, thread_id, state, status, metrics)

        rows = [
            {
                "session_id": session_id,
                "evidence_id": e["evidence_id"],
                "perspective": e["perspective"],
                "source_url": str(e["source_url"]),
                "source_title": e["source_title"],
                "source_type": e["source_type"],
                "excerpt": e.get("relevant_excerpt", ""),
                "verification_status": e.get("verification_status", "pending"),
                "retrieved_at": e.get("retrieved_at"),
                "details": {k: v for k, v in e.items() if k not in EVIDENCE_COLUMNS},
            }
            for e in state.get("evidence", [])
        ]
        if rows:
            stmt = insert(EvidenceRecord).values(rows)
            db.execute(stmt.on_conflict_do_update(
                constraint="uq_evidence_session_evidence_id",
                set_={c: stmt.excluded[c] for c in rows[0] if c not in ("session_id", "evidence_id")},
            ))

        report = state.get("final_report")
        if report:
            stmt = insert(DecisionReport).values(session_id=session_id, status=status,
                                                 is_conditional=bool(report.get("is_conditional")), report_json=report)
            db.execute(stmt.on_conflict_do_update(
                index_elements=["session_id"],
                set_={"status": stmt.excluded.status, "is_conditional": stmt.excluded.is_conditional,
                      "report_json": stmt.excluded.report_json},
            ))
