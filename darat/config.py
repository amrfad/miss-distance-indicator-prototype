"""
Konfigurasi Ground Unit (Darat)
Semua konstanta dan parameter sistem dikumpulkan di sini.
Ubah nilai di file ini untuk menyesuaikan sistem.
"""

import numpy as np

# ============================================================
# SERIAL COMMUNICATION
# ============================================================
BAUD_RATE = 230400
SERIAL_TIMEOUT = 1
LINUX_SERIAL_PORT = "/dev/ttyUSB0"

# ============================================================
# COMMANDS (string yang dikirim via serial ke drone)
# ============================================================
CMD_STANDBY = "STANDBY"
CMD_START_RECORD = "START_REC"
CMD_STOP_RECORD = "STOP_REC"
CMD_STATUS = "STATUS"
CMD_INFO = "INFO"
CMD_PROCESS = "PROCESS"
CMD_TRANSMIT = "TRANSMIT"

# ============================================================
# FILE TRANSFER
# ============================================================
SUPPORTED_EXTENSIONS = [".mp4", ".wav", ".txt", ".json"]

# ============================================================
# TDOA PROCESSING
# ============================================================
SPEED_OF_SOUND = 343.0  # m/s

# Posisi mikrofon dalam meter (x, y, z)
MIC_POSITIONS = {
    "mic0": np.array([-1.58, 0.77, 0.09]),
    "mic1": np.array([1.60, 0.77, 0.09]),
    "mic2": np.array([-0.59, -0.92, -0.07]),
    "mic3": np.array([0.59, -0.92, -0.05]),
    "mic4": np.array([-0.5, -0.11, -0.16]),
    "mic5": np.array([0.13, -0.01, -0.17]),
}

# ============================================================
# CLUSTERING
# ============================================================
CLUSTER_EPS = 1.0  # meter — jarak threshold untuk grouping solusi

# ============================================================
# GUI BUTTON STYLES
# ============================================================
BUTTON_STYLES = {
    "Orange.TButton":     {"foreground": "black", "background": "#FF8C00"},
    "Green.TButton":      {"foreground": "black", "background": "#28A745"},
    "Red.TButton":        {"foreground": "black", "background": "#DC3545"},
    "LightGreen.TButton": {"foreground": "black", "background": "#90EE90"},
    "Blue.TButton":       {"foreground": "black", "background": "#007BFF"},
}
