import os
import unittest
from core.os.process_manager import ProcessManager

class TestProcessManager(unittest.TestCase):

    def setUp(self):
        self.pm = ProcessManager()

    def test_list_processes(self):
        procs = self.pm.list_processes(limit=10)
        self.assertIsInstance(procs, list)
        self.assertGreater(len(procs), 0)
        self.assertIn("pid", procs[0])
        self.assertIn("name", procs[0])

    def test_find_process_by_pid(self):
        current_pid = os.getpid()
        procs = self.pm.find_process(current_pid)
        self.assertEqual(len(procs), 1)
        self.assertEqual(procs[0]["pid"], current_pid)

    def test_get_top_cpu_processes(self):
        top_procs = self.pm.get_top_cpu_processes(limit=3)
        self.assertLessEqual(len(top_procs), 3)

if __name__ == "__main__":
    unittest.main()
