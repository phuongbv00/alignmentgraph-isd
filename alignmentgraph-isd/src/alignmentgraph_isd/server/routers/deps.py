"""Shared lookups and conversions for the routers."""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request, status
from sqlmodel import Session as DBSession
from sqlmodel import select

from .. import briefs
from ..models import Message, Program, Run, RunStatus, Session
from ..runner import RunManager
from ..schemas import MessageOut, ProgramSummary, RunSummary
from ..settings import Settings


def get_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def load_program(db: DBSession, program_id: str) -> Program:
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Program not found.")
    return program


def load_run(db: DBSession, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return run


def primary_session(db: DBSession, program_id: str) -> Session:
    session = db.exec(
        select(Session).where(Session.program_id == program_id).order_by(Session.index)
    ).first()
    if session is None:
        # Defensive: `create_program` always makes one.
        session = Session(program_id=program_id, index=0)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def guard_no_active_run(manager: RunManager, db: DBSession, program_id: str) -> None:
    """Refuse edits while the harness is reading the brief."""
    if manager.registry.active_for_program(program_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A run is in progress for this program.")
    active = db.exec(
        select(Run).where(Run.program_id == program_id, Run.status.in_(RunStatus.ACTIVE))
    ).first()
    if active is not None and manager.registry.get(active.id) is None:
        # Row says running but this process has no such run: it died with a
        # previous process. Reconcile rather than blocking the program forever.
        active.status = RunStatus.INTERRUPTED
        active.error = active.error or "Interrupted by a server restart."
        db.add(active)
        db.commit()


def load_brief(program: Program) -> dict:
    return parse_json(program.brief_json)


def store_brief(program: Program, brief: dict) -> None:
    program.brief_json = json.dumps(brief, ensure_ascii=False)


def parse_json(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def run_summary(run: Run, manager: RunManager | None = None) -> RunSummary:
    """A run's public shape, preferring live state over the persisted row.

    The row is only written when a run ends, so for an in-flight run the
    registry is the accurate source.
    """
    status_value, error, stats, model_name = run.status, run.error, parse_json(run.stats_json), run.model_name
    if manager is not None:
        state = manager.registry.get(run.id)
        if state is not None:
            status_value, error = state.status, state.error
            stats = state.public_stats()
            model_name = state.model_name or model_name
    return RunSummary(
        id=run.id,
        status=status_value,
        error=error,
        model_name=model_name,
        stats=stats,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def latest_run(db: DBSession, program_id: str) -> Run | None:
    return db.exec(
        select(Run).where(Run.program_id == program_id).order_by(Run.created_at.desc())
    ).first()


def program_summary(db: DBSession, program: Program, manager: RunManager | None = None) -> ProgramSummary:
    run = latest_run(db, program.id)
    return ProgramSummary(
        id=program.id,
        title=program.title,
        source=program.source,
        created_at=program.created_at,
        updated_at=program.updated_at,
        brief_committed_at=program.brief_committed_at,
        brief_preview=briefs.preview(load_brief(program)),
        latest_run=run_summary(run, manager) if run is not None else None,
    )


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        seq=message.seq,
        role=message.role,
        content=message.content,
        payload=parse_json(message.payload_json),
        created_at=message.created_at,
    )
