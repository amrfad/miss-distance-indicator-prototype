import sys
from unittest.mock import MagicMock

# Mock heavy/missing dependencies to allow importing modules under test
sys.modules['librosa'] = MagicMock()
sys.modules['soundfile'] = MagicMock()

import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "."))

from udara.drone_system.main import process_command, EXIT_CODE_RESTART

class TestDroneRestart(unittest.TestCase):
    def test_process_command_restart(self):
        audio_system = MagicMock()
        audio_system.restart_requested = False
        
        serial_handler = MagicMock()
        
        # Verify that process_command raises KeyboardInterrupt on "RESTART"
        with self.assertRaises(KeyboardInterrupt):
            process_command("RESTART", audio_system, serial_handler)
            
        # Verify restart flag was set
        self.assertTrue(audio_system.restart_requested)
        # Verify response was sent via serial
        serial_handler.send_response.assert_called_once_with("OK:Restarting drone system...")

if __name__ == "__main__":
    unittest.main()
