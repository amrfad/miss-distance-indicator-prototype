#!/usr/bin/env python3
"""
Drone Audio Detection System - Main Application
Entry point untuk sistem drone audio detection dengan serial communication
"""

import sys
import time
from .core.controller import DroneAudioSystem
from .io.serial_handler import SerialHandler
from .core.config import (
    MAIN_LOOP_DELAY
)
from .audio.processor import NOISEREDUCE_AVAILABLE
from .core.config_manager import ConfigManager, ConfigError, get_global_config_manager
from .config_api import start_api_thread


EXIT_CODE_RESTART = 5


def print_header():
    """Print header aplikasi"""
    cfg = get_global_config_manager().get_config()
    op_mode = cfg.get("operation_mode", "OFFLINE")
    
    print("="*60)
    print("DRONE AUDIO DETECTION SYSTEM — Continuous Streaming Mode")
    print("="*60)
    print(f"Operation Mode: {op_mode}")
    if op_mode == "ONLINE":
        print(f"Serial Port: {cfg.get('serial_port')}")
        print(f"Baud Rate: {cfg.get('baud_rate')}")
    print(f"Sample Rate: {cfg.get('sample_rate')} Hz")
    print(f"Chunk Duration: {cfg.get('chunk_duration_sec', 5.0)}s  |  Overlap: {cfg.get('chunk_overlap_sec', 1.0)}s")
    print(f"Keep Audio: {cfg.get('keep_audio_files', True)}")
    print(f"Filtering: {'Enabled' if NOISEREDUCE_AVAILABLE else 'Disabled'}")
    print(f"Output Dir: {cfg.get('base_output_dir')}")
    print("="*60)
    if op_mode == "ONLINE":
        print("\nWaiting for commands from ground station...")
        print("Commands: START_REC | STOP_REC | STATUS")
    else:
        if sys.stdin.isatty():
            print("\nOFFLINE MODE - Keyboard Control")
            print("Commands:")
            print("  s - Start Recording")
            print("  p - Stop Recording and Process")
            print("  t - Get Status")
            print("  i - System Info")
            print("  q - Quit")
        else:
            print("\nOFFLINE MODE - Headless (Running as service)")
    print("Press Ctrl+C to exit\n")


def get_keyboard_command():
    """Baca command dari keyboard untuk OFFLINE mode"""
    import time
    if not sys.stdin.isatty():
        time.sleep(1.0)
        return None
        
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


def process_command(command, audio_system, serial_handler=None, config_manager=None):
    """
    Proses command dari ground station
    
    Args:
        command (str): Command yang diterima
        audio_system (DroneAudioSystem): Instance sistem audio
        serial_handler (SerialHandler): Instance serial handler
        config_manager (ConfigManager): Instance config manager (optional)
    """
    print(f"\n[RECEIVED] {command}")
    
    response = None
    
    if command == "START_REC":
        success, message = audio_system.start_recording()
        response = f"OK:{message}" if success else f"ERROR:{message}"
        
    elif command == "STOP_REC":
        success, message, _ = audio_system.stop_and_process()
        response = f"OK:{message}" if success else f"ERROR:{message}"
            
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

    elif command == "SET_CONFIG":
        response = _handle_set_config(serial_handler, config_manager, audio_system)
        
    elif command == "RESTART":
        if audio_system:
            audio_system.restart_requested = True
        if serial_handler:
            serial_handler.send_response("OK:Restarting drone system...")
            print("[RESPONSE] OK:Restarting drone system...")
            time.sleep(0.5)  # Jeda agar serial terkirim
        raise KeyboardInterrupt("Restart requested via serial")

    else:
        response = f"ERROR:Unknown command '{command}'"

    
    # Kirim response (hanya jika ada serial_handler)
    if response:
        if serial_handler:
            serial_handler.send_response(response)
        print(f"[RESPONSE] {response}")


