"""
Main System Controller
Mengkoordinasi semua module untuk sistem drone audio detection
"""

import os
import time
import uuid
from datetime import datetime
from .recorder import AudioRecorder
from .processor import AudioProcessor
from .detector import EventDetector
from .logger import DataLogger
from .tdoa import calculate_all_tdoa
from .comms import SerialCommunicator
from .config import (
    BASE_OUTPUT_DIR,
    EVENTS_CSV,
    EVENTS_JSON,
    TDOA_JSON,
    EVENT_PADDING_SEC,
    TIMESTAMP_FORMAT,
    LOG_TIMESTAMP_FORMAT,
    POST_RECORDING_DELAY,
    SAMPLE_RATE,
    OPERATION_MODE,
    DEVICE_PROFILES
)


class DroneAudioSystem:
    """Sistem utama yang mengkoordinasi semua module"""
    
    def __init__(self):
        """Initialize sistem dengan semua module yang diperlukan"""
        self.recorder = AudioRecorder()
        
        # Initialize processor dengan format dari recorder
        rec_status = self.recorder.get_status()
        output_format = rec_status.get("format", "S24_3LE")
        self.processor = AudioProcessor(output_format=output_format)
        
        self.detector = EventDetector()
        self.comms = SerialCommunicator()
        
        self.current_session_dir = None
        self.current_wav_path = None
        self.recording_start_time = None
        
        # Buat base output directory jika belum ada
        os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
        
        print(f"[SYSTEM] DroneAudioSystem initialized (format: {output_format})")
        
    def start_recording(self):
        """
        Mulai recording session baru
        
        Returns:
            tuple: (success, message)
                - success (bool): True jika berhasil
                - message (str): Pesan status
        """
        if self.recorder.is_recording():
            return False, "Recording sudah berjalan"
            
        # Buat session folder dengan timestamp dan UID
        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        uid = uuid.uuid4().hex[:6]
        session_id = f"session_{timestamp}_{uid}"
        self.current_session_dir = os.path.join(BASE_OUTPUT_DIR, session_id)
        os.makedirs(self.current_session_dir, exist_ok=True)
        
        # Path untuk raw recording
        self.current_wav_path = os.path.join(self.current_session_dir, "raw_12ch.wav")
        
        # Mulai recording
        success = self.recorder.start_recording(self.current_wav_path)
        if success:
            self.recording_start_time = time.time()
            return True, f"Recording started: {session_id}"
        else:
            return False, "Failed to start recording"
    
    def stop_and_process(self):
        """
        Stop recording dan proses audio (filter + detect + save)
        
        Returns:
            tuple: (success, message, events)
                - success (bool): True jika berhasil
                - message (str): Pesan status
                - events (list): List of detected events
        """
        if not self.recorder.is_recording():
            return False, "Tidak ada recording aktif", None
            
        # Stop recording
        self.recorder.stop_recording()
        time.sleep(POST_RECORDING_DELAY)  # Tunggu file selesai ditulis
        
        if not os.path.exists(self.current_wav_path):
            return False, "File recording tidak ditemukan", None
            
        print("\n" + "="*50)
        print("MEMPROSES AUDIO")
        print("="*50)
        
        try:
            # Get active take indices from recorder (based on probe result)
            active_indices = self.recorder.get_active_take_indices()
            print(f"[SYSTEM] Using channel indices: {active_indices}")

            # 1. Extract channels
            original_files, data, sr, duration = self.processor.extract_channels(
                self.current_wav_path, 
                self.current_session_dir,
                sr_override=SAMPLE_RATE,
                channel_indices=active_indices
            )
            
            if not original_files:
                return False, "Ekstraksi channel gagal", None
            
            # 2. Filter channels
            filtered_files, filtered_data = self.processor.filter_channels(
                data, 
                sr, 
                self.current_session_dir,
                channel_indices=active_indices
            )
            
            # 3. Detect events
            events = self.detector.detect_events(self.current_session_dir)
            
            # 4. Cut and Save Event Clips (Using Filtered Data)
            processed_events = self.processor.save_event_clips(
                filtered_data, 
                sr, 
                events, 
                self.current_session_dir,
                padding=EVENT_PADDING_SEC,
                channel_indices=active_indices
            )
            
            # 5. Calculate TDOA for each event
            print("[SYSTEM] Calculating TDOA...")
            tdoa_results = []
            for event in processed_events:
                # Re-slice filtered data based on padded times
                start_sample = int(event['padded_start'] * sr)
                end_sample = int(event['padded_end'] * sr)
                
                # Ensure indices are within bounds
                start_sample = max(0, start_sample)
                end_sample = min(filtered_data.shape[0], end_sample)
                
                event_audio = filtered_data[start_sample:end_sample, :]
                
                # Calculate TDOA
                event_tdoa = calculate_all_tdoa(event_audio, sr, channel_indices=active_indices)
                
                tdoa_results.append({
                    "event_number": event['event_number'],
                    "tdoa": event_tdoa
                })

            # 6. Save results to JSON
            session_id = os.path.basename(self.current_session_dir)
            timestamp = datetime.now().strftime(LOG_TIMESTAMP_FORMAT)
            json_path = os.path.join(self.current_session_dir, EVENTS_JSON)
            tdoa_json_path = os.path.join(self.current_session_dir, TDOA_JSON)
            
            # Collect extra info from recorder
            rec_status = self.recorder.get_status()
            profile_name = rec_status.get("profile", "Unknown")
            profile = DEVICE_PROFILES.get(profile_name, {})
            num_mics = profile.get("num_mics", 4)
            num_tdoa_pairs = num_mics * (num_mics - 1) // 2  # C(n,2) = n*(n-1)/2
            
            extra_info = {
                "device_profile": profile_name,
                "format": rec_status.get("format", "Unknown"),
                "channels": rec_status.get("channels", 0),
                "num_mics": num_mics,
                "num_tdoa_pairs": num_tdoa_pairs
            }
            
            # Save Events JSON
            DataLogger.save_events_json(
                json_path, 
                session_id, 
                timestamp, 
                processed_events, 
                duration, 
                sr, 
                extra_info=extra_info
            )
            
            # Save TDOA JSON
            DataLogger.save_events_json(
                tdoa_json_path,
                session_id,
                timestamp,
                tdoa_results, # Pass TDOA results as events data
                duration,
                sr,
                extra_info={"type": "TDOA_RESULTS", **extra_info}
            )
            
            print("\n" + "="*50)
            print("PROSES SELESAI")
            print("="*50)
            print(f"Session: {session_id}")
            print(f"Duration: {duration:.2f}s")
            print(f"Events detected: {len(events)}")
            print(f"Results saved to: {json_path}")
            print(f"TDOA saved to: {tdoa_json_path}")
            
            # 7. Send TDOA JSON to Ground (hanya jika ONLINE mode)
            if OPERATION_MODE == "ONLINE":
                print("[SYSTEM] Sending TDOA results to ground...")
                if self.comms.send_file(tdoa_json_path):
                    print("[SYSTEM] TDOA results sent successfully.")
                else:
                    print("[SYSTEM] Failed to send TDOA results.")
            else:
                print("[SYSTEM] OFFLINE mode - skipping file transmission")
            
            print("="*50 + "\n")
            
            # Reset state
            self._reset_state()
            
            return True, f"Processed: {len(events)} events detected", events
            
        except Exception as e:
            print(f"[ERROR] Processing failed: {e}")
            self._reset_state()
            return False, f"Processing error: {str(e)}", None
    
    def get_status(self):
        """
        Dapatkan status sistem
        
        Returns:
            tuple: (success, status_message, data)
                - success (bool): True jika berhasil
                - status_message (str): Status string
                - data (dict): Additional status data
        """
        if self.recorder.is_recording():
            elapsed = time.time() - self.recording_start_time if self.recording_start_time else 0
            return True, f"RECORDING ({elapsed:.1f}s)", {"elapsed": elapsed}
        else:
            return True, "IDLE", None
    
    def _reset_state(self):
        """Reset internal state setelah processing selesai"""
        self.current_session_dir = None
        self.current_wav_path = None
        self.recording_start_time = None
    
    def get_system_info(self):
        """
        Dapatkan informasi lengkap sistem
        
        Returns:
            dict: Dictionary berisi informasi sistem
        """
        return {
            "recorder": self.recorder.get_status(),
            "processor_features": self.processor.get_available_features(),
            "output_directory": BASE_OUTPUT_DIR,
            "events_json_filename": EVENTS_JSON,
            "current_session": self.current_session_dir
        }
