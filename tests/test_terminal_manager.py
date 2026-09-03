import sys
import unittest
from core.os.terminal_manager import TerminalManager

class TestTerminalManager(unittest.TestCase):

    def setUp(self):
        self.tm = TerminalManager()

    def test_shell_detection(self):
        self.assertIsNotNone(self.tm.shell)
        self.assertTrue(len(self.tm.shell) > 0)

    def test_execute_simple_command(self):
        cmd = 'echo "Hello Jarvis"' if sys.platform == "win32" else "echo 'Hello Jarvis'"
        res = self.tm.execute(cmd)
        self.assertTrue(res["success"])
        self.assertEqual(res["operation"], "terminal")
        self.assertIn("Hello Jarvis", res["stdout"])
        self.assertEqual(res["exit_code"], 0)
        self.assertGreaterEqual(res["duration"], 0.0)

    def test_secret_redaction(self):
        secret_str = "api_key=sk-1234567890abcdef1234567890abcdef"
        redacted = self.tm._redact_secrets(secret_str)
        self.assertNotIn("sk-1234567890abcdef1234567890abcdef", redacted)
        self.assertIn("***REDACTED", redacted)

    def test_execute_async(self):
        cmd = "ping 127.0.0.1 -n 2" if sys.platform == "win32" else "sleep 1"
        res = self.tm.execute_async(cmd)
        self.assertTrue(res["success"])
        self.assertGreater(res["pid"], 0)
        self.tm.terminate_process(res["pid"])

if __name__ == "__main__":
    unittest.main()
