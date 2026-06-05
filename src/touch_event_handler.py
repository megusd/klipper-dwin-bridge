import logging

logger = logging.getLogger(__name__)


class TouchEventHandler:
    def __init__(self, websocket):
        self.ws = websocket

    def handle_touch_event(self, address: int, data: bytes):
        logger.info(f"Touch event received addr=0x{address:04X} data={data.hex().upper()}")
        # In real implementation this maps to Moonraker calls
#
# Display Touch Event Handler
#
# Maps T5UID1 display touch events to Moonraker API calls.
# Handles button presses, numerical inputs, and control actions.
#

import logging
import struct
from typing import Callable, Dict, Any, Optional
from enum import IntEnum

from moonraker.websocket_interface import WebsocketInterface
from moonraker.moonraker_request import MoonrakerRequest
from data_addresses import DataAddress

logger = logging.getLogger(__name__)


class TouchEventHandler:
    """
    Handles display touch events and translates them to Moonraker API calls.
    
    Monitors specific display register addresses for touch input and performs
    corresponding printer actions (pause, resume, home, etc.).
    """
    
    def __init__(self, websocket: WebsocketInterface):
        """
        Initialize touch event handler.
        
        Args:
            websocket: WebsocketInterface instance for API communication
        """
        self.websocket = websocket
        self._handlers: Dict[int, Callable] = {}
        self._setup_event_handlers()
    
    def register_handler(self, address: int, handler: Callable):
        """
        Register a handler for a touch event at a specific address.
        
        Args:
            address: DataAddress where touch event is received
            handler: Callable that handles the event (receives data bytes)
        """
        self._handlers[address] = handler
    
    def handle_touch_event(self, address: int, data: bytes):
        """
        Handle a touch event received from the display.
        
        Args:
            address: Register address of the event
            data: Event data bytes
        """
        try:
            if address in self._handlers:
                handler = self._handlers[address]
                handler(data)
            else:
                logger.debug(f"No handler registered for address 0x{address:04x}")
        except Exception as e:
            logger.error(f"Error handling touch event at 0x{address:04x}: {e}", exc_info=True)
    
    def _setup_event_handlers(self):
        """Set up default handlers for common touch events."""
        # Pause print button
        self.register_handler(
            DataAddress.PAUSE_PRINT,
            self._handle_pause_print
        )
        
        # Resume print button
        self.register_handler(
            DataAddress.RESUME_PRINT,
            self._handle_resume_print
        )
        
        # Cancel/abort print button
        self.register_handler(
            DataAddress.ABORT_PRINT,
            self._handle_abort_print
        )
        
        # Speed factor adjustment
        self.register_handler(
            DataAddress.SET_FEEDRATE,
            self._handle_set_feedrate
        )
        
        # Extrusion factor adjustment
        self.register_handler(
            DataAddress.SET_FLOWRATE,
            self._handle_set_flowrate
        )
        
        # Z-offset adjustment
        self.register_handler(
            DataAddress.SET_Z_OFFSET,
            self._handle_set_z_offset
        )
        
        # Z-offset increment/decrement
        self.register_handler(
            DataAddress.ADJUST_Z_OFFSET,
            self._handle_adjust_z_offset
        )
        
        # Temperature preset selection
        self.register_handler(
            DataAddress.TEMP_PRESET_SELECT,
            self._handle_temp_preset
        )
    
    # ===== Event Handlers =====
    
    def _handle_pause_print(self, data: bytes):
        """Handle pause print button press."""
        try:
            logger.info("Pause print requested")
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.print.pause",
                    "id": 1001
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error pausing print: {e}")
    
    def _handle_resume_print(self, data: bytes):
        """Handle resume print button press."""
        try:
            logger.info("Resume print requested")
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.print.resume",
                    "id": 1002
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error resuming print: {e}")
    
    def _handle_abort_print(self, data: bytes):
        """Handle cancel/abort print button press."""
        try:
            logger.info("Cancel print requested")
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.print.cancel",
                    "id": 1003
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error cancelling print: {e}")
    
    def _handle_set_feedrate(self, data: bytes):
        """Handle speed factor adjustment from display."""
        try:
            if len(data) < 2:
                logger.warning(f"Invalid feedrate data: {data.hex()}")
                return
            
            # Data is int16 in big-endian, representing percentage
            feedrate = struct.unpack('>h', data[:2])[0]
            
            logger.info(f"Set feedrate: {feedrate}%")
            
            # Queue M220 command
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": f"M220 S{feedrate}"},
                    "id": 1004
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error setting feedrate: {e}")
    
    def _handle_set_flowrate(self, data: bytes):
        """Handle extrusion factor adjustment from display."""
        try:
            if len(data) < 2:
                logger.warning(f"Invalid flowrate data: {data.hex()}")
                return
            
            # Data is int16 in big-endian, representing percentage
            flowrate = struct.unpack('>h', data[:2])[0]
            
            logger.info(f"Set flowrate: {flowrate}%")
            
            # Queue M221 command
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": f"M221 S{flowrate}"},
                    "id": 1005
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error setting flowrate: {e}")
    
    def _handle_set_z_offset(self, data: bytes):
        """Handle Z-offset value input from display."""
        try:
            if len(data) < 2:
                logger.warning(f"Invalid Z-offset data: {data.hex()}")
                return
            
            # Data is int16 in big-endian, in 0.01mm units
            offset_steps = struct.unpack('>h', data[:2])[0]
            offset_mm = offset_steps / 100.0
            
            logger.info(f"Set Z-offset: {offset_mm} mm")
            
            # Queue SET_GCODE_OFFSET command
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": f"SET_GCODE_OFFSET Z={offset_mm} MOVE=1"},
                    "id": 1006
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error setting Z-offset: {e}")
    
    def _handle_adjust_z_offset(self, data: bytes):
        """Handle Z-offset increment/decrement from display."""
        try:
            if len(data) < 2:
                logger.warning(f"Invalid Z-offset adjustment data: {data.hex()}")
                return
            
            # Data is uint16 representing increment/decrement direction
            adjust_value = struct.unpack('>H', data[:2])[0]
            
            # Define adjustment values (these should match display configuration)
            # Typically: 1=increment, 2=decrement
            if adjust_value == 1:
                logger.info("Z-offset increment (+0.01mm)")
                adjustment = "+0.01"
            elif adjust_value == 2:
                logger.info("Z-offset decrement (-0.01mm)")
                adjustment = "-0.01"
            else:
                logger.warning(f"Unknown Z-offset adjustment: {adjust_value}")
                return
            
            # Queue SET_GCODE_OFFSET command with adjustment
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": f"SET_GCODE_OFFSET Z_ADJUST={adjustment} MOVE=1"},
                    "id": 1007
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error adjusting Z-offset: {e}")
    
    def _handle_temp_preset(self, data: bytes):
        """Handle temperature preset selection from display."""
        try:
            if len(data) < 2:
                logger.warning(f"Invalid temp preset data: {data.hex()}")
                return
            
            # Data is uint16 representing preset type
            preset = struct.unpack('>H', data[:2])[0]
            
            # Define presets (should match display DGUS config)
            presets = {
                1: {"name": "PLA", "hotend": 200, "bed": 60},
                2: {"name": "PETG", "hotend": 235, "bed": 80},
                3: {"name": "ABS", "hotend": 240, "bed": 100},
            }
            
            if preset not in presets:
                logger.warning(f"Unknown temperature preset: {preset}")
                return
            
            preset_config = presets[preset]
            logger.info(f"Setting temperature preset: {preset_config['name']}")
            
            # Queue temperature commands
            script = f"""SET_HEATER_TEMPERATURE HEATER=extruder TARGET={preset_config['hotend']}
SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={preset_config['bed']}"""
            
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": script},
                    "id": 1008
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error setting temperature preset: {e}")
    
    def home_axis(self, axis: str):
        """
        Home a single axis (for directional controls).
        
        Args:
            axis: Axis letter ('X', 'Y', 'Z', or 'All')
        """
        try:
            if axis.upper() == "ALL":
                cmd = "G28"
            else:
                cmd = f"G28 {axis.upper()}"
            
            logger.info(f"Homing {axis}")
            
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": cmd},
                    "id": 1009
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error homing {axis}: {e}")
    
    def move_axis(self, axis: str, distance: float, speed: float = 50):
        """
        Move an axis by a relative distance.
        
        Args:
            axis: Axis letter ('X', 'Y', or 'Z')
            distance: Distance to move (mm)
            speed: Movement speed (mm/min)
        """
        try:
            cmd = f"G91\nG1 {axis.upper()}{distance} F{speed}\nG90"
            
            logger.info(f"Move {axis} by {distance}mm")
            
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": cmd},
                    "id": 1010
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error moving {axis}: {e}")
    
    def set_fan_speed(self, speed: float):
        """
        Set part cooling fan speed.
        
        Args:
            speed: Fan speed 0-100 (percentage)
        """
        try:
            # Convert percentage to PWM value (0-1)
            pwm = max(0, min(1, speed / 100.0))
            
            logger.info(f"Set fan speed: {speed}%")
            
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": f"M106 S{int(pwm * 255)}"},
                    "id": 1011
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error setting fan speed: {e}")
    
    def preheat_hotend(self, temperature: float = 200):
        """
        Preheat the hotend.
        
        Args:
            temperature: Target temperature in °C
        """
        try:
            logger.info(f"Preheating hotend to {temperature}°C")
            
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": f"M104 S{int(temperature)}"},
                    "id": 1012
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error preheating hotend: {e}")
    
    def preheat_bed(self, temperature: float = 60):
        """
        Preheat the bed.
        
        Args:
            temperature: Target temperature in °C
        """
        try:
            logger.info(f"Preheating bed to {temperature}°C")
            
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": f"M140 S{int(temperature)}"},
                    "id": 1013
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error preheating bed: {e}")
    
    def emergency_stop(self):
        """Trigger printer emergency stop."""
        try:
            logger.critical("EMERGENCY STOP triggered")
            
            request = MoonrakerRequest(
                request={
                    "jsonrpc": "2.0",
                    "method": "printer.emergency_stop",
                    "id": 1014
                }
            )
            self.websocket.queue_request(request)
        except Exception as e:
            logger.error(f"Error triggering emergency stop: {e}")
