import unittest
from unittest.mock import patch

import httpx2
from google.genai.errors import APIError

from app.services.memo import ExtractedItem, ExtractedMemo, MemoUnavailable, extract_memo


def success_response():
    return ExtractedMemo(supplier_name="Example", items=[ExtractedItem(product_name="Rice", quantity="2", unit_price="10")])


def api_error(status):
    return APIError(status, {"error": {"message": "provider error", "code": status}})


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.8-flash"})
@patch("app.services.memo.time.sleep")
class MemoRetryTests(unittest.TestCase):
    @patch("app.services.memo.ChatGoogleGenerativeAI")
    def test_retries_503_and_timeout_once_then_returns_draft(self, model, sleep):
        invoke = model.return_value.with_structured_output.return_value.invoke
        for error in (api_error(503), httpx2.ReadTimeout("timeout")):
            with self.subTest(error=type(error).__name__):
                invoke.reset_mock()
                sleep.reset_mock()
                invoke.side_effect = [error, success_response()]
                draft = extract_memo(b"image", "image/png")
                self.assertEqual(draft.items[0].product_name, "Rice")
                self.assertEqual(invoke.call_count, 2)
                sleep.assert_called_once_with(1)
        model.assert_called_with(model="gemini-3.8-flash", api_key="test-key", timeout=20, max_retries=1)
        message = invoke.call_args.args[0][0]
        self.assertEqual(message.content[1]["image_url"]["url"], "data:image/png;base64,aW1hZ2U=")

    @patch("app.services.memo.ChatGoogleGenerativeAI")
    def test_two_failures_stop_and_allow_manual_fallback(self, model, sleep):
        invoke = model.return_value.with_structured_output.return_value.invoke
        invoke.side_effect = [api_error(503), api_error(503)]
        with self.assertRaises(MemoUnavailable):
            extract_memo(b"image", "image/png")
        self.assertEqual(invoke.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("app.services.memo.ChatGoogleGenerativeAI")
    def test_quota_and_auth_errors_are_not_retried(self, model, sleep):
        invoke = model.return_value.with_structured_output.return_value.invoke
        for status in (429, 401):
            with self.subTest(status=status):
                invoke.reset_mock()
                sleep.reset_mock()
                invoke.side_effect = api_error(status)
                with self.assertRaises(MemoUnavailable):
                    extract_memo(b"image", "image/png")
                self.assertEqual(invoke.call_count, 1)
                sleep.assert_not_called()
