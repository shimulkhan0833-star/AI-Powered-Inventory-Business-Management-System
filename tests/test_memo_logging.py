import unittest
from unittest.mock import patch

import httpx2
from google.genai.errors import APIError

from app.services.memo import MemoUnavailable, extract_memo


class MemoLoggingTests(unittest.TestCase):
    @patch.dict("os.environ", {"GOOGLE_API_KEY": "private-test-key", "GEMINI_MODEL": "gemini-3.8-flash"})
    @patch("app.services.memo.time.sleep")
    @patch("app.services.memo.ChatGoogleGenerativeAI")
    def test_failures_log_safe_categories(self, model, sleep):
        invoke = model.return_value.with_structured_output.return_value.invoke
        scenarios = [
            (httpx2.ReadTimeout("private-test-key private-memo-content"), "timed out"),
            (httpx2.ConnectError("private-test-key private-memo-content"), "connection to Google failed"),
            (APIError(429, {"error": {"message": "private-memo-content"}}), "HTTP 429"),
            (ValueError("private-memo-content"), "invalid or incomplete Google response"),
        ]
        for error, expected in scenarios:
            with self.subTest(expected=expected):
                invoke.side_effect = error
                with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                    with self.assertRaises(MemoUnavailable):
                        extract_memo(b"private-memo-content", "image/png")
                message = " ".join(logs.output)
                self.assertIn(expected, message)
                self.assertNotIn("private-test-key", message)
                self.assertNotIn("private-memo-content", message)

    @patch.dict("os.environ", {"GOOGLE_API_KEY": ""})
    def test_missing_key_is_reported_without_value(self):
        with self.assertLogs("uvicorn.error", level="WARNING") as logs:
            with self.assertRaises(MemoUnavailable):
                extract_memo(b"memo", "image/png")
        self.assertIn("missing Google API key", logs.output[0])
