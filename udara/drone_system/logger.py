"""
Data Logger Module
Menyimpan hasil deteksi ke file JSON
"""

import os
import json
import csv
from .config import LOG_TIMESTAMP_FORMAT


class DataLogger:
    """Menyimpan hasil deteksi ke JSON"""
    
    @staticmethod
    def save_events_json(json_path, session_id, timestamp, events_data, duration, sample_rate, extra_info=None):
        """
        Simpan data session dan event ke JSON
        
        Args:
            json_path (str): Path file JSON output
            session_id (str): ID session recording
            timestamp (str): Timestamp session
            events_data (list): List of event dictionaries (dari processor.save_event_clips)
            duration (float): Total durasi recording (detik)
            sample_rate (int): Sample rate audio
            extra_info (dict, optional): Informasi tambahan
        """
        # Buat directory jika belum ada
        os.makedirs(os.path.dirname(json_path) if os.path.dirname(json_path) else ".", exist_ok=True)
        
        data = {
            "session_id": session_id,
            "timestamp": timestamp,
            "total_recording_duration": round(duration, 3),
            "sample_rate": sample_rate,
            "event_count": len(events_data) if events_data else 0,
            "events": events_data if events_data else []
        }
        
        if extra_info:
            data.update(extra_info)
            
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[LOG] Saved session data to {json_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save JSON log: {e}")

    @staticmethod
    def save_events(csv_path, session_id, timestamp, events, duration, sample_rate, extra_info=None):
        """Legacy CSV logger - Deprecated"""
        pass
    
    @staticmethod
    def save_session_info(csv_path, session_info):
        """
        Simpan informasi session ke CSV terpisah
        
        Args:
            csv_path (str): Path file CSV output
            session_info (dict): Dictionary berisi info session
        """
        os.makedirs(os.path.dirname(csv_path) if os.path.dirname(csv_path) else ".", exist_ok=True)
        
        write_header = not os.path.exists(csv_path)
        
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            fieldnames = list(session_info.keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if write_header:
                writer.writeheader()
            
            writer.writerow(session_info)
        
        print(f"[LOG] Session info saved to {csv_path}")
    
    @staticmethod
    def read_events(csv_path, session_id=None):
        """
        Baca events dari CSV
        
        Args:
            csv_path (str): Path file CSV
            session_id (str, optional): Filter berdasarkan session_id
            
        Returns:
            list: List of dictionaries berisi event data
        """
        if not os.path.exists(csv_path):
            print(f"[ERROR] File tidak ditemukan: {csv_path}")
            return []
        
        events = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Filter berdasarkan session_id jika diminta
                if session_id is None or row["session_id"] == session_id:
                    events.append(row)
        
        return events
    
    @staticmethod
    def get_summary(csv_path):
        """
        Dapatkan summary dari semua events dalam CSV
        
        Args:
            csv_path (str): Path file CSV
            
        Returns:
            dict: Summary statistics
        """
        if not os.path.exists(csv_path):
            return {
                "total_sessions": 0,
                "total_events": 0,
                "total_duration": 0
            }
        
        sessions = set()
        event_count = 0
        total_duration = 0
        
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sessions.add(row["session_id"])
                if row["event_number"] and int(row["event_number"]) > 0:
                    event_count += 1
                if row["total_recording_duration"]:
                    try:
                        total_duration += float(row["total_recording_duration"])
                    except (ValueError, TypeError):
                        pass
        
        return {
            "total_sessions": len(sessions),
            "total_events": event_count,
            "total_duration": round(total_duration, 2)
        }
