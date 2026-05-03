"""
Konfigurasi Drone Unit (Udara)
File ini sekarang hanya menyimpan konstanta statis dan profil perangkat.
Parameter yang dapat dikonfigurasi telah dipindahkan ke:
udara/config/drone_config_override.json dan diatur melalui ConfigManager.
"""

# ============================================================
# DEVICE PROFILES (Statik)
# ============================================================
DEVICE_PROFILES = {
    "H8": {
        "channels": 12,
        "format": "S24_3LE",
        "take_indices_4mic": (4, 5, 6, 7),      # Channel 5-8 (4 XLR inputs)
        "take_indices_6mic": (4, 5, 6, 7, 8, 9), # Channel 5-10 (4 XLR + 2 Capsule)
        "num_mics": 6  # Default fallback
    },
    "H6E": {
        "channels": 6,
        "format": "S32_LE",
        "take_indices_4mic": (2, 3, 4, 5),
        "take_indices_6mic": (2, 3, 4, 5),  # H6E tetap 4 mic
        "num_mics": 4
    }
}

def get_take_indices(profile_name, num_mics_h8=6):
    """Get take_indices berdasarkan profile dan jumlah mic yang dikonfigurasi"""
    profile = DEVICE_PROFILES.get(profile_name, DEVICE_PROFILES["H6E"])
    num_mics = num_mics_h8 if profile_name == "H8" else profile.get("num_mics", 4)
    if num_mics == 6:
        return profile.get("take_indices_6mic", profile["take_indices_4mic"])
    else:
        return profile["take_indices_4mic"]

# Fallback defaults for legacy modules
CHANNELS = 12
CHANNEL_INDICES = (4, 5, 6, 7)

# ============================================================
# FIXED SYSTEM PARAMETERS
# ============================================================
# Parameter audio processing yang jarang berubah
HOP_LENGTH = 512
FRAME_LENGTH = 1024
NORMALIZATION_PERCENTILE = 99.9

# Format file & timing
EVENT_PADDING_SEC = 0.3
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
POST_RECORDING_DELAY = 0.5
MAIN_LOOP_DELAY = 0.1