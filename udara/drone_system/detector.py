"""
Event Detection Module
Deteksi event menggunakan sensor fusion dari multiple microphones
"""

import os
import glob
import numpy as np
import librosa
from .config_manager import get_global_config_manager


class EventDetector:
    """Deteksi event menggunakan consensus dari multiple microphones"""
    
    def __init__(self):
        """
        Initialize event detector
        
        Args:
            min_duration (float): Durasi minimal event yang valid (detik)
            max_gap (float): Gap maksimal untuk merge event (detik)
            detect_ratio (float): Threshold deteksi (relatif terhadap max)
            filter_ratio (float): Threshold filter final (relatif terhadap max)
            ignore_time (float): Abaikan deteksi di awal (detik)
            hop_length (int): Hop length untuk RMS calculation
            frame_length (int): Frame length untuk RMS calculation
        """
        cfg = get_global_config_manager().get_config()
        self.min_duration = cfg.get("min_duration", 0.25)
        self.max_gap = cfg.get("max_gap", 0.1)
        self.detect_ratio = cfg.get("detect_ratio", 0.20)
        self.filter_ratio = cfg.get("filter_ratio", 0.40)
        self.ignore_time = cfg.get("ignore_time", 0.5)
        # Hop dan frame length tidak ada di runtime config UI, gunakan nilai hardcoded default
        self.hop_length = 512
        self.frame_length = 1024
        self.normalization_percentile = 99.9
        
    def detect_events(self, folder_path, file_pattern="*_filtered.wav"):
        """
        Deteksi event menggunakan consensus dari multiple mics
        
        Args:
            folder_path (str): Path folder berisi file audio
            file_pattern (str): Pattern file yang akan dianalisis
            
        Returns:
            list: List of (start_time, end_time) tuples
        """
        search_path = os.path.join(folder_path, file_pattern)
        files = sorted(glob.glob(search_path))
        
        if not files:
            print(f"[DETECT] Tidak ada file matching '{file_pattern}'")
            return []
            
        print(f"[DETECT] Analyzing {len(files)} files")
        
        # Load dan normalisasi setiap file
        rms_list, sr, min_len = self._load_and_normalize_files(files)
        
        if not rms_list:
            print("[DETECT] Tidak ada data yang bisa diproses")
            return []
        
        # SENSOR FUSION: rata-rata energi dari semua mic
        combined_rms = np.mean(rms_list, axis=0)
        times = librosa.frames_to_time(range(min_len), sr=sr, hop_length=self.hop_length)
        
        # Calculate thresholds
        global_max = np.max(combined_rms)
        det_thresh = global_max * self.detect_ratio
        sel_thresh = global_max * self.filter_ratio
        
        print(f"[DETECT] Max Energy: {global_max:.4f}")
        print(f"[DETECT] Detect Threshold: {det_thresh:.4f} ({self.detect_ratio*100}%)")
        print(f"[DETECT] Select Threshold: {sel_thresh:.4f} ({self.filter_ratio*100}%)")
        
        # Deteksi raw events
        raw_events = self._detect_raw_events(combined_rms, times, det_thresh)
        
        if not raw_events:
            print("[DETECT] Tidak ada event terdeteksi")
            return []
        
        # Merge events yang berdekatan
        merged_events = self._merge_events(raw_events, times)
        
        # Filter berdasarkan durasi dan kekuatan
        final_events = self._filter_events(merged_events, combined_rms, times, global_max)
        
        print(f"[DETECT] Found {len(final_events)} valid events")
        for i, (start, end) in enumerate(final_events):
            print(f"  Event {i+1}: {start:.3f}s - {end:.3f}s ({end-start:.3f}s)")
            
        return final_events
    
    def _load_and_normalize_files(self, files):
        """
        Load file dan normalisasi RMS energy
        
        Args:
            files (list): List path file audio
            
        Returns:
            tuple: (rms_list, sr, min_len)
        """
        rms_list = []
        sr = None
        min_len = float('inf')
        
        for f in files:
            try:
                y, s = librosa.load(f, sr=None)
                if sr is None:
                    sr = s
                    
                # Hitung RMS energy
                rms = librosa.feature.rms(
                    y=y, 
                    frame_length=self.frame_length, 
                    hop_length=self.hop_length
                )[0]
                
                # Normalisasi per-channel untuk mencegah bias dari mic yang lebih keras
                peak_val = np.percentile(rms, self.normalization_percentile)
                if peak_val > 0:
                    rms_norm = rms / peak_val
                else:
                    rms_norm = rms
                    
                rms_list.append(rms_norm)
                if len(rms_norm) < min_len:
                    min_len = len(rms_norm)
                    
            except Exception as e:
                print(f"[ERROR] Load file {os.path.basename(f)}: {e}")
                continue
        
        # Potong ke panjang yang sama
        if rms_list:
            rms_list = [r[:min_len] for r in rms_list]
        
        return rms_list, sr, min_len
    
    def _detect_raw_events(self, combined_rms, times, threshold):
        """
        Deteksi raw events dari sinyal gabungan
        
        Args:
            combined_rms (np.ndarray): RMS energy yang sudah di-fuse
            times (np.ndarray): Array waktu
            threshold (float): Threshold deteksi
            
        Returns:
            list: List of (start_idx, end_idx) tuples
        """
        raw_events = []
        in_event = False
        start_idx = 0
        
        for i, energy in enumerate(combined_rms):
            # Abaikan deteksi di awal recording
            if times[i] < self.ignore_time:
                continue
                
            if energy > threshold:
                if not in_event:
                    in_event = True
                    start_idx = i
            else:
                if in_event:
                    in_event = False
                    raw_events.append((start_idx, i))
        
        # Jika masih dalam event di akhir
        if in_event:
            raw_events.append((start_idx, len(combined_rms) - 1))
            
        return raw_events
    
    def _merge_events(self, raw_events, times):
        """
        Merge events yang gap-nya kecil
        
        Args:
            raw_events (list): List of (start_idx, end_idx)
            times (np.ndarray): Array waktu
            
        Returns:
            list: List of (start_idx, end_idx) yang sudah di-merge
        """
        if not raw_events:
            return []
            
        merged = []
        current_start, current_end = raw_events[0]
        
        for i in range(1, len(raw_events)):
            next_start, next_end = raw_events[i]
            gap_time = times[next_start] - times[current_end]
            
            if gap_time <= self.max_gap:
                # Merge dengan event sebelumnya
                current_end = max(current_end, next_end)
            else:
                # Simpan event sebelumnya dan mulai yang baru
                merged.append((current_start, current_end))
                current_start, current_end = next_start, next_end
                
        merged.append((current_start, current_end))
        return merged
    
    def _filter_events(self, merged_events, combined_rms, times, global_max):
        """
        Filter events berdasarkan durasi dan kekuatan
        
        Args:
            merged_events (list): List of (start_idx, end_idx)
            combined_rms (np.ndarray): RMS energy yang sudah di-fuse
            times (np.ndarray): Array waktu
            global_max (float): Nilai maksimum global
            
        Returns:
            list: List of (start_time, end_time) yang valid
        """
        final = []
        
        for start_idx, end_idx in merged_events:
            start_t = times[start_idx]
            end_t = times[end_idx]
            durasi = end_t - start_t
            
            # Cek kekuatan event
            event_data = combined_rms[start_idx:end_idx+1]
            local_peak = np.max(event_data) if len(event_data) > 0 else 0
            ratio = local_peak / global_max if global_max > 0 else 0
            
            # Validasi: harus memenuhi durasi minimal dan kekuatan minimal
            if ratio >= self.filter_ratio and durasi >= self.min_duration:
                final.append((start_t, end_t))
                
        return final
    
    def update_parameters(self, **kwargs):
        """
        Update detection parameters
        
        Args:
            **kwargs: Parameter yang ingin diupdate
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                print(f"[DETECT] Updated {key} = {value}")
            else:
                print(f"[WARNING] Unknown parameter: {key}")
