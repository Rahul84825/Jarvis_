import time
import unittest
from unittest.mock import MagicMock, patch
from core.clap_detector import ClapDetector

class TestClapDetector(unittest.TestCase):
    
    @patch('core.clap_detector.sd.InputStream')
    def setUp(self, mock_input_stream):
        # Setup detector with shorter gap limits for faster unit test execution
        self.detector = ClapDetector(threshold=0.15, min_gap=0.04, max_gap=0.3)
        self.single_mock = MagicMock()
        self.double_mock = MagicMock()
        
    def tearDown(self):
        self.detector.stop()

    @patch('core.clap_detector.sd.InputStream')
    def test_start_stop(self, mock_input_stream):
        """Verifies start/stop sets the active state correctly."""
        self.assertFalse(self.detector.is_active())
        self.detector.start(self.single_mock, self.double_mock)
        self.assertTrue(self.detector.is_active())
        self.detector.stop()
        self.assertFalse(self.detector.is_active())

    def test_single_clap_timer_fires(self):
        """Verifies that a single clap triggers the single clap callback after the timeout gap."""
        self.detector.on_single_clap_cb = self.single_mock
        self.detector.on_double_clap_cb = self.double_mock
        
        t0 = time.time()
        self.detector._handle_clap_event(t0)
        
        # Shouldn't call immediately
        self.single_mock.assert_not_called()
        self.assertTrue(self.detector._waiting_for_second)
        
        # Wait for max_gap (0.3s) to pass
        time.sleep(0.4)
        
        # Callback should have fired
        self.single_mock.assert_called_once()
        self.double_mock.assert_not_called()
        self.assertFalse(self.detector._waiting_for_second)

    def test_double_clap_fires(self):
        """Verifies that a second clap within the window triggers double-clap and cancels single-clap."""
        self.detector.on_single_clap_cb = self.single_mock
        self.detector.on_double_clap_cb = self.double_mock
        
        t0 = time.time()
        self.detector._handle_clap_event(t0)
        
        # Second clap is 100ms later (between min_gap 40ms and max_gap 300ms)
        self.detector._handle_clap_event(t0 + 0.1)
        
        # Wait a moment for thread dispatch
        time.sleep(0.05)
        
        self.double_mock.assert_called_once()
        self.single_mock.assert_not_called()
        self.assertFalse(self.detector._waiting_for_second)
        
        # Wait for timer window to fully expire to ensure single clap is not called
        time.sleep(0.3)
        self.single_mock.assert_not_called()

if __name__ == "__main__":
    unittest.main()
