import json
import threading
import unittest
import urllib.request
from unittest import mock

from gemini_web2api import bl
from gemini_web2api.config import CONFIG, DEFAULT_BL
from gemini_web2api.gemini import is_canned_error, CannedResponse, StaleBuildError
from gemini_web2api.models import MODELS, all_models, resolve_model
from gemini_web2api.server import GeminiHandler, ThreadedServer


class BuildLabelTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(CONFIG)
        bl._cache.update({"bl": None, "ts": 0.0, "source": None, "error": None})

    def tearDown(self):
        CONFIG.clear()
        CONFIG.update(self.original_config)
        bl._cache.update({"bl": None, "ts": 0.0, "source": None, "error": None})

    def test_parse_from_wiz_global_data(self):
        html = '<script>window.WIZ_global_data={"cfb2h":"boq_gemini-web-uiserver_20261115.13_p0"}</script>'
        self.assertEqual(bl.parse_bl(html), "boq_gemini-web-uiserver_20261115.13_p0")

    def test_parse_from_any_bundle_text(self):
        js = 'var a="x";var b="boq_assistant-bard-web-server_20260716.08_p0",c=1'
        self.assertEqual(bl.parse_bl(js), "boq_assistant-bard-web-server_20260716.08_p0")

    def test_parse_absent_returns_none(self):
        self.assertIsNone(bl.parse_bl("<html>nothing here</html>"))
        self.assertIsNone(bl.parse_bl(""))

    def test_explicit_config_wins_over_discovery(self):
        CONFIG["gemini_bl"] = "boq_assistant-bard-web-server_20200101.00_p0"
        with mock.patch.object(bl, "fetch_bl") as fetch:
            self.assertEqual(bl.get_bl(), CONFIG["gemini_bl"])
            fetch.assert_not_called()

    def test_auto_discovers_and_caches(self):
        CONFIG["gemini_bl"] = "auto"
        with mock.patch.object(bl, "fetch_bl", return_value="boq_gemini-web-uiserver_20261115.13_p0") as fetch:
            self.assertEqual(bl.get_bl(), "boq_gemini-web-uiserver_20261115.13_p0")
            self.assertEqual(bl.get_bl(), "boq_gemini-web-uiserver_20261115.13_p0")
            self.assertEqual(fetch.call_count, 1)

    def test_falls_back_to_default_when_fetch_fails(self):
        CONFIG["gemini_bl"] = "auto"
        with mock.patch.object(bl, "fetch_bl", side_effect=OSError("offline")):
            self.assertEqual(bl.get_bl(), DEFAULT_BL)

    def test_invalidate_forces_refetch(self):
        CONFIG["gemini_bl"] = "auto"
        values = iter(["boq_gemini-web-uiserver_20261115.13_p0", "boq_gemini-web-uiserver_20261116.10_p0"])
        with mock.patch.object(bl, "fetch_bl", side_effect=lambda *a, **k: next(values)) as fetch:
            first = bl.get_bl()
            bl.invalidate()
            second = bl.get_bl()
            self.assertNotEqual(first, second)
            self.assertEqual(fetch.call_count, 2)


class CannedErrorTests(unittest.TestCase):
    def test_detects_known_upstream_rejections(self):
        for text in (
            "I seem to be encountering an error. Can I try something else for you?",
            "I encountered an error doing what you asked. Please try again.",
            "I'm having a hard time fulfilling your request. Can I help with something else?",
        ):
            self.assertTrue(is_canned_error(text), text)

    def test_ignores_real_answers_that_mention_errors(self):
        long_answer = (
            "When a request fails the gateway returns 502. " * 20
        )
        self.assertFalse(is_canned_error(long_answer))
        self.assertFalse(is_canned_error("Error handling in Python uses try/except."))
        self.assertFalse(is_canned_error(""))
        self.assertFalse(is_canned_error(None))

    def test_exception_types_are_runtime_errors(self):
        self.assertTrue(issubclass(CannedResponse, RuntimeError))
        self.assertTrue(issubclass(StaleBuildError, RuntimeError))


class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(CONFIG)

    def tearDown(self):
        CONFIG.clear()
        CONFIG.update(self.original_config)

    def test_custom_model_from_config_resolves(self):
        CONFIG["models"] = {"my-flash": {"mode": 1, "think": 2, "desc": "custom"}}
        self.assertIn("my-flash", all_models())
        name, mode_id, think, err, extra = resolve_model("my-flash")
        self.assertEqual((name, mode_id, think, err), ("my-flash", 1, 2, None))

    def test_custom_model_can_override_builtin(self):
        CONFIG["models"] = {"gemini-3.7-flash": {"mode": 5, "think": 0}}
        name, mode_id, think, err, _ = resolve_model("gemini-3.7-flash")
        self.assertEqual((name, mode_id, think), ("gemini-3.7-flash", 5, 0))

    def test_unknown_model_falls_back_to_default(self):
        CONFIG["default_model"] = "gemini-3.6-flash"
        name, _, _, err, _ = resolve_model("totally-made-up")
        self.assertIsNone(err)
        self.assertEqual(name, "gemini-3.6-flash")

    def test_builtin_catalog_intact(self):
        self.assertIn("gemini-3.7-flash", MODELS)


class HealthzTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(CONFIG)
        CONFIG["gemini_bl"] = "auto"
        bl._cache.update({"bl": None, "ts": 0.0, "source": None, "error": None})
        self.patcher = mock.patch.object(
            bl, "fetch_bl", return_value="boq_gemini-web-uiserver_20261115.13_p0")
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        CONFIG.clear()
        CONFIG.update(self.original_config)
        bl._cache.update({"bl": None, "ts": 0.0, "source": None, "error": None})

    def test_healthz_reports_build_label(self):
        server = ThreadedServer(("127.0.0.1", 0), GeminiHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=20) as resp:
                self.assertEqual(resp.status, 200)
                payload = json.loads(resp.read().decode())
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("build_label", payload)
        self.assertTrue(payload["build_label"]["bl"].startswith("boq_"))
        self.assertTrue(payload["models"])


if __name__ == "__main__":
    unittest.main()
