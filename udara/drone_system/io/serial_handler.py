"""
Serial Communication Module
Mengelola komunikasi serial dengan ground station
"""

import os
import time
import threading
import serial

START_MARKER = b"[START]\n"
END_MARKER = b"\n[END]\n"
CHUNK_SIZE = 512


class SerialHandler:
    """Mengelola komunikasi serial dengan ground station (Command & File Transfer)."""

    def __init__(self, port="/dev/ttyUSB0", baudrate=230400, timeout=5):
        """
        Initialize serial handler
        
        Args:
            port (str): Serial port path (e.g., "/dev/ttyUSB0")
            baudrate (int): Baud rate komunikasi
            timeout (int): Timeout untuk read operation (detik)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self._lock = threading.Lock()
        
    def connect(self):
        """
        Buka koneksi serial
        
        Returns:
            bool: True jika berhasil, False jika gagal
        """
        with self._lock:
            if self.serial and self.serial.is_open:
                return True
            try:
                self.serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout
                )
                time.sleep(0.2)  # Tunggu stabilisasi koneksi
                print(f"[SERIAL] Connected to {self.port} at {self.baudrate} baud")
                return True
            except serial.SerialException as e:
                print(f"[ERROR] Serial connection failed: {e}")
                return False

    def disconnect(self):
        """Disconnect alias for close() for compatibility."""
        self.close()

    def read_command(self):
        """
        Baca command dari serial secara thread-safe
        
        Returns:
            str or None: Command string jika ada, None jika tidak ada/error
        """
        if not self.serial or not self.serial.is_open:
            return None
            
        try:
            with self._lock:
                if not self.serial or not self.serial.is_open:
                    return None
                received_bytes = self.serial.readline()
            if received_bytes:
                command = received_bytes.decode("utf-8").strip()
                return command
        except serial.SerialException as e:
            print(f"[ERROR] Serial read error: {e}")
            # Coba reconnect
            self._reconnect()
        except UnicodeDecodeError:
            print("[ERROR] Invalid data received")
            
        return None
    
    def send_response(self, message):
        """
        Kirim response ke ground station secara thread-safe
        
        Args:
            message (str): Pesan yang akan dikirim
            
        Returns:
            bool: True jika berhasil, False jika gagal
        """
        if not self.serial or not self.serial.is_open:
            return False
            
        try:
            with self._lock:
                if not self.serial or not self.serial.is_open:
                    return False
                self.serial.write((message + "\n").encode("utf-8"))
                self.serial.flush()  # Pastikan data terkirim
            return True
        except serial.SerialException as e:
            print(f"[ERROR] Serial write error: {e}")
            return False

    def send_file(self, file_path):
        """
        Kirim file ke ground station menggunakan protokol START/END marker secara thread-safe.

        Args:
            file_path (str): Path ke file yang akan dikirim

        Returns:
            bool: True jika berhasil, False jika gagal
        """
        if not self.serial or not self.serial.is_open:
            if not self.connect():
                return False

        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
                file_size = len(file_data)

                print(f"[COMMS] Sending file: {os.path.basename(file_path)} ({file_size} bytes)")
                start_time = time.time()

                with self._lock:
                    if not self.serial or not self.serial.is_open:
                        return False

                    # Send START marker
                    self.serial.write(START_MARKER)
                    time.sleep(0.05)

                    # Send data in chunks
                    bytes_sent = 0
                    for i in range(0, file_size, CHUNK_SIZE):
                        chunk = file_data[i:i + CHUNK_SIZE]
                        self.serial.write(chunk)
                        bytes_sent += len(chunk)
                        time.sleep(0.05)

                    self.serial.flush()
                    time.sleep(0.05)

                    # Send END marker
                    self.serial.write(END_MARKER)
                    self.serial.flush()

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

    def _reconnect(self):
        """Coba reconnect serial jika terputus"""
        try:
            with self._lock:
                if self.serial and self.serial.is_open:
                    self.serial.close()
                time.sleep(1)
                self.serial.open()
            print("[SERIAL] Reconnected")
        except Exception as e:
            print(f"[ERROR] Reconnect failed: {e}")
    
    def close(self):
        """Tutup koneksi serial"""
        with self._lock:
            if self.serial and self.serial.is_open:
                self.serial.close()
                print("[SERIAL] Connection closed")
    
    def is_connected(self):
        """
        Cek apakah koneksi serial aktif
        
        Returns:
            bool: True jika terhubung, False jika tidak
        """
        return self.serial is not None and self.serial.is_open
    
    def get_status(self):
        """
        Dapatkan status koneksi serial
        
        Returns:
            dict: Dictionary berisi status serial
        """
        return {
            "connected": self.is_connected(),
            "port": self.port,
            "baudrate": self.baudrate,
            "timeout": self.timeout
        }
