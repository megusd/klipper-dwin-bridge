#
# T5UID1 Serial Communication Interface
# 
# Implements T5UID1 touchscreen serial protocol for DMT48270C043_06WT display
# Protocol: 0x5A 0xA5 framing with 0x82 (write) / 0x83 (read) commands
#

import logging
import queue
import struct
import threading
from collections import defaultdict
from typing import Any, Callable, Optional
from time import time, sleep

from serial import Serial, SerialException

logger = logging.getLogger(__name__)

# T5UID1 Protocol Commands
T5UID1_CMD_WRITEVAR = 0x82
T5UID1_CMD_READVAR = 0x83

# T5UID1 Frame Header
T5UID1_HEADER = bytes([0x5A, 0xA5])

# Timeout settings
RESPONSE_TIMEOUT = 1.0
READ_RESPONSE_SLEEP = 0.02


class T5UID1Frame:
    """T5UID1 frame builder and parser"""
    
    @staticmethod
    def build_write_frame(address: int, data: bytes) -> bytes:
        """
        Build a T5UID1 write register frame.
        
        Frame format:
        - Header: 0x5A 0xA5
        - Length: payload length (command + address + data)
        - Command: 0x82 (write)
        - Address: 2 bytes, big-endian
        - Data: variable length
        """
        payload = bytearray()
        payload.append(T5UID1_CMD_WRITEVAR)
        payload.extend(struct.pack('>H', address))  # Big-endian address
        payload.extend(data)
        
        length = len(payload)
        frame = bytearray(T5UID1_HEADER)
        frame.append(length)
        frame.extend(payload)
        
        return bytes(frame)
    
    @staticmethod
    def build_read_frame(address: int, length: int) -> bytes:
        """
        Build a T5UID1 read register frame.
        
        Frame format:
        - Header: 0x5A 0xA5
        - Length: payload length (command + address + length)
        - Command: 0x83 (read)
        - Address: 2 bytes, big-endian
        - Length: 1 byte (number of bytes to read)
        """
        payload = bytearray()
        payload.append(T5UID1_CMD_READVAR)
        payload.extend(struct.pack('>H', address))
        payload.append(length)
        
        frame_length = len(payload)
        frame = bytearray(T5UID1_HEADER)
        frame.append(frame_length)
        frame.extend(payload)
        
        return bytes(frame)
    
    @staticmethod
    def parse_write_response(data: bytes) -> Optional[int]:
        """
        Parse T5UID1 write response.
        Expected: 0x5A 0xA5 [length] 0x82 [address bytes]
        Returns address on success, None on failure.
        """
        if len(data) < 5:
            return None
        
        if data[0:2] != T5UID1_HEADER:
            return None
        
        length = data[2]
        if len(data) < 3 + length:
            return None
        
        if data[3] != T5UID1_CMD_WRITEVAR:
            return None
        
        # Extract and validate address
        address = struct.unpack('>H', data[4:6])[0]
        return address
    
    @staticmethod
    def parse_read_response(data: bytes) -> Optional[tuple]:
        """
        Parse T5UID1 read response.
        Expected: 0x5A 0xA5 [length] 0x83 [address bytes] [data...]
        Returns (address, data) tuple on success, None on failure.
        """
        if len(data) < 6:
            return None
        
        if data[0:2] != T5UID1_HEADER:
            return None
        
        length = data[2]
        if len(data) < 3 + length:
            return None
        
        if data[3] != T5UID1_CMD_READVAR:
            return None
        
        address = struct.unpack('>H', data[4:6])[0]
        response_data = data[6:3+length]
        
        return (address, response_data)