def _handle_set_config(serial_handler, config_manager, audio_system):
    """
    Handler untuk command SET_CONFIG via serial (section 5 contract).

    Protokol yang diharapkan setelah 'SET_CONFIG\n' diterima:
        [CONFIG_START]\n
        {json_content}\n
        [CONFIG_END]\n

    Returns:
        str: Response string untuk dikirim ke ground
    """
    import json
    from .core.config import CONFIG_TX_START_MARKER, CONFIG_TX_END_MARKER

    if config_manager is None:
        return "ERROR:SET_CONFIG:SERVER_ERROR:ConfigManager tidak tersedia"

    TIMEOUT = 5.0  # detik menunggu payload

    def read_line_with_timeout(timeout=TIMEOUT):
        """Baca satu baris dari serial dengan timeout."""
        if serial_handler is None:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = serial_handler.read_command()
            if line is not None:
                return line
            time.sleep(0.05)
        return None

    # 1. Baca [CONFIG_START]
    start_line = read_line_with_timeout()
    if start_line != CONFIG_TX_START_MARKER:
        print(f"[SET_CONFIG] Expected '{CONFIG_TX_START_MARKER}', got: {start_line!r}")
        return "ERROR:SET_CONFIG:VALIDATION_ERROR:Missing CONFIG_START marker"

    # 2. Baca JSON content
    json_line = read_line_with_timeout()
    if json_line is None:
        return "ERROR:SET_CONFIG:VALIDATION_ERROR:Timeout waiting for JSON payload"

    # 3. Baca [CONFIG_END]
    end_line = read_line_with_timeout()
    if end_line != CONFIG_TX_END_MARKER:
        print(f"[SET_CONFIG] Expected '{CONFIG_TX_END_MARKER}', got: {end_line!r}")
        return "ERROR:SET_CONFIG:VALIDATION_ERROR:Missing CONFIG_END marker"

    # 4. Parse JSON
    try:
        changes = json.loads(json_line)
    except json.JSONDecodeError as e:
        return f"ERROR:SET_CONFIG:VALIDATION_ERROR:JSON parse error: {e}"

    if not isinstance(changes, dict):
        return "ERROR:SET_CONFIG:VALIDATION_ERROR:Payload harus JSON object"

    # 5. Apply via ConfigManager (source="serial" → reject 🔒 params)
    try:
        result = config_manager.update(changes, source="serial")
    except ConfigError as e:
        return f"ERROR:SET_CONFIG:{e.code}:{e.message}"

    # 6. Apply ke runtime objects
    if audio_system is not None:
        detector = getattr(audio_system, "detector", None)
        config_manager.apply_to_runtime_objects(detector=detector)

    n_updated = len(result.get("updated", {}))
    return f"OK:SET_CONFIG:{n_updated} params updated"


def main():
    """Main loop aplikasi"""
    print_header()

    # Initialize ConfigManager
    config_manager = get_global_config_manager()

    # Initialize audio system (setelah config ter-apply)
    audio_system = DroneAudioSystem()

    # Apply runtime config ke detector (yang sudah instantiated)
    config_manager.apply_to_runtime_objects(
        detector=audio_system.detector,
        processor=audio_system.processor,
    )

    # Start Config REST API di daemon thread
    # Host dan port dibaca dari config_manager (api_host, api_port)
    start_api_thread(config_manager, audio_system)

    if config_manager.get("operation_mode") == "ONLINE":
        return run_online_mode(audio_system, config_manager)
    else:
        return run_offline_mode(audio_system, config_manager)


def run_online_mode(audio_system, config_manager=None):
    """Run dalam ONLINE mode dengan serial communication"""
    cfg = config_manager.get_config()
    serial_port = cfg.get("serial_port", "/dev/ttyUSB0")
    baud_rate = cfg.get("baud_rate", 230400)
    timeout = cfg.get("serial_timeout", 5)

    serial_handler = SerialHandler(port=serial_port, baudrate=baud_rate, timeout=timeout)
    
    # Connect to serial
    if not serial_handler.connect():
        print("[FATAL] Tidak dapat membuka serial port")
        print("Pastikan:")
        print(f"  1. Device {serial_port} ada")
        print("  2. Permission sudah benar (sudo usermod -a -G dialout $USER)")
        print("  3. Tidak ada program lain yang menggunakan port tersebut")
        return 1
    
    try:
        while True:
            # Baca command dari ground
            command = serial_handler.read_command()
            
            if command:
                process_command(command, audio_system, serial_handler, config_manager)
            
            # Small delay — baca dari config_manager agar bisa di-update runtime
            loop_delay = MAIN_LOOP_DELAY
            if config_manager is not None:
                try:
                    loop_delay = config_manager.get("main_loop_delay")
                except Exception:
                    pass
            time.sleep(loop_delay)
            
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down...")
        
        # Stop recording jika masih aktif
        if audio_system.recorder.is_recording():
            print("[SYSTEM] Stopping active recording...")
            audio_system.recorder.stop_recording()
        
        if getattr(audio_system, "restart_requested", False):
            print("[SYSTEM] Restart requested, returning exit code 5")
            return EXIT_CODE_RESTART
        
    finally:
        serial_handler.close()
        print("[SYSTEM] Shutdown complete")
    
    return 0


def run_offline_mode(audio_system, config_manager=None):
    """Run dalam OFFLINE mode dengan keyboard input"""
    try:
        while True:
            # Baca command dari keyboard
            command = get_keyboard_command()
            
            if command == 'QUIT':
                print("\n[SYSTEM] Quitting...")
                break
            
            if command:
                process_command(command, audio_system, serial_handler=None,
                                config_manager=config_manager)
            
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down...")
        if getattr(audio_system, "restart_requested", False):
            print("[SYSTEM] Restart requested, returning exit code 5")
            return EXIT_CODE_RESTART
    
    finally:
        # Stop recording jika masih aktif
        if audio_system.recorder.is_recording():
            print("[SYSTEM] Stopping active recording...")
            audio_system.recorder.stop_recording()
        
        print("[SYSTEM] Shutdown complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
