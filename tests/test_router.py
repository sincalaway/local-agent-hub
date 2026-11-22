import unittest
import copy
from unittest.mock import patch

import main


class RouterTests(unittest.TestCase):
    def test_general_chat_uses_llama(self):
        self.assertEqual(main.choose_backend("解释一下光合作用"), "llama")

    def test_code_and_complex_tasks_use_strata(self):
        self.assertEqual(main.choose_backend("帮我写一段 Python 代码"), "strata")
        self.assertEqual(main.choose_backend("复杂系统设计评审"), "strata")

    def test_explicit_large_model_task_uses_airllm(self):
        self.assertEqual(main.choose_backend("请用 70B 模型做批量深度分析"), "airllm")

    def test_completion_url(self):
        self.assertEqual(main._completion_url("http://127.0.0.1:8081/v1/"), "http://127.0.0.1:8081/v1/chat/completions")

    def test_config_merge_keeps_default_backends(self):
        merged = main._merge_config({"auto_start": False})
        self.assertFalse(merged["auto_start"])
        self.assertEqual(set(merged["backends"].keys()), {"llama", "strata", "airllm", "custom"})
        self.assertFalse(merged["backends"]["custom"]["enabled"])

    def test_model_discovery_uses_api_key_and_parses_model_ids(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"data":[{"id":"local-qwen"},{"id":"local-llama"}]}'

        with patch.object(main, "urlopen", return_value=FakeResponse()) as mocked:
            models = main._fetch_models("http://127.0.0.1:1234/v1", "test-secret")

        self.assertEqual(models, ["local-qwen", "local-llama"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:1234/v1/models")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")

    def test_custom_backend_can_be_selected_manually(self):
        config = copy.deepcopy(main.CONFIG)
        config["backends"]["custom"].update({"enabled": True, "model": "local-qwen"})
        with patch.object(main, "CONFIG", config), patch.object(main, "health_check", return_value=(True, "HTTP 200")), patch.object(main, "_call_backend", return_value="local reply"):
            result = main.run_chat({"model": "custom", "messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(result["backend"], "custom")
        self.assertEqual(result["reply"], "local reply")

    def test_custom_backend_health_path_includes_v1(self):
        custom = main.DEFAULT_CONFIG["backends"]["custom"]
        self.assertEqual(main._health_url(custom), "http://127.0.0.1:1234/v1/models")

    def test_not_needed_api_key_is_not_sent_to_backend(self):
        config = copy.deepcopy(main.CONFIG)
        config["backends"]["strata"].update({
            "base_url": "http://127.0.0.1:8080/v1",
            "api_key": "not-needed",
            "model": "test-model",
        })

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"choices":[{"message":{"content":"ok"}}]}'

        with patch.object(main, "CONFIG", config), patch.object(main, "urlopen", return_value=FakeResponse()) as mocked:
            self.assertEqual(main._call_backend("strata", [{"role": "user", "content": "hi"}], 0.7, 64), "ok")

        request = mocked.call_args.args[0]
        self.assertFalse(any(name.lower() == "authorization" for name, _value in request.header_items()))


if __name__ == "__main__":
    unittest.main()
