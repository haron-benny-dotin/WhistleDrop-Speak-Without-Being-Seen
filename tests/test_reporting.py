import re

import pytest

CODE_PATTERN = re.compile(r"^WD-[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}$")


def test_submit_returns_case_code(client):
    res = client.post("/reports", json={
        "category": "corruption",
        "description": "Purchase orders above 50k are being split to avoid approval.",
        "evidence_url": "https://example.com/po-list.pdf",
    })
    assert res.status_code == 201
    body = res.json()
    assert CODE_PATTERN.match(body["case_code"])
    assert body["status"] == "SUBMITTED"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", body["submitted_on"])


def test_case_codes_are_unique(submit):
    codes = {submit() for _ in range(50)}
    assert len(codes) == 50


@pytest.mark.parametrize("payload, field", [
    ({"category": "gossip", "description": "x" * 30}, "category"),
    ({"category": "security", "description": "too short"}, "description"),
    ({"category": "security", "description": "   " + "a" * 10 + "   "}, "description"),
    ({"category": "security", "description": "x" * 5001}, "description"),
    ({"category": "security", "description": "x" * 30, "evidence_url": "javascript:alert(1)"}, "evidence_url"),
    ({"category": "security", "description": "x" * 30, "evidence_url": "not a url"}, "evidence_url"),
    ({"description": "x" * 30}, "category"),
])
def test_invalid_submissions_rejected(client, payload, field):
    res = client.post("/reports", json=payload)
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert any(d["field"] == field for d in error["details"])


def test_identity_fields_are_refused(client):
    res = client.post("/reports", json={
        "category": "harassment", "description": "x" * 30, "email": "me@company.com"})
    assert res.status_code == 422


def test_errors_do_not_echo_submitted_text(client):
    res = client.post("/reports", json={"category": "nope", "description": "SECRET-DETAIL-12345"})
    assert "SECRET-DETAIL-12345" not in res.text


def test_track_with_code(client, submit):
    code = submit()
    res = client.get("/reports/track", headers={"X-Case-Code": code})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "SUBMITTED"
    assert body["updates"] == []
    assert body["is_closed"] is False


def test_track_accepts_relaxed_formatting(client, submit):
    code = submit()
    messy = code.lower().replace("-", " ")
    assert client.get("/reports/track", headers={"X-Case-Code": messy}).status_code == 200
    bare = code.replace("WD-", "").replace("-", "")
    assert client.get("/reports/track", headers={"X-Case-Code": bare}).status_code == 200


def test_track_missing_header(client):
    res = client.get("/reports/track")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "missing_case_code"


def test_track_malformed_code(client):
    res = client.get("/reports/track", headers={"X-Case-Code": "hello"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_case_code"


def test_track_unknown_code(client):
    res = client.get("/reports/track", headers={"X-Case-Code": "WD-2222-3333-4444"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "case_not_found"


def test_privacy_headers_present(client):
    res = client.get("/health")
    assert res.headers["Cache-Control"] == "no-store"
    assert res.headers["Referrer-Policy"] == "no-referrer"


def test_wrong_method_and_unknown_route(client):
    assert client.delete("/reports").status_code == 405
    res = client.get("/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"
