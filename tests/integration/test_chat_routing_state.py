import fcntl
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


class SharedRoutingTests(unittest.TestCase):
    def test_chat_and_translation_success_updates_use_cross_process_lock(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "routing.json"
            code = """
import sys
from qtranslate.audit.legacy import remember_success
remember_success(sys.argv[1],sys.argv[2],{'provider':'fixture','credential_id':'fixture','model':'fixture'})
"""
            children = []
            with path.with_suffix(".json.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    for action in ["text", "translation"]:
                        children.append(
                            subprocess.Popen(
                                ["/usr/bin/python3", "-c", code, str(path), action],
                                env={**os.environ, "PYTHONPATH": "src"},
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )
                        )
                    time.sleep(0.2)
                    blocked = all(child.poll() is None for child in children)
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                    for child in children:
                        child.communicate(timeout=3)
            self.assertTrue(blocked, "Routing writer ignored the shared process lock")
            self.assertTrue(all(child.returncode == 0 for child in children))
            self.assertEqual(
                set(json.loads(path.read_text())["last_success"]),
                {"text", "translation"},
            )
