"""
Audio Processing Module
Mengelola ekstraksi channel dan noise reduction filtering.

Filtering kini menggunakan arsitektur plugin registry (Strategy Pattern).
Tambahkan metode filter baru di builtin_filters/ atau custom_filters/
tanpa mengubah file ini.
"""

import os
import ctypes
import numpy as np
import soundfile as sf
from ..core.config import CHANNEL_INDICES
from ..core.config_manager import get_global_config_manager
from ..tdoa import filter_registry

# Backward compatibility for main.py
try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    NOISEREDUCE_AVAILABLE = False


# Mute ALSA warnings (Linux)
try:
    _asound = ctypes.CDLL('libasound.so.2')
    try:
        _asound.snd_lib_error_set_handler(ctypes.c_void_p(0))
    except Exception:
        pass
except Exception:
    pass


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
        print(f"[PROCESSOR] Available filters: {filter_registry.list_available_methods()}")
        
    def extract_channels(self, wav_path, output_dir, sr_override=None, channel_indices=None, normalize=None, mic_names=None):
        """
        Ekstrak channel tertentu dari file multi-channel
        
        Args:
            wav_path (str): Path ke file WAV input
            output_dir (str): Directory untuk menyimpan file output
            sr_override (int, optional): Override sample rate jika perlu
            channel_indices (tuple, optional): Override indices channel yang akan diekstrak
            normalize (bool): Lakukan normalisasi output
            mic_names (list[str], optional): Nama asli tiap mic untuk penamaan file output
            
        Returns:
            tuple: (original_files, data, sr, actual_duration)
        """
        if normalize is None:
            normalize = get_global_config_manager().get_config().get("normalize", False)
            
        if not os.path.exists(wav_path):
            print(f"[ERROR] File tidak ditemukan: {wav_path}")
            return [], None, None, 0
            
        # Use provided indices or default
        indices_to_use = channel_indices if channel_indices is not None else self.channel_indices
        names_to_use = list(mic_names) if mic_names is not None else [f"mic{i}" for i in range(len(indices_to_use))]
            
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
                mname = names_to_use[i] if i < len(names_to_use) else f"mic{i}"
                if idx >= n_ch:
                    print(f"[WARNING] Channel {idx} tidak ada, skip {mname}")
                    continue
                    
                ch = data[:, idx]
                
                # Normalisasi jika diminta (penting untuk 32-bit float > 0dB)
                if normalize:
                    peak = np.max(np.abs(ch))
                    if peak > 0:
                        ch = ch / peak
                
                fname = os.path.join(output_dir, f"{mname}_original.wav")
                
                # Write dengan format yang sesuai dari device profile
                try:
                    sf.write(fname, ch, sr, subtype=self.sf_subtype)
                    print(f"[EXTRACT] Saved {mname} as {self.sf_subtype}")
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
                       channel_indices=None, mic_names=None):
        """
        Filter setiap channel menggunakan metode yang dikonfigurasi via filter_registry.

        Metode filtering dan parameter-nya dibaca dari ConfigManager:
          - cfg["filter_method"]: key metode (default: "spectral_gating")
          - cfg["filter_configs"][method_key]: dict parameter untuk metode terpilih

        Args:
            data (np.ndarray): Audio data 2D (n_samples, n_channels)
            sr (int): Sample rate
            output_dir (str): Directory untuk menyimpan file output
            channel_indices (tuple, optional): Override indices channel

        Returns:
            tuple: (filtered_files, filtered_data)
                - filtered_files (list): List path file yang sudah difilter
                - filtered_data (np.ndarray): Audio data yang sudah difilter
        """
        if data is None:
            return [], None

        cfg = get_global_config_manager().get_config()

        # ── Resolusi metode filter via registry ────────────────────────
        method_key = cfg.get("filter_method", filter_registry.DEFAULT_METHOD)
        FilterClass = filter_registry.get_method_class(method_key)

        if FilterClass is None:
            print(f"[FILTER] Tidak ada filter yang tersedia, melewati filtering")
            return [], data

        # Ambil parameter khusus untuk metode terpilih
        method_params = cfg.get("filter_configs", {}).get(method_key, {})
        filter_instance = FilterClass(**method_params)
        print(f"[FILTER] Menggunakan metode: '{method_key}' ({FilterClass.get_display_name()})")

        if not FilterClass.is_available():
            print(f"[SKIP] Filter '{method_key}' tidak tersedia di environment ini")
            return [], data

        # ── Persiapan filtered_data array ─────────────────────────────
        # Catatan: setiap FilterClass bertanggung jawab atas trimming internalnya
        # (mis. SpectralGatingFilter melakukan trim 0.8s). Hasil apply() bisa
        # lebih pendek dari input jika metode melakukan trimming.
        # Untuk konsistensi multi-channel, kita inisiasi filtered_data dari data asli
        # dan overwrite per-channel setelah filtering.
        filtered_data = data.copy()
        indices_to_use = channel_indices if channel_indices is not None else self.channel_indices
        names_to_use = list(mic_names) if mic_names is not None else [f"mic{i}" for i in range(len(indices_to_use))]
        filtered_files = []
        n_ch = data.shape[1]

        for i, idx in enumerate(indices_to_use):
            if idx >= n_ch:
                continue

            mname = names_to_use[i] if i < len(names_to_use) else f"mic{i}"
            ch = data[:, idx]
            print(f"[FILTER] Processing {mname} (channel {idx})...")

            try:
                chf = filter_instance.apply(ch, sr)

                # Sinkronisasi panjang: jika filter melakukan trimming,
                # potong filtered_data ke panjang terpendek yang konsisten
                if chf.shape[0] != filtered_data.shape[0]:
                    new_len = chf.shape[0]
                    if new_len < filtered_data.shape[0]:
                        filtered_data = filtered_data[:new_len, :]
                    else:
                        chf = chf[:filtered_data.shape[0]]

                filtered_data[:, idx] = chf

                # Simpan file hasil
                fname = os.path.join(output_dir, f"{mname}_filtered.wav")
                try:
                    sf.write(fname, chf, sr, subtype=self.sf_subtype)
                except Exception as e:
                    print(f"[WARNING] Failed to save as {self.sf_subtype}, using default: {e}")
                    sf.write(fname, chf, sr)

                filtered_files.append(fname)

            except Exception as e:
                print(f"[ERROR] Filter {mname} failed: {e}")

        print(f"[FILTER] Completed {len(filtered_files)} files dengan metode '{method_key}'")
        return filtered_files, filtered_data
    
    def save_event_clips(self, data, sr, events, output_dir, padding=0.25, channel_indices=None, mic_names=None):
        """
        Potong dan simpan klip audio untuk setiap event
        
        Args:
            data (np.ndarray): Audio data 2D (n_samples, n_channels)
            sr (int): Sample rate
            events (list): List of (start_time, end_time) tuples
            output_dir (str): Directory session
            padding (float): Padding waktu dalam detik (sebelum dan sesudah)
            channel_indices (tuple, optional): Override indices channel
            mic_names (list[str], optional): Nama asli tiap mic
            
        Returns:
            list: List of event dicts dengan info file path
        """
        if data is None or not events:
            return []
            
        indices_to_use = channel_indices if channel_indices is not None else self.channel_indices
        names_to_use = list(mic_names) if mic_names is not None else [f"mic{i}" for i in range(len(indices_to_use))]
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
                    
                mname = names_to_use[ch_idx] if ch_idx < len(names_to_use) else f"mic{ch_idx}"
                # Slice audio
                audio_slice = data[start_sample:end_sample, original_idx]
                
                # Save file
                filename = f"{mname}.wav"
                filepath = os.path.join(event_dir, filename)
                
                try:
                    sf.write(filepath, audio_slice, sr, subtype=self.sf_subtype)
                except Exception as e:
                    print(f"[WARNING] Failed to save as {self.sf_subtype}, using default: {e}")
                    sf.write(filepath, audio_slice, sr)
                    
                event_files[mname] = os.path.join(event_dir_name, filename)
            
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
            dict: Dictionary berisi status feature dan daftar filter yang tersedia
        """
        available_methods = filter_registry.list_available_methods()
        return {
            "soundfile": True,  # Selalu ada karena sudah di-import
            "filter_methods": available_methods,
            "active_filter": get_global_config_manager().get_config().get(
                "filter_method", filter_registry.DEFAULT_METHOD
            ),
        }
