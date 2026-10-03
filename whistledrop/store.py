import sqlite3
from typing import List, Optional, Tuple

from . import security

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15




def insert_report(conn: sqlite3.Connection, *, report_id: str, case_hash: str, category: str,
                  description: str, evidence_url: Optional[str], submitted_on: str) -> None:
    conn.execute(
        """INSERT INTO reports (id, case_hash, category, description, evidence_url,
                                status, is_closed, submitted_on)
           VALUES (?, ?, ?, ?, ?, 'SUBMITTED', 0, ?)""",
        (report_id, case_hash, category, description, evidence_url, submitted_on),
    )
    conn.commit()


def report_by_case_hash(conn: sqlite3.Connection, case_hash: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM reports WHERE case_hash = ?", (case_hash,)).fetchone()


def report_by_id(conn: sqlite3.Connection, report_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_reports(conn: sqlite3.Connection, *, status: Optional[str], category: Optional[str],
                 is_closed: Optional[bool], search: Optional[str],
                 limit: int, offset: int) -> Tuple[int, List[sqlite3.Row]]:
    where, params = [], []
    if status:
        where.append("status = ?")
        params.append(status)
    if category:
        where.append("category = ?")
        params.append(category)
    if is_closed is not None:
        where.append("is_closed = ?")
        params.append(1 if is_closed else 0)
    if search:
        where.append("description LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(search)}%")
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = conn.execute(f"SELECT COUNT(*) FROM reports {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM reports {clause} ORDER BY rowid DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return total, rows


def updates_for_report(conn: sqlite3.Connection, report_id: str,
                       public_only: bool) -> List[sqlite3.Row]:
    sql = """SELECT u.*, m.username AS moderator
             FROM report_updates u JOIN moderators m ON m.id = u.moderator_id
             WHERE u.report_id = ?"""
    if public_only:
        sql += " AND u.visible_to_reporter = 1"
    sql += " ORDER BY u.id ASC"
    return conn.execute(sql, (report_id,)).fetchall()


def change_status(conn: sqlite3.Connection, *, report_id: str, expected_status: str,
                  new_status: str, moderator_id: int, note: str, visible: bool) -> bool:
    # only updates if the status is still what we checked, so if two moderators
    # change it at the same time the second one fails instead of overwriting
    try:
        cur = conn.execute(
            "UPDATE reports SET status = ? WHERE id = ? AND status = ? AND is_closed = 0",
            (new_status, report_id, expected_status),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return False
        conn.execute(
            """INSERT INTO report_updates (report_id, moderator_id, from_status, to_status,
                                           note, visible_to_reporter, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (report_id, moderator_id, expected_status, new_status, note,
             1 if visible else 0, security.now_iso()),
        )
        conn.commit()
        return True
    except sqlite3.Error:
        conn.rollback()
        raise


def add_note(conn: sqlite3.Connection, *, report_id: str, moderator_id: int,
             note: str, visible: bool) -> None:
    conn.execute(
        """INSERT INTO report_updates (report_id, moderator_id, from_status, to_status,
                                       note, visible_to_reporter, created_at)
           VALUES (?, ?, NULL, NULL, ?, ?, ?)""",
        (report_id, moderator_id, note, 1 if visible else 0, security.now_iso()),
    )
    conn.commit()


def close_report(conn: sqlite3.Connection, report_id: str) -> bool:
    cur = conn.execute(
        """UPDATE reports SET is_closed = 1
           WHERE id = ? AND is_closed = 0 AND status IN ('RESOLVED', 'DISMISSED')""",
        (report_id,),
    )
    conn.commit()
    return cur.rowcount == 1




def create_moderator(conn: sqlite3.Connection, username: str, password: str) -> int:
    cur = conn.execute(
        "INSERT INTO moderators (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, security.hash_password(password), security.now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def moderator_by_username(conn: sqlite3.Connection, username: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM moderators WHERE username = ?", (username,)).fetchone()


def record_failed_login(conn: sqlite3.Connection, moderator_id: int) -> None:
    row = conn.execute("SELECT failed_attempts FROM moderators WHERE id = ?",
                       (moderator_id,)).fetchone()
    attempts = row["failed_attempts"] + 1
    locked_until = None
    if attempts >= MAX_FAILED_LOGINS:
        locked_until = security.iso_after(LOCKOUT_MINUTES)
        attempts = 0
    conn.execute("UPDATE moderators SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                 (attempts, locked_until, moderator_id))
    conn.commit()


def reset_failed_logins(conn: sqlite3.Connection, moderator_id: int) -> None:
    conn.execute("UPDATE moderators SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
                 (moderator_id,))
    conn.commit()




def create_session(conn: sqlite3.Connection, moderator_id: int, ttl_minutes: int) -> Tuple[str, str]:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (security.now_iso(),))
    token = security.new_session_token()
    expires_at = security.iso_after(ttl_minutes)
    conn.execute("INSERT INTO sessions (token_hash, moderator_id, expires_at) VALUES (?, ?, ?)",
                 (security.hash_token(token), moderator_id, expires_at))
    conn.commit()
    return token, expires_at


def moderator_for_token(conn: sqlite3.Connection, token: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        """SELECT m.* FROM sessions s JOIN moderators m ON m.id = s.moderator_id
           WHERE s.token_hash = ? AND s.expires_at > ?""",
        (security.hash_token(token), security.now_iso()),
    ).fetchone()


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (security.hash_token(token),))
    conn.commit()
