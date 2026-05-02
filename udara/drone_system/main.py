#!/usr/bin/env python3
"""
Drone Audio Detection System - Main Application
Entry point untuk sistem drone audio detection dengan serial communication
"""

import sys
from .controller import DroneAudioSystem
from .serial_handler import SerialHandler
from .config import (
    SERIAL_PORT,
    BAUD_RATE,
    MAIN_LOOP_DELAY,
    SAMPLE_RATE,
    BASE_OUTPUT_DIR,
    OPERATION_MODE
)
from .processor import NOISEREDUCE_AVAILABLE


def print_header():
    """Print header aplikasi"""
    print("="*60)
    print("DRONE AUDIO DETECTION SYSTEM")
    print("="*60)
    print(f"Operation Mode: {OPERATION_MODE}")
    if OPERATION_MODE == "ONLINE":
        print(f"Serial Port: {SERIAL_PORT}")
        print(f"Baud Rate: {BAUD_RATE}")
    print(f"Sample Rate: {SAMPLE_RATE} Hz")
    print(f"Filtering: {'Enabled' if NOISEREDUCE_AVAILABLE else 'Disabled'}")
    print(f"Output Dir: {BASE_OUTPUT_DIR}")
    print("="*60)
    if OPERATION_MODE == "ONLINE":
        print("\nWaiting for commands from ground station...")
        print("Commands: START_REC | STOP_REC | STATUS")
    else:
        print("\nOFFLINE MODE - Keyboard Control")
        print("Commands:")
        print("  s - Start Recording")
        print("  p - Stop Recording and Process")
        print("  t - Get Status")
        print("  i - System Info")
        print("  q - Quit")
    print("Press Ctrl+C to exit\n")


def get_keyboard_command():
    """Baca command dari keyboard untuk OFFLINE mode"""
    try:
        cmd = input("\nEnter command (s/p/t/i/q): ").strip().lower()
        command_map = {
            's': 'START_REC',
            'p': 'STOP_REC',
            't': 'STATUS',
            'i': 'INFO',
            'q': 'QUIT'
        }
        return command_map.get(cmd, None)
    except EOFError:
        return None
    except KeyboardInterrupt:
        return 'QUIT'


def process_command(command, audio_system, serial_handler=None):
    """
    Proses command dari ground station
    
    Args:
        command (str): Command yang diterima
        audio_system (DroneAudioSystem): Instance sistem audio
        serial_handler (SerialHandler): Instance serial handler
    """
    print(f"\n[RECEIVED] {command}")
    
    response = None
    
    if command == "START_REC":
        success, message = audio_system.start_recording()
        response = f"OK:{message}" if success else f"ERROR:{message}"
        
    elif command == "STOP_REC":
        success, message, events = audio_system.stop_and_process()
        if success:
            event_count = len(events) if events else 0
            response = f"OK:{event_count} events detected"
        else:
            response = f"ERROR:{message}"
            
    elif command == "STATUS":
        success, status, _ = audio_system.get_status()
        response = f"OK:{status}"
        
    elif command == "INFO":
        # Command tambahan untuk mendapatkan system info
        info = audio_system.get_system_info()
        
        # Print detail untuk OFFLINE mode
        if not serial_handler:
            print("\n" + "="*50)
            print("SYSTEM INFORMATION")
            print("="*50)
            rec_info = info['recorder']
            print(f"Recording Status: {'ACTIVE' if rec_info['is_recording'] else 'IDLE'}")
            print(f"Device Profile: {rec_info['profile']}")
            print(f"Audio Format: {rec_info['format']}")
            print(f"Channels: {rec_info['channels']}")
            print(f"Sample Rate: {rec_info['sample_rate']} Hz")
            print(f"Output Directory: {info['output_directory']}")
            print(f"Noise Reduction: {'Available' if info['processor_features']['noisereduce'] else 'Not Available'}")
            if info['current_session']:
                print(f"Current Session: {info['current_session']}")
            print("="*50)
        
        response = f"OK:Recorder={rec_info['is_recording']},Features={info['processor_features']}"
        
    else:
        response = f"ERROR:Unknown command '{command}'"
    
    # Kirim response (hanya jika ada serial_handler)
    if response:
        if serial_handler:
            serial_handler.send_response(response)
        print(f"[RESPONSE] {response}")


def main():
    """Main loop aplikasi"""
    print_header()
    
    # Initialize system
    audio_system = DroneAudioSystem()
    
    if OPERATION_MODE == "ONLINE":
        return run_online_mode(audio_system)
    else:
        return run_offline_mode(audio_system)


def run_online_mode(audio_system):
    """Run dalam ONLINE mode dengan serial communication"""
    serial_handler = SerialHandler()
    
    # Connect to serial
    if not serial_handler.connect():
        print("[FATAL] Tidak dapat membuka serial port")
        print("Pastikan:")
        print(f"  1. Device {SERIAL_PORT} ada")
        print("  2. Permission sudah benar (sudo usermod -a -G dialout $USER)")
        print("  3. Tidak ada program lain yang menggunakan port tersebut")
        return 1
    
    try:
        while True:
            # Baca command dari ground
            command = serial_handler.read_command()
            
            if command:
                process_command(command, audio_system, serial_handler)
            
            # Small delay untuk mengurangi CPU usage
            import time
            time.sleep(MAIN_LOOP_DELAY)
            
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down...")
        
        # Stop recording jika masih aktif
        if audio_system.recorder.is_recording():
            print("[SYSTEM] Stopping active recording...")
            audio_system.recorder.stop_recording()
        
    finally:
        serial_handler.close()
        print("[SYSTEM] Shutdown complete")
    
    return 0


def run_offline_mode(audio_system):
    """Run dalam OFFLINE mode dengan keyboard input"""
    try:
        while True:
            # Baca command dari keyboard
            command = get_keyboard_command()
            
            if command == 'QUIT':
                print("\n[SYSTEM] Quitting...")
                break
            
            if command:
                process_command(command, audio_system, serial_handler=None)
            
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down...")
    
    finally:
        # Stop recording jika masih aktif
        if audio_system.recorder.is_recording():
            print("[SYSTEM] Stopping active recording...")
            audio_system.recorder.stop_recording()
        
        print("[SYSTEM] Shutdown complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
