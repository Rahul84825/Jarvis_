import unittest
from core.os.system_info import SystemInfoProvider

class TestSystemInfo(unittest.TestCase):

    def setUp(self):
        self.sip = SystemInfoProvider()

    def test_cpu_info(self):
        res = self.sip.get_cpu_info()
        self.assertTrue(res["success"])
        self.assertIn("CPU:", res["text"])

    def test_ram_info(self):
        res = self.sip.get_ram_info()
        self.assertTrue(res["success"])
        self.assertIn("RAM:", res["text"])

    def test_disk_info(self):
        res = self.sip.get_disk_info()
        self.assertTrue(res["success"])
        self.assertIn("Disk Space", res["text"])

    def test_os_info(self):
        res = self.sip.get_os_info()
        self.assertTrue(res["success"])
        self.assertIn("Operating System:", res["text"])

    def test_network_ip(self):
        res = self.sip.get_network_ip()
        self.assertTrue(res["success"])
        self.assertIn("Local IP", res["text"])

    def test_uptime(self):
        res = self.sip.get_uptime()
        self.assertTrue(res["success"])
        self.assertIn("Uptime", res["text"])

if __name__ == "__main__":
    unittest.main()
