"""
Konfigurasi Ground Unit (Darat)
File ini sekarang hanya menyimpan konstanta statis (misal: command serial).
Parameter yang dapat dikonfigurasi telah dipindahkan ke:
darat/config/ground_config_override.json dan diatur melalui GroundConfigManager.
"""

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
CMD_SET_CONFIG = "SET_CONFIG"

# ============================================================
# CONFIG UI SERIAL PROTOCOL (section 5.5 communication contract)
# ============================================================
CONFIG_TX_START_MARKER = "[CONFIG_START]"
CONFIG_TX_END_MARKER = "[CONFIG_END]"

# ============================================================
# FILE TRANSFER
# ============================================================
SUPPORTED_EXTENSIONS = [".mp4", ".wav", ".txt", ".json"]


