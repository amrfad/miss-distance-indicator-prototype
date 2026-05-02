"""
Drone Audio Detection System
Sistem modular untuk recording, filtering, dan event detection
yang dikontrol via komunikasi serial dari ground station.

Import lazy — modul hardware-dependent (librosa, pyserial, arecord) tidak
di-load otomatis saat package di-import. Import eksplisit bila diperlukan:

    from drone_system.recorder import AudioRecorder
    from drone_system.controller import DroneAudioSystem
"""

__version__ = "1.0.0"
__all__ = [
    "AudioRecorder",
    "AudioProcessor",
    "EventDetector",
    "DataLogger",
    "SerialHandler",
    "DroneAudioSystem",
]
