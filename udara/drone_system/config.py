"""
Konfigurasi sistem drone audio detection
Semua parameter dapat diubah di file ini
"""

# ============================================================
# OPERATION MODE
# ============================================================
# Mode operasi sistem: "ONLINE" atau "OFFLINE"
# ONLINE: Menerima command via serial (ttyUSB0) dari ground station
# OFFLINE: Kontrol langsung dari keyboard (untuk testing/debugging)
OPERATION_MODE = "OFFLINE"  # Ubah ke "ONLINE" untuk production

# ============================================================
# SERIAL COMMUNICATION (Hanya digunakan jika OPERATION_MODE = "ONLINE")
# ============================================================
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 230400
SERIAL_TIMEOUT = 5

# ============================================================
# AUDIO RECORDING
# ============================================================
ARECORD_DEVICE = "hw:2,0"
SAMPLE_RATE = 48000

# ============================================================
# MICROPHONE CONFIGURATION FOR H8
# ============================================================
# Jumlah microphone yang digunakan untuk H8 (4 atau 6)
# - 4 mic: menggunakan channel 5-8 (index 4-7) -> 6 pasang TDOA
# - 6 mic: menggunakan channel 5-10 (index 4-9) -> 15 pasang TDOA
# 
# ZOOM H8 Channel Mapping untuk 6 mic:
#   Channel 5 = Mic 1 (XLR 1) -> index 4
#   Channel 6 = Mic 2 (XLR 2) -> index 5
#   Channel 7 = Mic 3 (XLR 3) -> index 6
#   Channel 8 = Mic 4 (XLR 4) -> index 7
#   Channel 9 = Mic A (Capsule A/L) -> index 8
#   Channel 10 = Mic B (Capsule B/R) -> index 9
#
# Note: H6E tetap menggunakan 4 mic saja
NUM_MICS_H8 = 6  # Ubah ke 4 jika hanya menggunakan 4 microphone

# Device Profiles Configuration
# take_indices_4mic dan take_indices_6mic untuk H8
DEVICE_PROFILES = {
    "H8": {
        "channels": 12,
        "format": "S24_3LE",
        "take_indices_4mic": (4, 5, 6, 7),      # Channel 5-8 (4 XLR inputs)
        "take_indices_6mic": (4, 5, 6, 7, 8, 9), # Channel 5-10 (4 XLR + 2 Capsule)
        "num_mics": NUM_MICS_H8  # Diambil dari konfigurasi di atas
    },
    "H6E": {
        "channels": 6,
        "format": "S32_LE",
        "take_indices_4mic": (2, 3, 4, 5),
        "take_indices_6mic": (2, 3, 4, 5),  # H6E tetap 4 mic
        "num_mics": 4  # H6E selalu 4 mic
    }
}

# Helper function to get take_indices based on num_mics
def get_take_indices(profile_name):
    """Get take_indices berdasarkan profile dan jumlah mic yang dikonfigurasi"""
    profile = DEVICE_PROFILES.get(profile_name, DEVICE_PROFILES["H6E"])
    num_mics = profile.get("num_mics", 4)
    if num_mics == 6:
        return profile.get("take_indices_6mic", profile["take_indices_4mic"])
    else:
        return profile["take_indices_4mic"]

# Active Profile ("H8" or "H6E")
ACTIVE_PROFILE = "H8"

# Default fallback values (will be overwritten by profile)
CHANNELS = 12
CHANNEL_INDICES = (4, 5, 6, 7)

# ============================================================
# FILTERING PARAMETERS
# ============================================================
# Gunakan non-stationary noise reduction
STATIONARY = False

# Proporsi pengurangan noise (0.0 - 1.0)
# 1.0 = maksimal reduction, 0.0 = no reduction
PROP_DECREASE = 1.0

# Smoothing di domain frekuensi (Hz)
FREQ_MASK_SMOOTH_HZ = 100

# Smoothing di domain waktu (ms)
TIME_MASK_SMOOTH_MS = 10

# Normalisasi output filtered audio
NORMALIZE = False

# ============================================================
# EVENT DETECTION PARAMETERS
# ============================================================
# Durasi minimal event yang valid (detik)
MIN_DURATION = 0.25

# Gap maksimal antar event untuk di-merge (detik)
MAX_GAP = 0.1

# Threshold untuk deteksi awal event (relatif terhadap max energy)
# 0.20 = 20% dari max energy
DETECT_RATIO = 0.20

# Threshold untuk filter event final (relatif terhadap max energy)
# Event harus minimal sekuat ini untuk dianggap valid
FILTER_RATIO = 0.40

# Abaikan deteksi di awal recording (detik)
# Untuk menghindari noise dari startup
IGNORE_TIME = 0.5

# ============================================================
# LIBROSA PARAMETERS
# ============================================================
HOP_LENGTH = 512
FRAME_LENGTH = 1024

# Percentile untuk normalisasi RMS (menghindari outlier)
NORMALIZATION_PERCENTILE = 99.9

# ============================================================
# OUTPUT CONFIGURATION
# ============================================================
# Base directory untuk menyimpan recording
BASE_OUTPUT_DIR = "drone_recordings"

# Nama file CSV untuk menyimpan detected events
EVENTS_CSV = "detected_events.csv"

# Nama file JSON untuk menyimpan session events
EVENTS_JSON = "session_events.json"

# Nama file JSON untuk menyimpan TDOA results
TDOA_JSON = "session_tdoa.json"

# Padding untuk pemotongan event (detik)
# Audio akan dipotong dari start - padding sampai end + padding
EVENT_PADDING_SEC = 0.3

# Format timestamp untuk session folder
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Format timestamp untuk CSV log
LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================
# SYSTEM PARAMETERS
# ============================================================
# Delay setelah stop recording sebelum proses (detik)
POST_RECORDING_DELAY = 0.5

# Delay di main loop untuk mengurangi CPU usage (detik)
MAIN_LOOP_DELAY = 0.1

# Timeout untuk terminate arecord process (detik)
ARECORD_TERMINATE_TIMEOUT = 3

# ===========================================================
# TDOA CALCULATION PARAMETER
# ===========================================================
# Tipe Cross-Correlation
IS_GCC_PHAT = True