class T5UID1Serial:
    """
    T5UID1 Serial Communication Interface
    
    Manages serial communication with T5UID1 touchscreen displays using
    the T5UID1 protocol. Supports asynchronous command/response pattern
    and spontaneous data reception (touch events, user input).
    """
    
    def __init__(self, serial_port: str, baudrate: int = 115200):
        """
        Initialize T5UID1 serial interface.
        
        Args:
            serial_port: Path to serial device (e.g., '/dev/ttyAMA0')
            baudrate: Serial baud rate (default 115200)
        """
        self._ser = Serial()
        self._ser.port = serial_port
        self._ser.baudrate = baudrate
        self._ser.timeout = 0.1
        
        self._request_queue = queue.Queue()
        self._response_buffer = bytearray()
        self._mutex = threading.Lock()
        
        self._spontaneous_callbacks = defaultdict(list)
        
        self._com_thread = None
        self._run_com_thread = False
        self._com_opened = False
        
        self._current_request = None
        self._awaited_bytes = 0
        self._time_send = 0
        self._wait_for_response_timeout = RESPONSE_TIMEOUT
        
        self._port_state_callback: Optional[Callable[[bool], Any]] = None
    
    def register_spontaneous_callback(self, address: int, callback: Callable[[bytes], Any]):
        """
        Register a callback for spontaneous data from the display.
        
        Callbacks are triggered when data is received from the specified address
        without a corresponding request (e.g., touch events).
        
        Args:
            address: Register address to monitor
            callback: Function to call with received data
        """
        with self._mutex:
            self._spontaneous_callbacks[address].append(callback)
    
    def set_port_state_callback(self, callback: Callable[[bool], Any]):
        """
        Register callback for serial port state changes.
        
        Args:
            callback: Function called with True when port opens, False on error
        """
        self._port_state_callback = callback
    
    def _open_com_port(self) -> bool:
        """Open the serial port."""
        try:
            self._ser.open()
            logger.info(f"Opened serial port {self._ser.port} at {self._ser.baudrate} baud")
            if self._port_state_callback:
                self._port_state_callback(True)
            return True
        except SerialException as e:
            logger.error(f"Failed to open serial port {self._ser.port}: {e}")
            return False
    
    def start_com_thread(self):
        """Start the communication thread."""
        self._com_opened = self._open_com_port()
        if self._com_opened:
            self._com_thread = threading.Thread(
                target=self._com_thread_function,
                daemon=False
            )
            self._run_com_thread = True
            self._com_thread.start()
            logger.info("Started T5UID1 communication thread")
        else:
            logger.error("Failed to start communication thread")
    
    def stop(self):
        """Stop the communication thread and close the serial port."""
        self._run_com_thread = False
        if self._com_thread:
            self._com_thread.join(timeout=2.0)
        
        with self._mutex:
            if self._ser.is_open:
                self._ser.close()
                logger.info("Closed serial port")
    
    def queue_write_request(self, address: int, data: bytes) -> bool:
        """
        Queue a register write request.
        
        Args:
            address: Register address
            data: Data to write
        
        Returns:
            True if queued successfully, False if queue is full
        """
        try:
            request = {
                'type': 'write',
                'address': address,
                'data': data,
                'timestamp': time()
            }
            self._request_queue.put(request, block=False)
            return True
        except queue.Full:
            logger.warning("Request queue is full, dropping request")
            return False
    
    def queue_read_request(self, address: int, length: int) -> bool:
        """
        Queue a register read request.
        
        Args:
            address: Register address
            length: Number of bytes to read
        
        Returns:
            True if queued successfully, False if queue is full
        """
        try:
            request = {
                'type': 'read',
                'address': address,
                'length': length,
                'timestamp': time()
            }
            self._request_queue.put(request, block=False)
            return True
        except queue.Full:
            logger.warning("Request queue is full, dropping request")
            return False
    
    def write_register(self, address: int, value: int, data_type: str = 'uint16') -> bool:
        """
        Write a value to a register with automatic type conversion.
        
        Args:
            address: Register address
            value: Value to write
            data_type: Data type ('uint8', 'int8', 'uint16', 'int16', 'uint32', 'int32')
        
        Returns:
            True if request queued successfully
        """
        data = self._encode_value(value, data_type)
        return self.queue_write_request(address, data)
    
    def write_string(self, address: int, value: str, max_length: int = 32) -> bool:
        """
        Write a string to a register (null-terminated, padded with spaces).
        
        Args:
            address: Register address
            value: String to write
            max_length: Maximum string length (pads with spaces)
        
        Returns:
            True if request queued successfully
        """
        # Pad or truncate string to max_length
        padded = value[:max_length].ljust(max_length)
        data = padded.encode('utf-8')
        return self.queue_write_request(address, data)
    
    @staticmethod
    def _encode_value(value: int, data_type: str) -> bytes:
        """Encode integer value to bytes based on data type."""
        if data_type == 'uint8':
            return struct.pack('>B', value)
        elif data_type == 'int8':
            return struct.pack('>b', value)
        elif data_type == 'uint16':
            return struct.pack('>H', value)
        elif data_type == 'int16':
            return struct.pack('>h', value)
        elif data_type == 'uint32':
            return struct.pack('>I', value)
        elif data_type == 'int32':
            return struct.pack('>i', value)
        else:
            logger.warning(f"Unknown data type: {data_type}, defaulting to uint16")
            return struct.pack('>H', value)
    
    @staticmethod
    def _decode_value(data: bytes, data_type: str) -> Optional[int]:
        """Decode bytes to integer value based on data type."""
        try:
            if data_type == 'uint8' and len(data) >= 1:
                return struct.unpack('>B', data[:1])[0]
            elif data_type == 'int8' and len(data) >= 1:
                return struct.unpack('>b', data[:1])[0]
            elif data_type == 'uint16' and len(data) >= 2:
                return struct.unpack('>H', data[:2])[0]
            elif data_type == 'int16' and len(data) >= 2:
                return struct.unpack('>h', data[:2])[0]
            elif data_type == 'uint32' and len(data) >= 4:
                return struct.unpack('>I', data[:4])[0]
            elif data_type == 'int32' and len(data) >= 4:
                return struct.unpack('>i', data[:4])[0]
            else:
                logger.warning(f"Insufficient data for type {data_type}")
                return None
        except struct.error as e:
            logger.error(f"Failed to decode {data_type}: {e}")
            return None
    
    def _com_thread_function(self):
        """Main communication thread loop."""
        logger.debug("Communication thread started")
        try:
            while self._run_com_thread:
                self._process_communication()
                sleep(0.001)  # Prevent busy-waiting
        except Exception as e:
            logger.error(f"Communication thread error: {e}", exc_info=True)
        finally:
            logger.debug("Communication thread stopped")
    
    def _process_communication(self):
        """Process a single communication cycle: send request, receive response."""
        # Try to send a pending request
        if self._current_request is None:
            try:
                self._current_request = self._request_queue.get(block=False)
                self._send_request(self._current_request)
                self._time_send = time()
            except queue.Empty:
                pass
        
        # Try to receive response data
        if self._current_request:
            self._receive_response()
    
    def _send_request(self, request: dict):
        """Send a request over the serial port."""
        try:
            if request['type'] == 'write':
                frame = T5UID1Frame.build_write_frame(
                    request['address'],
                    request['data']
                )
                logger.debug(f"Sending write: addr=0x{request['address']:04x}, len={len(request['data'])}")
            elif request['type'] == 'read':
                frame = T5UID1Frame.build_read_frame(
                    request['address'],
                    request['length']
                )
                logger.debug(f"Sending read: addr=0x{request['address']:04x}, len={request['length']}")
            else:
                logger.error(f"Unknown request type: {request['type']}")
                self._current_request = None
                return
            
            with self._mutex:
                if not self._ser.is_open:
                    logger.warning("Serial port is closed, cannot send")
                    self._current_request = None
                    return
                
                self._ser.write(frame)
                self._response_buffer.clear()
                self._awaited_bytes = 0
        except SerialException as e:
            logger.error(f"Serial write error: {e}")
            self._current_request = None
    
    def _receive_response(self):
        """Receive and process response data."""
        try:
            with self._mutex:
                if not self._ser.is_open:
                    return
                
                # Read available data
                if self._ser.in_waiting:
                    data = self._ser.read(self._ser.in_waiting)
                    self._response_buffer.extend(data)
                    logger.debug(f"Received {len(data)} bytes")
            
            # Try to parse a complete frame
            if self._try_parse_response():
                self._current_request = None
            # Check for timeout
            elif time() - self._time_send > self._wait_for_response_timeout:
                logger.warning(f"Response timeout for request: {self._current_request}")
                self._current_request = None
                self._response_buffer.clear()
        
        except SerialException as e:
            logger.error(f"Serial read error: {e}")
            self._current_request = None
    
    def _try_parse_response(self) -> bool:
        """
        Try to parse a complete response frame.
        
        Returns:
            True if a complete frame was parsed and processed, False otherwise
        """
        if len(self._response_buffer) < 5:  # Minimum frame size
            return False
        
        # Look for header
        header_idx = self._response_buffer.find(T5UID1_HEADER)
        if header_idx == -1:
            logger.warning("No frame header found in response buffer")
            self._response_buffer.clear()
            return False
        
        if header_idx > 0:
            logger.debug(f"Discarding {header_idx} bytes before frame header")
            del self._response_buffer[:header_idx]
        
        # Check if we have the complete frame
        if len(self._response_buffer) < 3:
            return False
        
        length = self._response_buffer[2]
        total_frame_size = 3 + length
        
        if len(self._response_buffer) < total_frame_size:
            logger.debug(f"Incomplete frame: have {len(self._response_buffer)}, need {total_frame_size}")
            return False
        
        # Extract complete frame
        frame = bytes(self._response_buffer[:total_frame_size])
        del self._response_buffer[:total_frame_size]
        
        # Parse and process frame
        if self._current_request:
            if self._current_request['type'] == 'write':
                result = T5UID1Frame.parse_write_response(frame)
                if result is not None:
                    logger.debug(f"Write acknowledged at address 0x{result:04x}")
                    return True
            elif self._current_request['type'] == 'read':
                result = T5UID1Frame.parse_read_response(frame)
                if result is not None:
                    address, data = result
                    logger.debug(f"Read response: addr=0x{address:04x}, len={len(data)}")
                    return True
        else:
            # Spontaneous data from display
            result = T5UID1Frame.parse_read_response(frame)
            if result is not None:
                address, data = result
                logger.debug(f"Spontaneous data: addr=0x{address:04x}, len={len(data)}")
                self._trigger_spontaneous_callbacks(address, data)
                return True
        
        return False
    
    def _trigger_spontaneous_callbacks(self, address: int, data: bytes):
        """Trigger registered callbacks for spontaneous data."""
        with self._mutex:
            callbacks = self._spontaneous_callbacks.get(address, [])
        
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error for address 0x{address:04x}: {e}", exc_info=True)
