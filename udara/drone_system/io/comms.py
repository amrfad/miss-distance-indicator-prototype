import serial
import time
import sys
import os
from ..core.config_manager import get_global_config_manager

START_MARKER = b"[START]\n"
END_MARKER = b"\n[END]\n"
CHUNK_SIZE = 1024

class SerialCommunicator:
    def __init__(self, port=None, baudrate=None, timeout=None):
        cfg = get_global_config_manager().get_config()
        self.port = port if port is not None else cfg.get("serial_port", "/dev/ttyUSB0")
        self.baudrate = baudrate if baudrate is not None else cfg.get("baud_rate", 230400)
        self.timeout = timeout if timeout is not None else cfg.get("serial_timeout", 5)
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=10
            )
            time.sleep(0.2)
            print(f"[COMMS] Connected to {self.port} at {self.baudrate}")
            return True
        except serial.SerialException as e:
            print(f"[COMMS] Connection failed: {e}")
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[COMMS] Disconnected")

    def send_file(self, file_path):
        if not self.ser or not self.ser.is_open:
            if not self.connect():
                return False

        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
                file_size = len(file_data)
                
                print(f"[COMMS] Sending file: {os.path.basename(file_path)} ({file_size} bytes)")
                start_time = time.time()
                
                # Send START marker
                self.ser.write(START_MARKER)
                time.sleep(0.1)
                
                # Send data in chunks
                bytes_sent = 0
                for i in range(0, file_size, CHUNK_SIZE):
                    chunk = file_data[i:i + CHUNK_SIZE]
                    self.ser.write(chunk)
                    bytes_sent += len(chunk)
                    # Optional: small delay to prevent buffer overflow on receiver
                    time.sleep(0.005)
                
                time.sleep(0.1)
                # Send END marker
                self.ser.write(END_MARKER)
                
                end_time = time.time()
                duration = end_time - start_time
                print(f"[COMMS] Sent successfully in {duration:.2f}s")
                return True

        except FileNotFoundError:
            print(f"[COMMS] File not found: {file_path}")
            return False
        except Exception as e:
            print(f"[COMMS] Error sending file: {e}")
            return False
