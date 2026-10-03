import sqlite3
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import security, store
from .db import get_db
from .errors import ApiError
from .schemas import (ALLOWED_TRANSITIONS, FINAL_STATUSES, Category, LoginRequest,
                      LoginResponse, ModeratorUpdate, NoteCreate, ReportDetail, ReportList,
                      ReportSummary, Status, StatusChange)

router = APIRouter(prefix="/moderator", tags=["Moderator"])

_bearer = HTTPBearer(auto_error=False, description="Token from POST /moderator/login")



def _unauthorized(message: str) -> ApiError:
    return ApiError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def current_moderator(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
                      conn: sqlite3.Connection = Depends(get_db)) -> sqlite3.Row:
    if creds is None:
        raise _unauthorized("Log in first and send the token as 'Authorization: Bearer <token>'.")
    moderator = store.moderator_for_token(conn, creds.credentials)
    if moderator is None:
        raise _unauthorized("Your session is invalid or has expired. Please log in again.")
    return moderator


def _parse_report_id(report_id: str) -> str:
    try:
        return str(uuid.UUID(report_id))
    except ValueError:
        raise ApiError(404, "report_not_found", "No report with this id.")


def _load_report(conn: sqlite3.Connection, report_id: str) -> sqlite3.Row:
    report = store.report_by_id(conn, _parse_report_id(report_id))
    if report is None:
        raise ApiError(404, "report_not_found", "No report with this id.")
    return report


def _detail(conn: sqlite3.Connection, report: sqlite3.Row) -> ReportDetail:
    # case code / hash are never included here
    updates = store.updates_for_report(conn, report["id"], public_only=False)
    return ReportDetail(
        id=report["id"],
        category=report["category"],
        status=report["status"],
        is_closed=bool(report["is_closed"]),
        submitted_on=report["submitted_on"],
        description=report["description"],
        evidence_url=report["evidence_url"],
        updates=[ModeratorUpdate(from_status=u["from_status"], to_status=u["to_status"],
                                 note=u["note"], visible_to_reporter=bool(u["visible_to_reporter"]),
                                 moderator=u["moderator"], created_at=u["created_at"])
                 for u in updates],
    )



@router.post("/login", response_model=LoginResponse, summary="Log in and get a bearer token")
def login(body: LoginRequest, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    moderator = store.moderator_by_username(conn, body.username)
    if moderator is None:
        security.burn_password_check(body.password)
        raise _unauthorized("Wrong username or password.")

    locked_until = moderator["locked_until"]
    if locked_until and locked_until > security.now_iso():
        raise ApiError(429, "account_locked",
                       "Too many failed attempts. Try again in a few minutes.")

    if not security.verify_password(body.password, moderator["password_hash"]):
        store.record_failed_login(conn, moderator["id"])
        raise _unauthorized("Wrong username or password.")

    store.reset_failed_logins(conn, moderator["id"])
    token, expires_at = store.create_session(
        conn, moderator["id"], request.app.state.settings.session_ttl_minutes)
    return LoginResponse(access_token=token, expires_at=expires_at)


@router.post("/logout", status_code=204, summary="End the current session")
def logout(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
           _: sqlite3.Row = Depends(current_moderator),
           conn: sqlite3.Connection = Depends(get_db)):
    store.delete_session(conn, creds.credentials)
    return Response(status_code=204)


@router.get("/reports", response_model=ReportList, summary="List and filter reports")
def list_reports(status: Optional[Status] = None,
                 category: Optional[Category] = None,
                 is_closed: Optional[bool] = None,
                 q: Optional[str] = Query(default=None, max_length=100,
                                          description="Search text inside descriptions"),
                 limit: int = Query(default=20, ge=1, le=100),
                 offset: int = Query(default=0, ge=0),
                 _: sqlite3.Row = Depends(current_moderator),
                 conn: sqlite3.Connection = Depends(get_db)):
    total, rows = store.list_reports(
        conn, status=status.value if status else None,
        category=category.value if category else None,
        is_closed=is_closed, search=q.strip() if q and q.strip() else None,
        limit=limit, offset=offset)
    items = [ReportSummary(
        id=r["id"], category=r["category"], status=r["status"],
        is_closed=bool(r["is_closed"]), submitted_on=r["submitted_on"],
        description_preview=(r["description"][:120] + "...") if len(r["description"]) > 120
        else r["description"],
    ) for r in rows]
    return ReportList(total=total, limit=limit, offset=offset, items=items)


@router.get("/reports/{report_id}", response_model=ReportDetail,
            summary="View one report with its full history")
def get_report(report_id: str, _: sqlite3.Row = Depends(current_moderator),
               conn: sqlite3.Connection = Depends(get_db)):
    return _detail(conn, _load_report(conn, report_id))


@router.patch("/reports/{report_id}/status", response_model=ReportDetail,
              summary="Move a report to its next status (with a short update)")
def update_status(report_id: str, body: StatusChange,
                  moderator: sqlite3.Row = Depends(current_moderator),
                  conn: sqlite3.Connection = Depends(get_db)):
    report = _load_report(conn, report_id)
    if report["is_closed"]:
        raise ApiError(409, "case_closed", "This case is permanently closed and cannot change.")

    current = Status(report["status"])
    if body.status not in ALLOWED_TRANSITIONS[current]:
        allowed = ", ".join(s.value for s in ALLOWED_TRANSITIONS[current]) or "none (final status)"
        raise ApiError(409, "invalid_transition",
                       f"Cannot move from {current.value} to {body.status.value}. "
                       f"Allowed next: {allowed}.")

    changed = store.change_status(conn, report_id=report["id"], expected_status=current.value,
                                  new_status=body.status.value, moderator_id=moderator["id"],
                                  note=body.note, visible=body.visible_to_reporter)
    if not changed:
        raise ApiError(409, "status_changed_meanwhile",
                       "Another moderator changed this report just now. Reload and try again.")
    return _detail(conn, store.report_by_id(conn, report["id"]))


@router.post("/reports/{report_id}/updates", status_code=201, response_model=ReportDetail,
             summary="Add a note without changing the status")
def add_update(report_id: str, body: NoteCreate,
               moderator: sqlite3.Row = Depends(current_moderator),
               conn: sqlite3.Connection = Depends(get_db)):
    report = _load_report(conn, report_id)
    if report["is_closed"]:
        raise ApiError(409, "case_closed", "This case is permanently closed and cannot change.")
    store.add_note(conn, report_id=report["id"], moderator_id=moderator["id"],
                   note=body.note, visible=body.visible_to_reporter)
    return _detail(conn, store.report_by_id(conn, report["id"]))


@router.post("/reports/{report_id}/close", response_model=ReportDetail,
             summary="Permanently close a RESOLVED or DISMISSED case")
def close_case(report_id: str, _: sqlite3.Row = Depends(current_moderator),
               conn: sqlite3.Connection = Depends(get_db)):
    report = _load_report(conn, report_id)
    if report["is_closed"]:
        raise ApiError(409, "case_closed", "This case is already closed.")
    if Status(report["status"]) not in FINAL_STATUSES:
        raise ApiError(409, "not_final",
                       "Only RESOLVED or DISMISSED cases can be closed.")
    if not store.close_report(conn, report["id"]):
        raise ApiError(409, "status_changed_meanwhile",
                       "This report changed just now. Reload and try again.")
    return _detail(conn, store.report_by_id(conn, report["id"]))
