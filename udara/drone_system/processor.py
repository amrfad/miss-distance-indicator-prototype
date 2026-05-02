"""
Audio Processing Module
Mengelola ekstraksi channel dan noise reduction filtering
"""

import os
import ctypes
from contextlib import redirect_stderr
import numpy as np
import soundfile as sf
from .config import (
    CHANNEL_INDICES, 
    PROP_DECREASE, 
    FREQ_MASK_SMOOTH_HZ, 
    TIME_MASK_SMOOTH_MS,
    NORMALIZE,
    STATIONARY
)

# Mute ALSA warnings
try:
    _asound = ctypes.CDLL('libasound.so.2')
    try:
        _asound.snd_lib_error_set_handler(ctypes.c_void_p(0))
    except:
        pass
except:
    pass

# Import noisereduce dengan mute stderr
try:
    with open(os.devnull, "w") as d:
        with redirect_stderr(d):
            import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except Exception:
    NOISEREDUCE_AVAILABLE = False


class AudioProcessor:
    """Mengelola ekstraksi channel dan filtering"""
    
    def __init__(self, channel_indices=CHANNEL_INDICES, output_format="S24_3LE"):
        """
        Initialize audio processor
        
        Args:
            channel_indices (tuple): Indices channel yang akan diekstrak
            output_format (str): Format output untuk penyimpanan (S24_3LE atau S32_LE)
        """
        self.channel_indices = channel_indices
        self.noisereduce_available = NOISEREDUCE_AVAILABLE
        self.output_format = output_format
        
        # Mapping ALSA format ke soundfile subtype
        self.format_mapping = {
            "S24_3LE": "PCM_24",
            "S32_LE": "PCM_32",
            "S16_LE": "PCM_16",
            "FLOAT_LE": "FLOAT"
        }
        
        # Get soundfile subtype
        self.sf_subtype = self.format_mapping.get(output_format, "PCM_24")
        print(f"[PROCESSOR] Output format: {output_format} -> {self.sf_subtype}")
        
        if not self.noisereduce_available:
            print("[WARNING] noisereduce tidak tersedia, filtering akan dilewati")
        
    def extract_channels(self, wav_path, output_dir, sr_override=None, channel_indices=None, normalize=NORMALIZE):
        """
        Ekstrak channel tertentu dari file multi-channel
        
        Args:
            wav_path (str): Path ke file WAV input
            output_dir (str): Directory untuk menyimpan file output
            sr_override (int, optional): Override sample rate jika perlu
            channel_indices (tuple, optional): Override indices channel yang akan diekstrak
            normalize (bool): Lakukan normalisasi output
            
        Returns:
            tuple: (original_files, data, sr, actual_duration)
        """
        if not os.path.exists(wav_path):
            print(f"[ERROR] File tidak ditemukan: {wav_path}")
            return [], None, None, 0
            
        # Use provided indices or default
        indices_to_use = channel_indices if channel_indices is not None else self.channel_indices
            
        try:
            # Load audio file
            data, sr = sf.read(wav_path, always_2d=True)
            if sr_override is not None:
                sr = sr_override
                
            n_samples, n_ch = data.shape
            actual_duration = n_samples / sr if sr else 0.0
            
            print(f"[EXTRACT] Loaded: {n_samples} samples, {n_ch} channels, {sr} Hz")
            print(f"[EXTRACT] Duration: {actual_duration:.2f}s")
            
            # Ekstrak setiap channel yang diminta
            original_files = []
            for i, idx in enumerate(indices_to_use):
                if idx >= n_ch:
                    print(f"[WARNING] Channel {idx} tidak ada, skip mic{i}")
                    continue
                    
                ch = data[:, idx]
                
                # Normalisasi jika diminta (penting untuk 32-bit float > 0dB)
                if normalize:
                    peak = np.max(np.abs(ch))
                    if peak > 0:
                        print(peak) # TODO: delete this later
                        ch = ch / peak
                
                fname = os.path.join(output_dir, f"mic{i}_original.wav")
                
                # Write dengan format yang sesuai dari device profile
                try:
                    sf.write(fname, ch, sr, subtype=self.sf_subtype)
                    print(f"[EXTRACT] Saved mic{i} as {self.sf_subtype}")
                except Exception as e:
                    print(f"[WARNING] Failed to save as {self.sf_subtype}, using default: {e}")
                    sf.write(fname, ch, sr)
                    
                original_files.append(fname)
                
            print(f"[EXTRACT] Extracted {len(original_files)} channels")
            return original_files, data, sr, actual_duration
            
        except Exception as e:
            print(f"[ERROR] Extract failed: {e}")
            return [], None, None, 0
    
    def filter_channels(self, data, sr, output_dir, 
                       prop_decrease=PROP_DECREASE,
                       freq_smooth=FREQ_MASK_SMOOTH_HZ,
                       time_smooth=TIME_MASK_SMOOTH_MS,
                       normalize=NORMALIZE,
                       stationary=STATIONARY,
                       channel_indices=None):
        """
        Filter setiap channel dengan noise reduction
        
        Args:
            data (np.ndarray): Audio data 2D (n_samples, n_channels)
            sr (int): Sample rate
            output_dir (str): Directory untuk menyimpan file output
            prop_decrease (float): Proporsi pengurangan noise (0-1)
            freq_smooth (int): Smoothing di domain frekuensi (Hz)
            time_smooth (int): Smoothing di domain waktu (ms)
            normalize (bool): Normalisasi output
            stationary (bool): Gunakan stationary noise reduction
            channel_indices (tuple, optional): Override indices channel
            
        Returns:
            tuple: (filtered_files, filtered_data)
                - filtered_files (list): List path file yang sudah difilter
                - filtered_data (np.ndarray): Audio data yang sudah difilter
        """
        if not self.noisereduce_available:
            print("[SKIP] Filtering dilewati (noisereduce tidak tersedia)")
            return [], data
            
        if data is None:
            return [], None
            
        # Use provided indices or default
        indices_to_use = channel_indices if channel_indices is not None else self.channel_indices
            
        filtered_files = []
        
        # Calculate trim samples (800ms) to remove spectral gating artifacts
        trim_duration = 0.8
        trim_samples = int(trim_duration * sr)
        n_samples = data.shape[0]
        
        # Initialize filtered_data
        if n_samples > 2 * trim_samples:
            print(f"[FILTER] Trimming {trim_duration}s ({trim_samples} samples) from start and end")
            filtered_data = data[trim_samples:-trim_samples, :].copy()
        else:
            print(f"[WARNING] Audio too short ({n_samples/sr:.2f}s) to trim {trim_duration}s. Keeping original length.")
            trim_samples = 0
            filtered_data = data.copy()
            
        n_ch = data.shape[1]
        
        for i, idx in enumerate(indices_to_use):
            if idx >= n_ch:
                continue
                
            ch = data[:, idx]
            print(f"[FILTER] Processing mic{i}...")
            
            try:
                # Apply noise reduction
                chf = nr.reduce_noise(
                    y=ch, 
                    sr=sr, 
                    stationary=stationary,
                    prop_decrease=prop_decrease,
                    freq_mask_smooth_hz=freq_smooth,
                    time_mask_smooth_ms=time_smooth
                )
                
                # Trim if needed
                if trim_samples > 0:
                    chf = chf[trim_samples:-trim_samples]
                
                # Optional normalization
                if normalize:
                    peak = np.max(np.abs(chf))
                    if peak > 0:
                        chf = chf / peak
                        
                # Clip to valid range
                chf = np.clip(chf, -1.0, 1.0)
                
                # Update filtered data array
                filtered_data[:, idx] = chf
                
                # Save filtered file
                fname = os.path.join(output_dir, f"mic{i}_filtered.wav")
                try:
                    sf.write(fname, chf, sr, subtype=self.sf_subtype)
                except Exception as e:
                    print(f"[WARNING] Failed to save as {self.sf_subtype}, using default: {e}")
                    sf.write(fname, chf, sr)
                    
                filtered_files.append(fname)
                
            except Exception as e:
                print(f"[ERROR] Filter mic{i} failed: {e}")
                
        print(f"[FILTER] Completed {len(filtered_files)} files")
        return filtered_files, filtered_data
    
    def save_event_clips(self, data, sr, events, output_dir, padding=0.25, channel_indices=None):
        """
        Potong dan simpan klip audio untuk setiap event
        
        Args:
            data (np.ndarray): Audio data 2D (n_samples, n_channels)
            sr (int): Sample rate
            events (list): List of (start_time, end_time) tuples
            output_dir (str): Directory session
            padding (float): Padding waktu dalam detik (sebelum dan sesudah)
            channel_indices (tuple, optional): Override indices channel
            
        Returns:
            list: List of event dicts dengan info file path
        """
        if data is None or not events:
            return []
            
        indices_to_use = channel_indices if channel_indices is not None else self.channel_indices
        processed_events = []
        n_samples = data.shape[0]
        
        print(f"[PROCESSOR] Cutting {len(events)} events with {padding}s padding...")
        
        for i, (start_t, end_t) in enumerate(events, 1):
            # Hitung sample indices dengan padding
            start_sample = int(max(0, (start_t - padding) * sr))
            end_sample = int(min(n_samples, (end_t + padding) * sr))
            
            # Buat folder event
            event_dir_name = f"event_{i}"
            event_dir = os.path.join(output_dir, event_dir_name)
            os.makedirs(event_dir, exist_ok=True)
            
            event_files = {}
            
            # Potong dan simpan tiap channel
            for ch_idx, original_idx in enumerate(indices_to_use):
                if original_idx >= data.shape[1]:
                    continue
                    
                # Slice audio
                audio_slice = data[start_sample:end_sample, original_idx]
                
                # Save file
                filename = f"mic{ch_idx}.wav"
                filepath = os.path.join(event_dir, filename)
                
                try:
                    sf.write(filepath, audio_slice, sr, subtype=self.sf_subtype)
                except Exception as e:
                    print(f"[WARNING] Failed to save as {self.sf_subtype}, using default: {e}")
                    sf.write(filepath, audio_slice, sr)
                    
                event_files[f"mic{ch_idx}"] = os.path.join(event_dir_name, filename)
            
            processed_events.append({
                "event_number": i,
                "original_start": start_t,
                "original_end": end_t,
                "padded_start": start_sample / sr,
                "padded_end": end_sample / sr,
                "duration": (end_sample - start_sample) / sr,
                "files": event_files
            })
            
        return processed_events

    def get_available_features(self):
        """
        Dapatkan informasi feature yang tersedia
        
        Returns:
            dict: Dictionary berisi status feature
        """
        return {
            "noisereduce": self.noisereduce_available,
            "soundfile": True,  # Selalu ada karena sudah di-import
        }
