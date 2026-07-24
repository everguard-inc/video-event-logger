import unittest

from video_event_logger.services.annotation_api import (
    TOKEN_AUTH_SCHEME,
    UPLOAD_TIMEOUT_MS,
    build_upload_request,
    default_http_error_message,
    server_response_message,
    validate_api_settings,
)


class AnnotationApiTest(unittest.TestCase):
    def test_settings_require_http_url_and_token(self) -> None:
        self.assertIsNotNone(validate_api_settings("example.org/upload", "token"))
        self.assertIsNotNone(validate_api_settings("https://example.org/upload", ""))
        self.assertIsNone(
            validate_api_settings("http://localhost:8000/api/annotations", "secret")
        )

    def test_request_uses_token_auth_and_json_body_contract(self) -> None:
        request = build_upload_request(
            "https://example.org/api/v1/annotations",
            "secret-token",
        )

        self.assertEqual(request.url().toString(), "https://example.org/api/v1/annotations")
        self.assertEqual(
            bytes(request.rawHeader("Authorization")),
            ("%s secret-token" % TOKEN_AUTH_SCHEME).encode("utf-8"),
        )
        self.assertEqual(bytes(request.rawHeader("Content-Type")), b"application/json")
        self.assertEqual(bytes(request.rawHeader("Accept")), b"application/json")
        self.assertEqual(request.transferTimeout(), UPLOAD_TIMEOUT_MS)

    def test_server_message_prefers_structured_detail(self) -> None:
        self.assertEqual(
            server_response_message(b'{"detail": "Already uploaded"}'),
            "Already uploaded",
        )
        self.assertEqual(server_response_message(b"gateway unavailable"), "gateway unavailable")

    def test_html_error_page_is_hidden_in_favor_of_friendly_http_message(self) -> None:
        html = b"""<!doctype html><html><body><h1>Not Found</h1></body></html>"""

        self.assertEqual(server_response_message(html), "")
        self.assertEqual(
            default_http_error_message(404),
            "The upload endpoint was not found. Check the URL in Connection \u2192 Settings\u2026",
        )


if __name__ == "__main__":
    unittest.main()
