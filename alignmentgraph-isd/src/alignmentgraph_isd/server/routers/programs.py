"""Training programs and their design briefs."""
from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlmodel import Session as DBSession
from sqlmodel import select

from .. import artifacts, briefs
from ..db import get_session
from ..models import Message, Program, Run, Session, utcnow
from ..runner import RunManager
from ..schemas import (
    BriefResponse,
    BriefUpdate,
    ProgramCreate,
    ProgramDetail,
    ProgramSummary,
    ProgramUpdate,
)
from ..settings import Settings
from .deps import (
    get_app_settings,
    get_manager,
    guard_no_active_run,
    load_brief,
    load_program,
    message_out,
    primary_session,
    program_summary,
    run_summary,
    store_brief,
)

router = APIRouter(prefix="/programs", tags=["programs"])


@router.get("", response_model=list[ProgramSummary])
def list_programs(
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> list[ProgramSummary]:
    programs = db.exec(select(Program).order_by(Program.updated_at.desc())).all()
    return [program_summary(db, p, manager) for p in programs]


@router.post("", response_model=ProgramDetail, status_code=status.HTTP_201_CREATED)
def create_program(
    payload: ProgramCreate,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> ProgramDetail:
    program = Program(title=payload.title.strip() or "Untitled program")
    db.add(program)
    db.commit()
    db.refresh(program)

    # Every program owns exactly one session today. Created here so the rest of
    # the code can assume it exists.
    db.add(Session(program_id=program.id, index=0))
    db.commit()

    return _detail(db, program, manager)


@router.get("/{program_id}", response_model=ProgramDetail)
def get_program(
    program_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> ProgramDetail:
    return _detail(db, load_program(db, program_id), manager)


@router.patch("/{program_id}", response_model=ProgramSummary)
def rename_program(
    program_id: str,
    payload: ProgramUpdate,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> ProgramSummary:
    program = load_program(db, program_id)
    program.title = payload.title.strip()
    program.updated_at = utcnow()
    db.add(program)
    db.commit()
    db.refresh(program)
    return program_summary(db, program, manager)


@router.delete("/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_program(
    program_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    program = load_program(db, program_id)
    guard_no_active_run(manager, db, program_id)

    # Deleted child-first with a flush between each stage. The models declare
    # plain foreign-key columns and no ORM relationships, so nothing tells the
    # unit of work which order these have to go in; leaving it to infer that
    # trips the foreign-key constraint on the way out.
    sessions = db.exec(select(Session).where(Session.program_id == program_id)).all()
    for session in sessions:
        for message in db.exec(select(Message).where(Message.session_id == session.id)).all():
            db.delete(message)
    db.flush()
    for run in db.exec(select(Run).where(Run.program_id == program_id)).all():
        db.delete(run)
    db.flush()
    for session in sessions:
        db.delete(session)
    db.flush()
    db.delete(program)
    db.commit()

    shutil.rmtree(settings.programs_dir / program_id, ignore_errors=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{program_id}/brief", response_model=BriefResponse)
def replace_brief(
    program_id: str,
    payload: BriefUpdate,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> BriefResponse:
    program = load_program(db, program_id)
    guard_no_active_run(manager, db, program_id)
    try:
        brief, warnings = briefs.validate_brief(payload.brief)
    except briefs.BriefImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _store(db, program, brief, warnings)


@router.post("/{program_id}/brief/import", response_model=BriefResponse)
async def import_brief(
    program_id: str,
    file: UploadFile = File(...),
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> BriefResponse:
    """Load a benchmark scenario file as this program's brief.

    Accepts the benchmark's scenario shape directly (`scenario_id` becomes
    `id`), which is what makes a demo reproducible against the same inputs the
    experiments used.
    """
    program = load_program(db, program_id)
    guard_no_active_run(manager, db, program_id)

    if file.filename and not file.filename.lower().endswith(".json"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Expected a .json file.")

    raw = await file.read()
    if len(raw) > briefs.MAX_IMPORT_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File is larger than {briefs.MAX_IMPORT_BYTES // 1000} kB.",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Not valid JSON: {exc}") from exc

    try:
        brief, warnings = briefs.scenario_to_brief_dict(payload)
    except briefs.BriefImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    program.source = "import"
    if brief.get("title") and program.title == "Untitled program":
        program.title = brief["title"]
    return _store(db, program, brief, warnings)


@router.post("/{program_id}/brief/commit", response_model=BriefResponse)
def commit_brief(
    program_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> BriefResponse:
    """Settle the brief built through the conversation.

    A brief assembled turn by turn is a draft: it changes with every answer and
    is often half-formed. Committing marks the point where the designer says it
    is the brief — which is what the UI then shows as the program's design
    brief. An imported file is committed on arrival, since it arrives whole.
    """
    program = load_program(db, program_id)
    guard_no_active_run(manager, db, program_id)

    brief = load_brief(program)
    if not briefs.is_runnable(brief):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The design brief is still empty. Describe the program in the chat or import a scenario file.",
        )
    return _store(db, program, brief, [])


def _store(db: DBSession, program: Program, brief: dict, warnings: list[str]) -> BriefResponse:
    store_brief(program, brief)
    program.brief_committed_at = utcnow()
    program.updated_at = utcnow()
    db.add(program)
    db.commit()
    db.refresh(program)
    return BriefResponse(
        brief=brief,
        brief_preview=briefs.preview(brief),
        missing_fields=briefs.missing_core_fields(brief),
        warnings=warnings,
        brief_committed_at=program.brief_committed_at,
    )


def _detail(db: DBSession, program: Program, manager: RunManager) -> ProgramDetail:
    brief = load_brief(program)
    session = primary_session(db, program.id)
    messages = db.exec(
        select(Message).where(Message.session_id == session.id).order_by(Message.seq)
    ).all()
    runs = db.exec(
        select(Run).where(Run.program_id == program.id).order_by(Run.created_at.desc())
    ).all()
    return ProgramDetail(
        program=program_summary(db, program, manager),
        brief=brief,
        brief_preview=briefs.preview(brief),
        messages=[message_out(m) for m in messages],
        missing_fields=briefs.missing_core_fields(brief),
        runs=[run_summary(r, manager) for r in runs],
    )
