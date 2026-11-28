import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.services.memo import MemoUnavailable, extract_memo


def success_response():
    response = MagicMock()
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text":
        '{"supplier_name":"Example","items":[{"product_name":"Rice","quantity":"2","unit_price":"10"}]}'}]}}]}
    return response


def http_error(status):
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("provider error", request=request, response=response)


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.8-flash"})
@patch("app.services.memo.time.sleep")
class MemoRetryTests(unittest.TestCase):
    @patch("app.services.memo.httpx.post")
    def test_retries_503_and_timeout_once_then_returns_draft(self, post, sleep):
        for error in (http_error(503), httpx.ReadTimeout("timeout")):
            with self.subTest(error=type(error).__name__):
                post.reset_mock()
                sleep.reset_mock()
                post.side_effect = [error, success_response()]
                draft = extract_memo(b"image", "image/png")
                self.assertEqual(draft.items[0].product_name, "Rice")
                self.assertEqual(post.call_count, 2)
                sleep.assert_called_once_with(1)

    @patch("app.services.memo.httpx.post")
    def test_two_failures_stop_and_allow_manual_fallback(self, post, sleep):
        post.side_effect = [http_error(503), http_error(503)]
        with self.assertRaises(MemoUnavailable):
            extract_memo(b"image", "image/png")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("app.services.memo.httpx.post")
    def test_quota_and_auth_errors_are_not_retried(self, post, sleep):
        for status in (429, 401):
            with self.subTest(status=status):
                post.reset_mock()
                sleep.reset_mock()
                post.side_effect = http_error(status)
                with self.assertRaises(MemoUnavailable):
                    extract_memo(b"image", "image/png")
                self.assertEqual(post.call_count, 1)
                sleep.assert_not_called()
