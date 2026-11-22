import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DataDirectoryTests(unittest.TestCase):
    def test_explicit_data_dir_contains_config_and_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "user-data"
            env = os.environ.copy()
            env["LOCAL_AGENT_HUB_DATA_DIR"] = str(data_dir)
            subprocess.run(
                [sys.executable, "-c", "import main; assert main.CONFIG_PATH.exists(); assert main.LOG_DIR.is_dir()"],
                cwd=Path(__file__).resolve().parent.parent,
                env=env,
                check=True,
            )
            self.assertTrue((data_dir / "config.json").is_file())
            self.assertTrue((data_dir / "logs").is_dir())


if __name__ == "__main__":
    unittest.main()
