"""The planning conversation.

Synchronous on purpose: a planning turn is a few seconds, and streaming it would
add a second live-transport story alongside the run stream for very little gain.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session as DBSession
from sqlmodel import select

from .. import briefs, planner
from ..db import get_session
from ..models import Message, utcnow
from ..runner import RunManager
from ..schemas import MessageCreate, MessageOut, PlanTurnResponse
from .deps import (
    get_manager,
    guard_no_active_run,
    load_brief,
    load_program,
    message_out,
    primary_session,
    store_brief,
)

router = APIRouter(prefix="/programs/{program_id}", tags=["planning"])


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    program_id: str,
    db: DBSession = Depends(get_session),
) -> list[MessageOut]:
    load_program(db, program_id)
    session = primary_session(db, program_id)
    messages = db.exec(
        select(Message).where(Message.session_id == session.id).order_by(Message.seq)
    ).all()
    return [message_out(m) for m in messages]


@router.post("/messages", response_model=PlanTurnResponse)
def post_message(
    program_id: str,
    payload: MessageCreate,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> PlanTurnResponse:
    program = load_program(db, program_id)
    guard_no_active_run(manager, db, program_id)

    session = primary_session(db, program_id)
    history = db.exec(
        select(Message).where(Message.session_id == session.id).order_by(Message.seq)
    ).all()
    brief = load_brief(program)

    try:
        outcome = planner.plan_turn(
            [{"role": m.role, "content": m.content} for m in history],
            brief,
            payload.content,
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    next_seq = (history[-1].seq if history else 0) + 1
    user_message = Message(session_id=session.id, seq=next_seq, role="user", content=payload.content)
    assistant_message = Message(
        session_id=session.id,
        seq=next_seq + 1,
        role="assistant",
        content=outcome["reply"],
        payload_json=json.dumps(
            {
                "brief_patch": outcome["brief_patch"],
                "missing_fields": outcome["missing_fields"],
                "ready": outcome["ready"],
                "warnings": outcome["warnings"],
            },
            ensure_ascii=False,
        ),
    )
    db.add(user_message)
    db.add(assistant_message)

    store_brief(program, outcome["brief"])
    program.updated_at = utcnow()
    if outcome["brief_patch"]:
        # The brief moved, so whatever was committed no longer describes it.
        # Back to a draft until the designer commits again.
        program.brief_committed_at = None
    if program.title == "Untitled program" and outcome["brief"].get("title"):
        program.title = outcome["brief"]["title"]
    db.add(program)
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)

    return PlanTurnResponse(
        user_message=message_out(user_message),
        assistant_message=message_out(assistant_message),
        brief=outcome["brief"],
        brief_preview=briefs.preview(outcome["brief"]),
        missing_fields=outcome["missing_fields"],
        ready=outcome["ready"],
        warnings=outcome["warnings"],
        brief_committed_at=program.brief_committed_at,
    )
