"""
Serial Communication Module
Mengelola komunikasi serial dengan ground station
"""

import time
import serial
from .config import SERIAL_PORT, BAUD_RATE, SERIAL_TIMEOUT


class SerialHandler:
    """Mengelola komunikasi serial dengan ground station"""
    
    def __init__(self, port=SERIAL_PORT, baudrate=BAUD_RATE, timeout=SERIAL_TIMEOUT):
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
        
    def connect(self):
        """
        Buka koneksi serial
        
        Returns:
            bool: True jika berhasil, False jika gagal
        """
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
    
    def read_command(self):
        """
        Baca command dari serial
        
        Returns:
            str or None: Command string jika ada, None jika tidak ada/error
        """
        if not self.serial or not self.serial.is_open:
            return None
            
        try:
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
        Kirim response ke ground station
        
        Args:
            message (str): Pesan yang akan dikirim
            
        Returns:
            bool: True jika berhasil, False jika gagal
        """
        if not self.serial or not self.serial.is_open:
            return False
            
        try:
            self.serial.write((message + "\n").encode("utf-8"))
            self.serial.flush()  # Pastikan data terkirim
            return True
        except serial.SerialException as e:
            print(f"[ERROR] Serial write error: {e}")
            return False
    
    def _reconnect(self):
        """Coba reconnect serial jika terputus"""
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
            time.sleep(1)
            self.serial.open()
            print("[SERIAL] Reconnected")
        except Exception as e:
            print(f"[ERROR] Reconnect failed: {e}")
    
    def close(self):
        """Tutup koneksi serial"""
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
