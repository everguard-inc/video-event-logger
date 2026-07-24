import json
from typing import Optional
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


def _looks_like_html(text: str) -> bool:
    normalized = text.lstrip().lower()
    return normalized.startswith("<!doctype html") or normalized.startswith("<html")
