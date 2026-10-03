import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("whistledrop")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 headers: Optional[dict] = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def _body(code: str, message: str, details=None) -> dict:
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code,
                            headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # not sending the input back, so report text doesn't end up in logs
        details = []
        for err in exc.errors():
            location = err["loc"][0] if err["loc"] else "request"
            field = ".".join(str(part) for part in err["loc"][1:]) or None
            details.append({"location": location, "field": field, "message": err["msg"]})
        return JSONResponse(_body("validation_error", "The request data is invalid.", details),
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(_body(code, message), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        log.error("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(_body("internal_error", "Something went wrong on our side."),
                            status_code=500)
