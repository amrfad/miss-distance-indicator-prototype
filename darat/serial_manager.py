import threading
import time

import serial
import serial.tools.list_ports


class SerialManager:
    def __init__(self, baud_rate=230400, timeout=1):
        """Initialize serial manager with connection parameters"""
        self.serial_port = None
        self.listening_thread = None
        self.listening = False
        self.baud_rate = baud_rate
        self.timeout = timeout

        # Callbacks for events
        self.on_message_received = None
        self.on_connection_status = None
        self.on_data_received = None

    def detect_and_connect(self):
        """Automatically detect and connect to the first available serial port"""
        try:
            # Get list of available serial ports
            ports = serial.tools.list_ports.comports()

            if ports:
                # Use the first available port
                port_name = ports[0].device
                self.serial_port = serial.Serial(
                    port_name, self.baud_rate, timeout=self.timeout
                )
                if self.on_connection_status:
                    self.on_connection_status(f"Serial port connected: {port_name}")

                # Start listening after successful connection
                self.start_listening()
                return True
            else:
                if self.on_connection_status:
                    self.on_connection_status("No serial ports found")
                return False

        except Exception as e:
            if self.on_connection_status:
                self.on_connection_status(f"Error connecting to serial port: {e}")
            return False

    def connect_to_port(self, port_name):
        """Connect to a specific serial port"""
        try:
            self.serial_port = serial.Serial(
                port_name, self.baud_rate, timeout=self.timeout
            )
            if self.on_connection_status:
                self.on_connection_status(f"Connected to {port_name}")

            self.start_listening()
            return True

        except Exception as e:
            if self.on_connection_status:
                self.on_connection_status(f"Error connecting to {port_name}: {e}")
            return False

    def send_command(self, command):
        """Send a command via serial port"""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.write(str(command).encode())
                if self.on_message_received:
                    self.on_message_received(f"Sent command: {command}")
                return True
            else:
                if self.on_message_received:
                    self.on_message_received(
                        f"Serial port not available. Command {command} not sent."
                    )
                return False
        except Exception as e:
            if self.on_message_received:
                self.on_message_received(f"Error sending serial command: {e}")
            return False

    def start_listening(self):
        """Start listening thread for incoming serial data"""
        if self.serial_port and self.serial_port.is_open:
            self.listening = True
            self.listening_thread = threading.Thread(
                target=self._serial_listener, daemon=True
            )
            self.listening_thread.start()
            if self.on_connection_status:
                self.on_connection_status("Serial listening started")

    def stop_listening(self):
        """Stop listening thread"""
        self.listening = False
        if self.listening_thread and self.listening_thread.is_alive():
            self.listening_thread.join(timeout=1)
            if self.on_connection_status:
                self.on_connection_status("Serial listening stopped")

    def _serial_listener(self):
        """Background thread to listen for incoming serial data"""
        while self.listening and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    # Read available data
                    raw_data = self.serial_port.read(self.serial_port.in_waiting)
                    if self.on_data_received:
                        self.on_data_received(raw_data)
                time.sleep(0.1)  # Small delay to prevent excessive CPU usage
            except Exception as e:
                if self.on_message_received:
                    self.on_message_received(f"Error reading serial data: {e}")
                break

    def is_connected(self):
        """Check if serial port is connected and open"""
        return self.serial_port and self.serial_port.is_open

    def get_port_info(self):
        """Get information about the connected port"""
        if self.serial_port:
            return {
                "port": self.serial_port.port,
                "baudrate": self.serial_port.baudrate,
                "timeout": self.serial_port.timeout,
                "is_open": self.serial_port.is_open,
            }
        return None

    def get_available_ports(self):
        """Get list of available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [
            {"device": port.device, "description": port.description} for port in ports
        ]

    def disconnect(self):
        """Disconnect from serial port and clean up"""
        self.stop_listening()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            if self.on_connection_status:
                self.on_connection_status("Serial port closed")

    def set_callbacks(self, on_message=None, on_status=None, on_data=None):
        """Set callback functions for events"""
        if on_message:
            self.on_message_received = on_message
        if on_status:
            self.on_connection_status = on_status
        if on_data:
            self.on_data_received = on_data
