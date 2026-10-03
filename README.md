# WhistleDrop— Speak Without Being Seen

WhistleDrop is a backend setup for an organization where people in that organization can report or complaint a problem anonymously with out anybody knowing who reported it. They dont need a account or loging or any other authentication so report something.After submitting they will get a case code which used to check the ststus of report later. Moderators can review the reports and update them. but they cannot find who sent it 

I built it with Python (FastAPI) and SQLite.

i used some ai tools to structure this README file. Hope that will excluded from plagiarism.


## Setup instructions

Requires Python 3.10 or newer.

```bash
python -m venv venv
source venv/bin/activate            
pip install -r requirements.txt

python create_moderator.py alice

python server.py
```

Open **http://localhost:8000/docs** for interactive Swagger documentation.
To use moderator endpoints there: call `POST /moderator/login`, copy `access_token`, click **Authorize** and paste it.

---

## API endpoints

### Reporter (no login)

| `POST` | `/reports` | Submit a report. Returns the case code **once**. | `201` |
| `GET` | `/reports/track` | Check status and public updates. Case code goes in the `X-Case-Code` header. | `200` |

### Moderator (Bearer token required, except login)

| `POST` | `/moderator/login` | Exchange username and password for a token. | `200` |
| `POST` | `/moderator/logout` | Invalidate the current token. | `204` |
| `GET` | `/moderator/reports` | List reports. Filters: `status`, `category`, `is_closed`, `q` (text search), `limit`, `offset`. | `200` |
| `GET` | `/moderator/reports/{id}` | Full report with complete update history. | `200` |
| `PATCH` | `/moderator/reports/{id}/status` | Move to the next status, with a short note. | `200` |
| `POST` | `/moderator/reports/{id}/updates` | Add a note without changing status (public or internal). | `201` |
| `POST` | `/moderator/reports/{id}/close` | Permanently lock a `RESOLVED` or `DISMISSED` case. | `200` |

### Other

| `GET` | `/health` | Liveness check. |
| `GET` | `/docs` | Swagger UI. `/openapi.json` gives the raw OpenAPI spec. |

**Categories:** `security`, `harassment`, `corruption`, `technical`, `other`

**Report fields:** `category` (required), `description` (required, 20–5000 characters), `evidence_url` (optional, must be an `http://` or `https://` link).

---

## Example requests and responses

These are real responses captured from a running server.

### 1. Submit a report

```bash
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{"category":"security",
       "description":"The shared admin password for the billing server is written on a sticky note in room 204.",
       "evidence_url":"https://example.com/photo.jpg"}'
```

`201 Created`
```json
{
  "case_code": "WD-DA8V-DUN9-SJZG",
  "status": "SUBMITTED",
  "submitted_on": "2026-10-03",
  "message": "Save this case code now. It is the only way to check your report, and it cannot be recovered if lost."
}
```

### 2. Invalid submission

```bash
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{"category":"gossip","description":"short"}'
```

`422 Unprocessable Entity`
```json
{
  "error": {
    "code": "validation_error",
    "message": "The request data is invalid.",
    "details": [
      {"location": "body", "field": "category", "message": "Input should be 'security', 'harassment', 'corruption', 'technical' or 'other'"},
      {"location": "body", "field": "description", "message": "Value error, description must be at least 20 characters"}
    ]
  }
}
```

### 3. Moderator login

```bash
curl -X POST http://localhost:8000/moderator/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"strong-password-123"}'
```

`200 OK`
```json
{
  "access_token": "kIEVuWBnUt6qo8M1zYAoVskVROrH2faO_WXjZU7epPE",
  "token_type": "bearer",
  "expires_at": "2026-10-03T19:02:29Z"
}
```

### 4. List reports with a filter

```bash
curl "http://localhost:8000/moderator/reports?status=SUBMITTED" \
  -H "Authorization: Bearer <token>"
```

`200 OK`
```json
{
  "total": 1, "limit": 20, "offset": 0,
  "items": [{
    "id": "a63b9cb4-a188-4016-98d8-be3bef99ae6a",
    "category": "security",
    "status": "SUBMITTED",
    "is_closed": false,
    "submitted_on": "2026-10-03",
    "description_preview": "The shared admin password for the billing server is written on a sticky note in room 204."
  }]
}
```

### 5. Invalid status change

```bash
curl -X PATCH http://localhost:8000/moderator/reports/a63b9cb4-a188-4016-98d8-be3bef99ae6a/status \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"status":"RESOLVED","note":"Done"}'
```

