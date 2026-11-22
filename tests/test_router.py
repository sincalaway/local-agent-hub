import unittest

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
        self.assertEqual(set(merged["backends"].keys()), {"llama", "strata", "airllm"})


if __name__ == "__main__":
    unittest.main()
