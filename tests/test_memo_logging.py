import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.services.memo import MemoUnavailable, extract_memo


class MemoLoggingTests(unittest.TestCase):
    @patch.dict("os.environ", {"GOOGLE_API_KEY": "private-test-key", "GEMINI_MODEL": "gemini-3.8-flash"})
    def test_failures_log_safe_categories(self):
        request = httpx.Request("POST", "https://example.test")
        response = httpx.Response(429, request=request, text="private-memo-content")
        scenarios = [
            (httpx.ReadTimeout("private-test-key private-memo-content"), "timed out"),
            (httpx.ConnectError("private-test-key private-memo-content"), "connection to Google failed"),
            (httpx.HTTPStatusError("private-test-key", request=request, response=response), "HTTP 429"),
        ]
        for error, expected in scenarios:
            with self.subTest(expected=expected), patch("app.services.memo.httpx.post", side_effect=error):
                with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                    with self.assertRaises(MemoUnavailable):
                        extract_memo(b"private-memo-content", "image/png")
                message = " ".join(logs.output)
                self.assertIn(expected, message)
                self.assertNotIn("private-test-key", message)
                self.assertNotIn("private-memo-content", message)

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "private-test-key", "GEMINI_MODEL": "gemini-3.8-flash"})
    @patch("app.services.memo.httpx.post")
    def test_invalid_response_logs_no_contents(self, post):
        response = MagicMock()
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "private-memo-content"}]}}]}
        post.return_value = response
        with self.assertLogs("uvicorn.error", level="WARNING") as logs:
            with self.assertRaises(MemoUnavailable):
                extract_memo(b"private-memo-content", "image/png")
        self.assertIn("invalid or incomplete Google response", logs.output[0])
        self.assertNotIn("private-memo-content", " ".join(logs.output))

    @patch.dict("os.environ", {"GOOGLE_API_KEY": ""})
    def test_missing_key_is_reported_without_value(self):
        with self.assertLogs("uvicorn.error", level="WARNING") as logs:
            with self.assertRaises(MemoUnavailable):
                extract_memo(b"memo", "image/png")
        self.assertIn("missing Google API key", logs.output[0])