`409 Conflict`
```json
{"error": {"code": "invalid_transition", "message": "Cannot move from SUBMITTED to RESOLVED. Allowed next: UNDER_REVIEW."}}
```

### 6. Valid status change, internal note, resolve

```bash
curl -X PATCH .../reports/<id>/status -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"status":"UNDER_REVIEW","note":"Thanks, we are looking into this."}'

curl -X POST .../reports/<id>/updates -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"note":"Asked IT to rotate the password.","visible_to_reporter":false}'

curl -X PATCH .../reports/<id>/status -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"status":"RESOLVED","note":"The password has been changed and the note removed."}'
```

The moderator sees all three entries, including who made each one:
```json
{
  "id": "a63b9cb4-a188-4016-98d8-be3bef99ae6a",
  "status": "RESOLVED",
  "updates": [
    {"from_status": "SUBMITTED", "to_status": "UNDER_REVIEW", "note": "Thanks, we are looking into this.", "visible_to_reporter": true, "moderator": "alice", "created_at": "2026-10-03T17:02:29Z"},
    {"from_status": null, "to_status": null, "note": "Asked IT to rotate the password.", "visible_to_reporter": false, "moderator": "alice", "created_at": "2026-10-03T17:02:29Z"},
    {"from_status": "UNDER_REVIEW", "to_status": "RESOLVED", "note": "The password has been changed and the note removed.", "visible_to_reporter": true, "moderator": "alice", "created_at": "2026-10-03T17:02:29Z"}
  ]
}
```
(some fields shortened)

### 7. Reporter tracks the case

```bash
curl http://localhost:8000/reports/track -H "X-Case-Code: WD-DA8V-DUN9-SJZG"
```

`200 OK` — the internal note and the moderator's name are not included:
```json
{
  "category": "security",
  "status": "RESOLVED",
  "is_closed": false,
  "submitted_on": "2026-10-03",
  "updates": [
    {"status": "UNDER_REVIEW", "note": "Thanks, we are looking into this.", "created_at": "2026-10-03T17:02:29Z"},
    {"status": "RESOLVED", "note": "The password has been changed and the note removed.", "created_at": "2026-10-03T17:02:29Z"}
  ]
}
```

The code is accepted in relaxed forms too: `wd-da8v-dun9-sjzg`, `DA8V DUN9 SJZG`.

Unknown code → `404 {"error":{"code":"case_not_found",...}}`
Malformed code → `400 {"error":{"code":"invalid_case_code",...}}`

### 8. No token

```
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"error":{"code":"unauthorized","message":"Log in first and send the token as 'Authorization: Bearer <token>'."}}
```

---

## How anonymity is maintained

There is no login for reporters, so there is no user ID to connect to a report.
I don't save IP addresses, and I turned off the server's request log because it saves IPs.
I only save the date of a report, not the time. An exact time could show who was at their computer then.
I don't save the case code itself. I save a hash of it, so even if the database leaks, nobody can see the codes.
The case code is sent in a header instead of the URL, because URLs get saved in logs.
If someone sends extra fields like email or name, the API rejects the request.


## Important assumptions and design decisions 

FastAPI: it validates input automatically and gives Swagger docs for free, so it's easy to test without a frontend.
SQLite: no setup needed, it's just a file. All SQL is in store.py, so it would be easy to move to PostgreSQL later.
Status flow: I kept the exact flow from the task (SUBMITTED > UNDER_REVIEW > RESOLVED/DISMISSED). Wrong moves return 409 because the request conflicts with the report's current state.
Two moderators at once: the status only changes if it's still the same as when we checked, so one moderator can't overwrite another's change.
Moderator login: I used random tokens stored as hashes instead of JWT, because then logout really works.
Moderators are created from the command line, not through the API, because a public "create moderator" endpoint would be a security risk.


## Deployment

This repository includes `render.yaml` for [Render](https://render.com):

---

## Project structure

```
whistledrop/
├── server.py               
├── create_moderator.py    
├── requirements.txt
├── render.yaml             
├── whistledrop/
│   ├── main.py           
│   ├── config.py           
│   ├── db.py              
│   ├── schemas.py         
│   ├── security.py         
│   ├── store.py            
│   ├── routes_public.py    
│   ├── routes_moderator.py 
│   └── errors.py          
└── tests/
    ├── test_reporting.py
    ├── test_moderation.py
    └── test_privacy.py
```
