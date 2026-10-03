import sqlite3

from whistledrop import security


def _all_db_text(path):
    conn = sqlite3.connect(path)
    text = []
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        for row in conn.execute(f"SELECT * FROM {table}"):
            text.extend(str(v) for v in row)
    conn.close()
    return " ".join(text)


def test_case_code_never_stored_in_plain_text(client, settings, submit):
    code = submit()
    db_text = _all_db_text(settings.database_path)
    assert code not in db_text
    assert security.normalize_case_code(code) not in db_text


def test_no_reporter_metadata_columns(settings, client):
    conn = sqlite3.connect(settings.database_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(reports)")}
    conn.close()
    assert columns == {"id", "case_hash", "category", "description", "evidence_url",
                       "status", "is_closed", "submitted_on"}
    for forbidden in ("ip", "ip_address", "user_agent", "email", "name", "created_at"):
        assert forbidden not in columns


def test_moderator_views_never_contain_case_data(client, auth, submit):
    code = submit()
    listing = client.get("/moderator/reports", headers=auth)
    rid = listing.json()["items"][0]["id"]
    detail = client.get(f"/moderator/reports/{rid}", headers=auth)
    for res in (listing, detail):
        assert code not in res.text
        assert "case_hash" not in res.text
        assert "case_code" not in res.text


def test_case_hash_depends_on_server_secret():
    code = security.normalize_case_code("WD-ABCD-EFGH-JKMN")
    assert security.hash_case_code(code, b"one") != security.hash_case_code(code, b"two")


def test_passwords_and_tokens_are_hashed(client, settings, auth):
    db_text = _all_db_text(settings.database_path)
    token = auth["Authorization"].split()[1]
    assert token not in db_text
    assert "correct-horse-battery" not in db_text


def test_password_hashing_roundtrip():
    stored = security.hash_password("s3cret-pass")
    assert security.verify_password("s3cret-pass", stored)
    assert not security.verify_password("wrong", stored)
    assert not security.verify_password("x", "garbage")
