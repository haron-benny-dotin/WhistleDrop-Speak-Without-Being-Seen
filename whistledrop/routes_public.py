import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request

from . import security, store
from .db import get_db
from .errors import ApiError
from .schemas import (PublicUpdate, ReportCreate, ReportCreated, ReportTracking,
                      Status)

router = APIRouter(prefix="/reports", tags=["Reporter (anonymous)"])

_MAX_CODE_ATTEMPTS = 5


@router.post("", status_code=201, response_model=ReportCreated,
             summary="Submit a report anonymously")
def submit_report(body: ReportCreate, request: Request,
                  conn: sqlite3.Connection = Depends(get_db)):
    secret = request.app.state.settings.case_code_secret
    # only the date, exact time could help identify who submitted it
    submitted_on = datetime.now(timezone.utc).date().isoformat()

    for _ in range(_MAX_CODE_ATTEMPTS):
        case_code = security.generate_case_code()
        case_hash = security.hash_case_code(security.normalize_case_code(case_code), secret)
        try:
            store.insert_report(conn, report_id=str(uuid.uuid4()), case_hash=case_hash,
                                category=body.category.value, description=body.description,
                                evidence_url=body.evidence_url, submitted_on=submitted_on)
            break
        except sqlite3.IntegrityError:
            continue
    else:
        raise ApiError(503, "try_again", "Could not create the report. Please try again.")

    return ReportCreated(
        case_code=case_code,
        status=Status.SUBMITTED,
        submitted_on=submitted_on,
        message=("Save this case code now. It is the only way to check your report, "
                 "and it cannot be recovered if lost."),
    )


@router.get("/track", response_model=ReportTracking,
            summary="Check the status of your report using its case code")
def track_report(request: Request,
                 x_case_code: Optional[str] = Header(
                     default=None, alias="X-Case-Code",
                     description="Your case code, e.g. WD-7KQ2-M9XT-4HPA"),
                 conn: sqlite3.Connection = Depends(get_db)):
    # code is sent in a header, not the url, because urls get logged
    if not x_case_code:
        raise ApiError(400, "missing_case_code", "Send your case code in the X-Case-Code header.")

    normalized = security.normalize_case_code(x_case_code)
    if normalized is None:
        raise ApiError(400, "invalid_case_code",
                       "That does not look like a case code (expected WD-XXXX-XXXX-XXXX).")

    case_hash = security.hash_case_code(normalized, request.app.state.settings.case_code_secret)
    report = store.report_by_case_hash(conn, case_hash)
    if report is None:
        raise ApiError(404, "case_not_found", "No report matches this case code.")

    updates = store.updates_for_report(conn, report["id"], public_only=True)
    return ReportTracking(
        category=report["category"],
        status=report["status"],
        is_closed=bool(report["is_closed"]),
        submitted_on=report["submitted_on"],
        # no moderator name for the reporter
        updates=[PublicUpdate(status=u["to_status"], note=u["note"], created_at=u["created_at"])
                 for u in updates],
    )
