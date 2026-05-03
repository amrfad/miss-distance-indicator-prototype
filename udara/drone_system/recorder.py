"""
Audio Recording Module
Mengelola recording audio multi-channel via arecord
"""

import subprocess
import shlex
import re
import numpy as np
from .config import (
    CHANNELS, 
    DEVICE_PROFILES,
    get_take_indices
)
from .config_manager import get_global_config_manager


class AudioRecorder:
    """Mengelola recording audio multi-channel via arecord dengan probing capability"""
    
    def __init__(self, device=None, rate=None):
        """
        Initialize audio recorder
        
        Args:
            device (str): ALSA device identifier (e.g., "hw:2,0")
            rate (int): Sample rate dalam Hz
        """
        cfg = get_global_config_manager().get_config()
        self.device = device if device is not None else cfg.get("arecord_device", "hw:2,0")
        self.rate = rate if rate is not None else cfg.get("sample_rate", 48000)
        self.process = None
        self.output_path = None
        
        # Active configuration
        cfg = get_global_config_manager().get_config()
        active_prof = cfg.get("active_profile", "H8")
        self.active_profile_name = active_prof
        self.active_channels = CHANNELS
        self.active_format = "S24_3LE"
        self.active_take_indices = get_take_indices(active_prof, cfg.get("num_mics_h8", 6))
        
        # Configure initial profile
        self.configure_profile(active_prof)
        
    def configure_profile(self, profile_name):
        """Set active profile"""
        if profile_name in DEVICE_PROFILES:
            cfg = get_global_config_manager().get_config()
            num_mics_h8 = cfg.get("num_mics_h8", 6)
            self.active_profile_name = profile_name
            profile = DEVICE_PROFILES[profile_name]
            self.active_channels = profile["channels"]
            self.active_format = profile["format"]
            self.active_take_indices = get_take_indices(profile_name, num_mics_h8)
            num_mics = num_mics_h8 if profile_name == "H8" else profile.get("num_mics", 4)
            print(f"[RECORDER] Profile set to {profile_name} ({num_mics} mics)")
        else:
            print(f"[WARNING] Profile {profile_name} not found, using defaults")

    def _extract_format_from_line(self, line):
        """Extract format token from line starting with -"""
        if line.startswith("-"):
            parts = line.lstrip("- ").split()
            if parts:
                return parts[0]
        return None

    def _extract_channels_from_line(self, line):
        """Extract channel count from line"""
        if "CHANNELS" in line.upper() or line.lower().startswith("channels"):
            m = re.search(r"(\d+)", line)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, TypeError):
                    pass
        return None

    def _parse_arecord_dump(self, output):
        """Parse output dari arecord --dump-hw-params"""
        formats = []
        max_ch = None

        for line in output.splitlines():
            l = line.strip()
            
            # Parse formats
            fmt = self._extract_format_from_line(l)
            if fmt:
                formats.append(fmt)
                continue

            # Parse channels
            ch = self._extract_channels_from_line(l)
            if ch is not None:
                max_ch = ch
                        
        return formats, max_ch

    def probe_device(self):
        """
        Probe device untuk mengetahui format dan max channels yang tersedia.
        Updates self.active_format dan self.active_channels berdasarkan hasil probe.
        """
        print(f"[RECORDER] Probing device {self.device}...")
        try:
            res = subprocess.run(
                ["arecord", "-D", self.device, "--dump-hw-params"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5
            )
            out = res.stdout or ""
        except Exception as e:
            print(f"[WARNING] Gagal mem-probe device {self.device}: {e}")
            return

        formats, max_ch = self._parse_arecord_dump(out)

        # Update Format
        if formats:
            preferred = ["S24_3LE", "S32_LE", "FLOAT_LE", "S16_LE"]
            # Coba cari format profile di daftar available
            if self.active_format in formats:
                chosen_format = self.active_format
            else:
                # Jika tidak ada, cari yang preferred
                chosen_format = next((p for p in preferred if p in formats), formats[0])
            
            print(f"[RECORDER] Device supports: {formats}. Choosing: {chosen_format}")
            self.active_format = chosen_format
        else:
            print("[RECORDER] Could not detect formats, keeping default")

        # Update Channels
        if max_ch is not None and self.active_channels > max_ch:
            print(f"[RECORDER] Device max channels {max_ch} < requested {self.active_channels}. Adjusting.")
            self.active_channels = max_ch
        
        # Update Take Indices if needed
        self._adjust_take_indices()

    def _adjust_take_indices(self):
        """Adjust take_indices jika channel yang tersedia kurang dari yang diminta"""
        cfg = get_global_config_manager().get_config()
        num_mics_h8 = cfg.get("num_mics_h8", 6)
        
        profile = DEVICE_PROFILES.get(self.active_profile_name, DEVICE_PROFILES["H6E"])
        num_mics = num_mics_h8 if self.active_profile_name == "H8" else profile.get("num_mics", 4)
        
        # Ambil indices yang sesuai dengan jumlah mic yang dikonfigurasi
        profile_indices = get_take_indices(self.active_profile_name, num_mics_h8)
        
        # Jika semua index profile ada dalam range channel aktif, gunakan itu
        if all(idx < self.active_channels for idx in profile_indices):
            self.active_take_indices = profile_indices
        else:
            # Jika tidak, buat indices baru yang tersebar merata
            num_wanted = num_mics
            if self.active_channels < num_wanted:
                self.active_take_indices = tuple(range(self.active_channels))
            else:
                self.active_take_indices = tuple(np.linspace(0, self.active_channels - 1, num=num_wanted, dtype=int))
            
            print(f"[RECORDER] Adjusted take_indices to {self.active_take_indices}")

    def start_recording(self, output_path):
        """
        Mulai recording tanpa durasi (continuous)
        
        Args:
            output_path (str): Path untuk menyimpan file WAV
            
        Returns:
            bool: True jika berhasil, False jika gagal
        """
        if self.process is not None and self.process.poll() is None:
            print("[ERROR] Recording sudah berjalan")
            return False
            
        # Probe device dulu sebelum start
        self.probe_device()
            
        self.output_path = output_path
        cmd = [
            "arecord",
            "-D", self.device,
            "-f", self.active_format,
            "-r", str(self.rate),
            "-c", str(self.active_channels),
            output_path
        ]
        
        try:
            print(f"[RECORDING] Running: {' '.join(shlex.quote(x) for x in cmd)}")
            # Redirect stdout/stderr agar tidak mengganggu output program
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            
            # VERIFIKASI: Tunggu sebentar untuk memastikan process tidak crash
            import time
            time.sleep(1.0)  # Tunggu 1 detik
            
            if self.process.poll() is not None:
                # Process mati segera setelah start
                err_msg = "Unknown error"
                if self.process.stderr:
                    try:
                        # Baca sisa stderr
                        err_msg = self.process.stderr.read().decode('utf-8').strip()
                    except Exception:
                        pass
                
                print(f"[ERROR] Recording process died immediately. Exit code: {self.process.returncode}")
                print(f"[ARECORD ERROR] {err_msg}")
                self.process = None
                return False
                
            return True
        except Exception as e:
            print(f"[ERROR] Failed to start recording: {e}")
            return False
    
    def stop_recording(self):
        """
        Stop recording dan tunggu proses selesai
        
        Returns:
            bool: True jika berhasil stop, False jika gagal
        """
        if self.process is None or self.process.poll() is not None:
            print("[WARNING] Recording tidak aktif")
            return False
            
        try:
            cfg = get_global_config_manager().get_config()
            terminate_timeout = cfg.get("arecord_terminate_timeout", 3)
            
            # Terminate process dengan gentle signal
            self.process.terminate()
            self.process.wait(timeout=terminate_timeout)
            print("[RECORDING] Stopped")
        except subprocess.TimeoutExpired:
            # Jika tidak terminate dalam timeout, paksa kill
            self.process.kill()
            print("[RECORDING] Force killed")
        except Exception as e:
            print(f"[ERROR] Failed to stop recording: {e}")
            return False
            
        # Check stderr for errors
        if self.process.stderr:
            try:
                err = self.process.stderr.read().decode('utf-8')
                if err:
                    print(f"[ARECORD STDERR]\n{err}")
            except Exception:
                pass
                
        return True
    
    def is_recording(self):
        """
        Cek apakah sedang recording
        
        Returns:
            bool: True jika sedang recording, False jika tidak
        """
        return self.process is not None and self.process.poll() is None
    
    def get_status(self):
        """
        Dapatkan status recording
        
        Returns:
            dict: Dictionary berisi status recording
        """
        cfg = get_global_config_manager().get_config()
        num_mics_h8 = cfg.get("num_mics_h8", 6)
        profile = DEVICE_PROFILES.get(self.active_profile_name, {})
        num_mics = num_mics_h8 if self.active_profile_name == "H8" else profile.get("num_mics", 4)
        
        return {
            "is_recording": self.is_recording(),
            "output_path": self.output_path,
            "device": self.device,
            "sample_rate": self.rate,
            "channels": self.active_channels,
            "format": self.active_format,
            "profile": self.active_profile_name,
            "num_mics": num_mics,
            "take_indices": self.active_take_indices
        }
    
    def get_active_take_indices(self):
        """Return indices channel yang aktif digunakan"""
        return self.active_take_indices

