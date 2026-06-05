#
# Display Bridge - T5UID1 Adapter for DGUS Display Layer
#
# Adapts the T5UID1Serial interface to work with DGUS display masks.
# Provides compatibility layer for Request objects from the existing display framework.
#

import logging
import struct
from typing import Callable, Optional
from t5uid1_serial import T5UID1Serial

logger = logging.getLogger(__name__)


class Request:
    """Request object compatible with DGUS display framework."""
    
    def __init__(self, request_data_func: Callable, response_callback: Optional[Callable], name: str):
        """
        Args:
            request_data_func: Function that returns bytes to send
            response_callback: Function to call with response bytes
            name: Name/description of request
        """
        self.get_request_data = request_data_func
        self.response_callback = response_callback
        self.name = name


class DisplayBridge:
    """
    Adapter between DGUS display layer and T5UID1Serial protocol.
    
    - Accepts Request objects from display masks (compatible with DGUS framework)
    - Translates them to T5UID1 write/read operations
    - Routes responses back to display callbacks
    """
    
    def __init__(self, serial: T5UID1Serial):
        """
        Initialize DisplayBridge.
        
        Args:
            serial: T5UID1Serial instance for protocol handling
        """
        self.serial = serial
        self._request_callbacks = {}  # Map of pending request addresses to callbacks
    
    def queue_request(self, request: Request):
        """
        Queue a DGUS-compatible request for transmission.
        
        Args:
            request: Request object with get_request_data() and response_callback
        """
        try:
            # Get the raw bytes from the request
            request_bytes = request.get_request_data()
            
            if not request_bytes or len(request_bytes) < 5:
                logger.error(f"Invalid request data: {request_bytes}")
                return
            
            # Parse T5UID1 frame
            # Format: 0x5A 0xA5 [length] [command] [address_hi] [address_lo] [data...]
            if request_bytes[0:2] != bytes([0x5A, 0xA5]):
                logger.error(f"Invalid frame header in request: {request_bytes[0:2].hex()}")
                return
            
            frame_length = request_bytes[2]
            command = request_bytes[3]
            
            # Extract address (big-endian)
            if len(request_bytes) < 6:
                logger.error(f"Frame too short: {len(request_bytes)} bytes")
                return
            
            address = struct.unpack('>H', request_bytes[4:6])[0]
            
            logger.debug(f"Queuing request: {request.name} - cmd=0x{command:02x}, addr=0x{address:04x}")
            
            # Store callback for this address
            if request.response_callback:
                # Construct a response handler that includes the full frame response
                self._request_callbacks[address] = request.response_callback
                # Register spontaneous callback to capture response
                self.serial.register_spontaneous_callback(
                    address,
                    lambda data: self._handle_response(address, data, request_bytes)
                )
            
            # Queue the raw write/read request
            if command == 0x82:  # Write register
                data = request_bytes[6:3+frame_length]
                self.serial.queue_write_request(address, data)
            elif command == 0x83:  # Read register
                if len(request_bytes) > 6:
                    read_length = request_bytes[6]
                    self.serial.queue_read_request(address, read_length)
                else:
                    logger.error(f"Read request missing length: {request_bytes.hex()}")
            else:
                logger.error(f"Unknown command: 0x{command:02x}")
        
        except Exception as e:
            logger.error(f"Error queuing request: {e}", exc_info=True)
    
    def _handle_response(self, address: int, data: bytes, original_request: bytes):
        """
        Handle response from T5UID1 and invoke registered callback.
        
        Args:
            address: Register address that responded
            data: Response data bytes
            original_request: Original request bytes for reference
        """
        try:
            # Construct a fake DGUS response frame for compatibility
            # The display masks expect the full serial response
            # Format: 0x5A 0xA5 [length] [command] [data...]
            
            command = original_request[3]
            if command == 0x82:
                # Write response - just echo the address
                response = bytes([0x5A, 0xA5, 0x03, 0x82])
                response += struct.pack('>H', address)
            elif command == 0x83:
                # Read response - include the data
                response_payload = struct.pack('>H', address) + data
                length = len(response_payload) + 1
                response = bytes([0x5A, 0xA5, length, 0x83]) + response_payload
            else:
                logger.warning(f"Unknown command in response: 0x{command:02x}")
                return
            
            # Invoke the registered callback with the response
            if address in self._request_callbacks:
                callback = self._request_callbacks[address]
                del self._request_callbacks[address]
                
                if callback:
                    callback(response)
                    logger.debug(f"Response callback invoked for address 0x{address:04x}")
        
        except Exception as e:
            logger.error(f"Error handling response: {e}", exc_info=True)
    
    # Proxy methods for serial interface compatibility
    def register_spontaneous_callback(self, address: int, callback: Callable):
        """Register callback for spontaneous data."""
        self.serial.register_spontaneous_callback(address, callback)
    
    def set_port_state_callback(self, callback: Callable):
        """Register callback for port state changes."""
        self.serial.set_port_state_callback(callback)
    
    def start_com_thread(self) -> bool:
        """Start the communication thread."""
        self.serial.start_com_thread()
        return self.serial._com_opened
    
    def stop(self):
        """Stop communication."""
        self.serial.stop()
    
    def write_register(self, address: int, value: int, data_type: str = 'uint16') -> bool:
        """Write value to register (direct method, bypasses Request)."""
        return self.serial.write_register(address, value, data_type)
    
    def write_string(self, address: int, value: str, max_length: int = 32) -> bool:
        """Write string to register (direct method, bypasses Request)."""
        return self.serial.write_string(address, value, max_length)
