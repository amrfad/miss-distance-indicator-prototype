"""
Drone Audio Detection System
Sistem modular untuk recording, filtering, dan event detection
yang dikontrol via komunikasi serial dari ground station.
"""

from .recorder import AudioRecorder
from .processor import AudioProcessor
from .detector import EventDetector
from .logger import DataLogger
from .serial_handler import SerialHandler
from .controller import DroneAudioSystem

__version__ = "1.0.0"
__all__ = [
    "AudioRecorder",
    "AudioProcessor",
    "EventDetector",
    "DataLogger",
    "SerialHandler",
    "DroneAudioSystem"
]
