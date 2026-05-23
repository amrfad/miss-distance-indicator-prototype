import sys
import os
import platform
import subprocess
import ctypes

# Atur IP untuk PC Darat
TARGET_IP = "10.99.99.1"
PREFIX = "24"            # Subnet mask (24 = 255.255.255.0)

def is_admin():
    """Mengecek apakah Python dijalankan dengan hak akses Administrator/Root."""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() == 1
        else: # Linux/Mac
            return os.geteuid() == 0
    except Exception:
        return False

def setup_windows(ip, prefix):
    print("Mendeteksi adapter Ethernet yang sedang aktif di Windows...")
    
    # Cari adapter Ethernet yg colok LAN (Status = Up) 
    ps_find_cmd = (
        "(Get-NetAdapter | Where-Object {$_.Status -eq 'Up' -and "
        "($_.Name -like '*Ethernet*' -or $_.Name -like '*LAN*')}).Name | Select-Object -First 1"
    )
    
    result = subprocess.run(["powershell", "-Command", ps_find_cmd], capture_output=True, text=True)
    adapter_name = result.stdout.strip()
    
    if not adapter_name:
        print("[NETWORK] ❌ GAGAL: Tidak ditemukan adapter kabel yang sedang terhubung.")
        print("[NETWORK] TIPS: Pastikan PC Darat dan Raspberry Pi sudah dihubungkan dengan kabel LAN.")
        return False
        
    print(f"[NETWORK] ✅ Ditemukan adapter kabel aktif: '{adapter_name}'")
    print(f"[NETWORK] Memasang IP {ip}/{prefix} ke '{adapter_name}'...")
    
    ps_set_cmd = f"""
    $adapter = "{adapter_name}"
    $ip = "{ip}"
    $prefix = {prefix}
    
    Remove-NetIPAddress -InterfaceAlias $adapter -IPAddress $ip -Confirm:$false -ErrorAction SilentlyContinue
    New-NetIPAddress -InterfaceAlias $adapter -IPAddress $ip -PrefixLength $prefix -ErrorAction Stop
    """
    
    try:
        res = subprocess.run(["powershell", "-Command", ps_set_cmd], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[NETWORK] ✅ SUKSES: Windows sekarang memiliki IP {ip}!")
            return True
        else:
            print(f"[NETWORK] ❌ GAGAL mengatur IP. Response: {res.stderr}")
            return False
    except Exception as e:
        print(f"[NETWORK] ❌ Error saat menjalankan PowerShell: {e}")
        return False

def setup_linux(ip, prefix, interface="eth0"):
    print(f"[NETWORK] Memeriksa interface '{interface}' di Linux...")
    
    res = subprocess.run(["ip", "link", "show", interface], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[NETWORK] ❌ GAGAL: Interface '{interface}' tidak ditemukan di sistem ini.")
        return False
        
    print(f"[NETWORK] Memasang IP {ip}/{prefix} di '{interface}'...")
    
    try:
        cmd = f"ip addr add {ip}/{prefix} dev {interface}"
        res_ip = subprocess.run(cmd.split(), capture_output=True, text=True)
        
        if res_ip.returncode != 0 and "File exists" not in res_ip.stderr:
            print(f"[NETWORK] ❌ GAGAL menjalankan 'ip addr': {res_ip.stderr}")
            return False
            
        subprocess.run(["ip", "link", "set", interface, "up"], check=True)
        print(f"[NETWORK] ✅ SUKSES: Linux sekarang memiliki IP {ip}!")
        return True
    except Exception as e:
        print(f"[NETWORK] ❌ Error saat mengeksekusi perintah ip: {e}")
        return False

def init_network():
    """Entry point untuk setup auto-network spesifik PC Darat."""
    if not is_admin():
        print("[NETWORK] ⚠️ PERINGATAN: Program Ground darat/main.py tidak dijalankan sebagai Administrator.")
        print("[NETWORK] Automasi IP statis 10.99.99.1 dilewati. Pastikan PC menggunakan IP yang benar.\n")
        return False

    os_type = platform.system()
    
    if os_type == "Windows":
        return setup_windows(TARGET_IP, PREFIX)
    elif os_type == "Linux":
        return setup_linux(TARGET_IP, PREFIX)
    else:
        print(f"[NETWORK] ⚠️ Automasi jaringan tidak didukung pada {os_type}.")
        return False
