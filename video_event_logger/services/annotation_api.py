import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkRequest


TOKEN_AUTH_SCHEME = "TokenAuth"
UPLOAD_TIMEOUT_MS = 30_000
MAX_INTERVALS_PER_UPLOAD = 2_000


def validate_api_settings(endpoint_url: str, token: str) -> Optional[str]:
    clean_url = endpoint_url.strip()
    parsed_url = urlparse(clean_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        return "Enter a complete HTTP or HTTPS upload endpoint URL."
    if not token.strip():
        return "Enter an API access token."
    if "\r" in token or "\n" in token:
        return "The API access token cannot contain line breaks."
    return None


def build_upload_request(endpoint_url: str, token: str) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(endpoint_url.strip()))
    request.setHeader(
        QNetworkRequest.KnownHeaders.ContentTypeHeader,
        "application/json",
    )
    request.setRawHeader(b"Accept", b"application/json")
    request.setRawHeader(
        b"Authorization",
        ("%s %s" % (TOKEN_AUTH_SCHEME, token.strip())).encode("utf-8"),
    )
    request.setTransferTimeout(UPLOAD_TIMEOUT_MS)
    return request


def server_response_message(response_body: bytes) -> str:
    if not response_body:
        return ""
    decoded = response_body.decode("utf-8", errors="replace").strip()
    if _looks_like_html(decoded):
        return ""
    try:
        data = json.loads(decoded)
    except (ValueError, TypeError):
        return decoded[:500]

    if isinstance(data, dict):
        for key in ("detail", "message", "error"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    return ""


def default_http_error_message(status_code: Optional[int]) -> str:
    messages = {
        400: "The server rejected the annotation JSON as invalid.",
        401: "Authentication failed. Check the API access token.",
        403: "This token does not have permission to upload annotations.",
        404: "The upload endpoint was not found. Check the URL in Connection → Settings…",
        408: "The server timed out while processing the upload.",
        413: "The annotation JSON is too large for the server.",
        422: "The server could not validate the annotation JSON.",
        429: "Too many upload requests. Wait a moment and try again.",
    }
    if status_code in messages:
        return messages[status_code]
    if status_code is not None and status_code >= 500:
        return "The server could not process the upload. Try again later."
    return "Unknown server error."


@dataclass(frozen=True)
class UploadOutcome:
    """What the upload result screen shows for one server answer.

    tone: "success" (green), "attention" (amber: accepted but needs a look,
    or nothing changed), "error" (red: not stored), "canceled".
    primary: the main next step: "next" (open next video), "back" (edit),
    "settings" (connection settings), "retry" or "close".
    """

    tone: str
    title: str
    lead: str
    message: str
    footer: str
    primary: str
    status_text: str


_SUCCESS_STATUSES = {
    "export_queued": (
        "success",
        "Submitted",
        "The server accepted the annotations. Clips will be built and uploaded in the background.",
    ),
    "export_pending": (
        "success",
        "Submitted",
        "The server accepted the annotations. An export for this video is already running.",
    ),
    "no_events": (
        "success",
        "Marked as reviewed — no events",
        "The server recorded that this video has no events.",
    ),
    "unrecognized": (
        "attention",
        "Submitted, but not matched",
        "The server saved the annotations but could not match this video name "
        "to a batch group, so no clips will be made. Check the file name or tell your lead.",
    ),
}

SAVED_LOCALLY = "Your work is saved locally."


def _json_object(response_body: bytes) -> Dict[str, Any]:
    if not response_body:
        return {}
    try:
        data = json.loads(response_body.decode("utf-8", errors="replace"))
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _text_field(data: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return ""


def classify_upload_response(
    status_code: Optional[int],
    response_body: bytes,
    network_error_text: str = "",
    canceled: bool = False,
) -> UploadOutcome:
    """Map one eg-ml / tracker answer to what the annotator sees."""
    if canceled:
        return UploadOutcome(
            "canceled", "Upload canceled", "Nothing was sent. " + SAVED_LOCALLY,
            "", "", "close", "Annotation upload canceled.",
        )
    data = _json_object(response_body)
    if status_code is None:
        return UploadOutcome(
            "error",
            "Could not reach the server",
            "Check your internet or VPN connection and retry. " + SAVED_LOCALLY,
            network_error_text or "No answer from the server.",
            "Network error · no HTTP answer",
            "retry",
            "Annotation upload failed: no connection.",
        )
    if 200 <= status_code < 300:
        status_value = data.get("status")
        server_status = status_value if isinstance(status_value, str) else ""
        tone, title, lead = _SUCCESS_STATUSES.get(
            server_status,
            ("success", "Submitted", "The server accepted the annotations."),
        )
        footer = "HTTP %d" % status_code + (" · %s" % server_status if server_status else "")
        return UploadOutcome(
            tone, title, lead,
            _text_field(data, ("message", "detail")) or server_response_message(response_body),
            footer, "next",
            "Annotations uploaded%s." % (" (%s)" % server_status if server_status else ""),
        )
    message = _text_field(data, ("error", "detail", "message")) or server_response_message(response_body)
    footer = "HTTP %d" % status_code
    if status_code == 409:
        return UploadOutcome(
            "attention",
            "Already uploaded",
            "Annotations for this video were uploaded before. The server kept the earlier version.",
            message or "This annotation file was already uploaded.",
            footer + " · nothing changed on the server",
            "next",
            "Upload skipped: already uploaded.",
        )
    if status_code == 400:
        return UploadOutcome(
            "error",
            "The server rejected the annotations",
            "Fix the problem below and submit again. " + SAVED_LOCALLY,
            message or default_http_error_message(400),
            footer, "back", "Annotation upload rejected (HTTP 400).",
        )
    if status_code in (401, 403):
        lead = (
            "Your personal access token is missing, wrong or expired. "
            "Paste a valid token in Connection settings and submit again."
            if status_code == 401
            else "This access token is not allowed to upload annotations. "
            "Check the token in Connection settings."
        )
        return UploadOutcome(
            "error",
            "Access token not accepted",
            lead + " " + SAVED_LOCALLY,
            message or default_http_error_message(status_code),
            footer, "settings", "Annotation upload failed: bad access token.",
        )
    if status_code >= 500:
        return UploadOutcome(
            "error",
            "Server problem — try again later",
            "The annotation server is temporarily unavailable. "
            "This is not your mistake. " + SAVED_LOCALLY,
            message or default_http_error_message(status_code),
            footer + " · retry in a few minutes",
            "retry",
            "Annotation upload failed: server problem (HTTP %d)." % status_code,
        )
    return UploadOutcome(
        "error",
        "Upload failed",
        default_http_error_message(status_code) + " " + SAVED_LOCALLY,
        message or default_http_error_message(status_code),
        footer, "close", "Annotation upload failed (HTTP %d)." % status_code,
    )


def _looks_like_html(text: str) -> bool:
    normalized = text.lstrip().lower()
    return normalized.startswith("<!doctype html") or normalized.startswith("<html")
