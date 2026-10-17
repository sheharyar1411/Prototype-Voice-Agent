"""
Standardized JSON response envelope used by all API endpoints.

FLOW MAP:
  router handler → success_response / error_response → JSONResponse

KEY DETAILS:
  - Every endpoint returns {"data": ..., "error": ...} per the challenge spec
  - error_response includes a structured error object with code, message, details
  - Matches the assessment requirement: "standardized JSON responses"
"""

from typing import Any, Optional

from fastapi.responses import JSONResponse


def success_response(
    data: Any,
    status_code: int = 200,
    message: Optional[str] = None,
) -> JSONResponse:
    """
    Wrap a successful result in the standard envelope.

    Args:
        data: The response payload (dict, list, or scalar).
        status_code: HTTP status code (default 200).
        message: Optional human-readable success message.

    Returns:
        JSONResponse with ``{"data": ..., "error": null}`` body.
    """
    body: dict[str, Any] = {"data": data, "error": None}
    if message:
        body["message"] = message
    return JSONResponse(content=body, status_code=status_code)


def error_response(
    message: str,
    status_code: int = 400,
    code: str = "BAD_REQUEST",
    details: Optional[list[dict[str, Any]]] = None,
) -> JSONResponse:
    """
    Wrap an error in the standard envelope.

    Args:
        message: Human-readable error description.
        status_code: HTTP status code.
        code: Machine-readable error code (e.g. VALIDATION_ERROR).
        details: Optional list of per-field error details.

    Returns:
        JSONResponse with ``{"data": null, "error": {...}}`` body.
    """
    error_body: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details:
        error_body["details"] = details
    return JSONResponse(
        content={"data": None, "error": error_body},
        status_code=status_code,
    )
