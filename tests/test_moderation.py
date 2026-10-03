import sqlite3

from conftest import MOD_PASS, MOD_USER


def _first_report_id(client, auth):
    return client.get("/moderator/reports", headers=auth).json()["items"][0]["id"]



def test_moderator_routes_need_token(client):
    for method, path in [("get", "/moderator/reports"),
                         ("get", "/moderator/reports/abc"),
                         ("patch", "/moderator/reports/abc/status"),
                         ("post", "/moderator/logout")]:
        res = getattr(client, method)(path)
        assert res.status_code == 401, path
        assert res.headers["WWW-Authenticate"] == "Bearer"


def test_bad_token_rejected(client):
    res = client.get("/moderator/reports", headers={"Authorization": "Bearer made-up-token"})
    assert res.status_code == 401


def test_wrong_password_and_unknown_user_look_the_same(client):
    a = client.post("/moderator/login", json={"username": MOD_USER, "password": "wrong"})
    b = client.post("/moderator/login", json={"username": "nobody", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        client.post("/moderator/login", json={"username": MOD_USER, "password": "wrong"})
    res = client.post("/moderator/login", json={"username": MOD_USER, "password": MOD_PASS})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "account_locked"


def test_logout_invalidates_token(client, auth):
    assert client.post("/moderator/logout", headers=auth).status_code == 204
    assert client.get("/moderator/reports", headers=auth).status_code == 401



def test_list_and_filter(client, auth, submit):
    submit("security", "Firewall rules allow all inbound traffic on port 22.")
    submit("harassment", "A team lead keeps making comments about colleagues' appearance.")
    submit("security", "Old employee accounts are never disabled after people leave.")

    all_reports = client.get("/moderator/reports", headers=auth).json()
    assert all_reports["total"] == 3

    security_only = client.get("/moderator/reports?category=security", headers=auth).json()
    assert security_only["total"] == 2
    assert all(r["category"] == "security" for r in security_only["items"])

    searched = client.get("/moderator/reports?q=firewall", headers=auth).json()
    assert searched["total"] == 1

    paged = client.get("/moderator/reports?limit=1&offset=1", headers=auth).json()
    assert len(paged["items"]) == 1 and paged["total"] == 3


def test_search_treats_wildcards_literally(client, auth, submit):
    submit("technical", "Nothing special in this particular report text.")
    res = client.get("/moderator/reports?q=%25", headers=auth).json()
    assert res["total"] == 0


def test_invalid_filter_values(client, auth):
    assert client.get("/moderator/reports?status=DONE", headers=auth).status_code == 422
    assert client.get("/moderator/reports?limit=0", headers=auth).status_code == 422


def test_unknown_report_id(client, auth):
    assert client.get("/moderator/reports/not-a-uuid", headers=auth).status_code == 404
    res = client.get("/moderator/reports/00000000-0000-0000-0000-000000000000", headers=auth)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "report_not_found"



def test_full_workflow_visible_to_reporter(client, auth, submit):
    code = submit()
    rid = _first_report_id(client, auth)

    res = client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                       json={"status": "UNDER_REVIEW", "note": "We are looking into this."})
    assert res.status_code == 200
    assert res.json()["status"] == "UNDER_REVIEW"

    client.post(f"/moderator/reports/{rid}/updates", headers=auth,
                json={"note": "Spoke to facilities team.", "visible_to_reporter": False})

    res = client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                       json={"status": "RESOLVED", "note": "A lock has been installed."})
    assert res.json()["status"] == "RESOLVED"
    assert len(res.json()["updates"]) == 3

    tracked = client.get("/reports/track", headers={"X-Case-Code": code}).json()
    assert tracked["status"] == "RESOLVED"
    notes = [u["note"] for u in tracked["updates"]]
    assert notes == ["We are looking into this.", "A lock has been installed."]  # internal note hidden
    assert "moderator" not in tracked["updates"][0]


def test_invalid_transitions_rejected(client, auth, submit):
    submit()
    rid = _first_report_id(client, auth)

    res = client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                       json={"status": "RESOLVED", "note": "skip ahead"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "invalid_transition"

    res = client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                       json={"status": "SUBMITTED", "note": "same status"})
    assert res.status_code == 409

    client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                 json={"status": "UNDER_REVIEW", "note": "ok"})
    client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                 json={"status": "DISMISSED", "note": "Not enough information."})
    res = client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                       json={"status": "UNDER_REVIEW", "note": "reopen?"})
    assert res.status_code == 409  # DISMISSED is final


def test_status_change_needs_a_note(client, auth, submit):
    submit()
    rid = _first_report_id(client, auth)
    res = client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                       json={"status": "UNDER_REVIEW", "note": "   "})
    assert res.status_code == 422


def test_concurrent_change_does_not_overwrite(client, auth, settings, submit):
    from whistledrop import store
    submit()
    rid = _first_report_id(client, auth)
    conn = sqlite3.connect(settings.database_path)
    conn.execute("UPDATE reports SET status = 'UNDER_REVIEW' WHERE id = ?", (rid,))
    conn.commit()
    conn.close()

    from whistledrop.db import connect
    c = connect(settings.database_path)
    ok = store.change_status(c, report_id=rid, expected_status="SUBMITTED",
                             new_status="UNDER_REVIEW", moderator_id=1, note="late", visible=True)
    c.close()
    assert ok is False



def test_close_case(client, auth, submit):
    code = submit()
    rid = _first_report_id(client, auth)

    res = client.post(f"/moderator/reports/{rid}/close", headers=auth)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "not_final"

    client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                 json={"status": "UNDER_REVIEW", "note": "Checking."})
    client.patch(f"/moderator/reports/{rid}/status", headers=auth,
                 json={"status": "RESOLVED", "note": "Fixed."})
    res = client.post(f"/moderator/reports/{rid}/close", headers=auth)
    assert res.status_code == 200
    assert res.json()["is_closed"] is True

    res = client.post(f"/moderator/reports/{rid}/updates", headers=auth, json={"note": "more"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "case_closed"

    assert client.get("/reports/track", headers={"X-Case-Code": code}).json()["is_closed"] is True
