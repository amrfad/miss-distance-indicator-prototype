import sys
import os
import subprocess

TARGET_IP = "10.99.99.2"
PREFIX = "24"
INTERFACE = "eth0"

def is_root():
    return os.geteuid() == 0

def init_network():
    """Entry point untuk setup auto-network spesifik Drone/Udara."""
    if not is_root():
        print("[NETWORK] ⚠️ PERINGATAN: Program drone tidak dijalankan sebagai root (sudo).")
        print("[NETWORK] Automasi IP statis dilewati.\n")
        return False

    print(f"[NETWORK] Memeriksa interface '{INTERFACE}' di Linux (Raspberry Pi)...")
    res = subprocess.run(["ip", "link", "show", INTERFACE], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[NETWORK] ❌ GAGAL: Interface '{INTERFACE}' tidak ditemukan.")
        return False
        
    print(f"[NETWORK] Memasang IP {TARGET_IP}/{PREFIX} di '{INTERFACE}'...")
    try:
        cmd = f"ip addr add {TARGET_IP}/{PREFIX} dev {INTERFACE}"
        res_ip = subprocess.run(cmd.split(), capture_output=True, text=True)
        
        if res_ip.returncode != 0 and "File exists" not in res_ip.stderr:
            print(f"[NETWORK] ❌ GAGAL menjalankan 'ip addr': {res_ip.stderr}")
            return False
            
        subprocess.run(["ip", "link", "set", INTERFACE, "up"], check=True)
        print(f"[NETWORK] ✅ SUKSES: Drone (Raspberry Pi) sekarang memiliki IP {TARGET_IP} pada {INTERFACE}!")
        return True
    except Exception as e:
        print(f"[NETWORK] ❌ Error saat mengeksekusi perintah ip: {e}")
        return False
