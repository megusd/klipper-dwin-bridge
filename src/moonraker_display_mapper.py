import logging
from moonraker.klippy_state import KlippyState

logger = logging.getLogger(__name__)


class MoonrakerDisplayMapper:
    def __init__(self, serial_interface, websocket_interface):
        self.serial = serial_interface
        self.ws = websocket_interface

    def start(self):
        # Placeholder: register to websocket events in real implementation
        logger.info("MoonrakerDisplayMapper started (dry placeholder)")
#
# Moonraker Display State Mapper
#
# Maps Moonraker printer state to T5UID1 display register writes.
# Handles real-time updates for temperatures, progress, status messages, etc.
#

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from t5uid1_serial import T5UID1Serial
from data_addresses import DataAddress
from moonraker.websocket_interface import WebsocketInterface
from moonraker.printer_state import PrinterState

logger = logging.getLogger(__name__)


class MoonrakerDisplayMapper:
    """
    Maps Moonraker printer state to T5UID1 display register writes.
    
    Subscribes to Moonraker WebSocket events and writes corresponding
    values to the display's DGUS registers over T5UID1 serial protocol.
    """
    
    def __init__(self, serial: T5UID1Serial, websocket: WebsocketInterface):
        """
        Initialize the display mapper.
        
        Args:
            serial: T5UID1Serial instance for display communication
            websocket: WebsocketInterface instance for Moonraker access
        """
        self.serial = serial
        self.websocket = websocket
        
        self._last_update = {}  # Track last written values to avoid redundant updates
        self._update_threshold = 0.5  # Only update temp if change > 0.5°C
        self._progress_threshold = 1  # Only update progress if change > 1%
    
    def start(self):
        """Start listening to Moonraker state changes."""
        # Register callbacks for state changes
        self.websocket.register_printer_state_event_receiver(
            self._on_printer_state_changed
        )
        logger.info("Display mapper started")
    
    def update_temperatures(self, state: Dict[str, Any]):
        """
        Update display with current temperature readings.
        
        Args:
            state: Klipper state dictionary from Moonraker
        """
        try:
            # Extruder temperature
            if 'extruder' in state:
                extruder = state['extruder']
                
                # Current temperature
                if 'temperature' in extruder:
                    temp = int(round(float(extruder['temperature'])))
                    if self._should_update('extruder_temp', temp, self._update_threshold):
                        self.serial.write_register(
                            DataAddress.TEMP_HOTEND_CURRENT,
                            temp,
                            'int16'
                        )
                        self._last_update['extruder_temp'] = temp
                
                # Target temperature
                if 'target' in extruder:
                    target = int(round(float(extruder['target'])))
                    if self._should_update('extruder_target', target, self._update_threshold):
                        self.serial.write_register(
                            DataAddress.TEMP_HOTEND_TARGET,
                            target,
                            'int16'
                        )
                        self._last_update['extruder_target'] = target
            
            # Bed temperature
            if 'heater_bed' in state:
                bed = state['heater_bed']
                
                # Current temperature
                if 'temperature' in bed:
                    temp = int(round(float(bed['temperature'])))
                    if self._should_update('bed_temp', temp, self._update_threshold):
                        self.serial.write_register(
                            DataAddress.TEMP_BED_CURRENT,
                            temp,
                            'int16'
                        )
                        self._last_update['bed_temp'] = temp
                
                # Target temperature
                if 'target' in bed:
                    target = int(round(float(bed['target'])))
                    if self._should_update('bed_target', target, self._update_threshold):
                        self.serial.write_register(
                            DataAddress.TEMP_BED_TARGET,
                            target,
                            'int16'
                        )
                        self._last_update['bed_target'] = target
        
        except Exception as e:
            logger.error(f"Error updating temperatures: {e}", exc_info=True)
    
    def update_print_progress(self, state: Dict[str, Any]):
        """
        Update display with print progress and status.
        
        Args:
            state: Klipper state dictionary from Moonraker
        """
        try:
            # Print progress percentage
            if 'virtual_sdcard' in state:
                sdcard = state['virtual_sdcard']
                
                if 'progress' in sdcard:
                    progress = int(round(float(sdcard['progress']) * 100))
                    if self._should_update('print_progress', progress, self._progress_threshold):
                        self.serial.write_register(
                            DataAddress.STATUS_PRINT_PROGRESS,
                            min(100, max(0, progress)),
                            'uint16'
                        )
                        self._last_update['print_progress'] = progress
                
                # Filename
                if 'filename' in sdcard:
                    filename = sdcard['filename']
                    # Extract just the filename without path
                    if '/' in filename:
                        filename = filename.split('/')[-1]
                    
                    if self._should_update('filename', filename):
                        # Write filename to status message
                        self.serial.write_string(
                            DataAddress.STATUS_MESSAGE,
                            filename[:32],
                            max_length=32
                        )
                        self._last_update['filename'] = filename
            
            # Print time elapsed
            if 'print_stats' in state:
                stats = state['print_stats']
                
                if 'print_duration' in stats:
                    elapsed_sec = int(float(stats['print_duration']))
                    elapsed_str = self._format_duration(elapsed_sec)
                    
                    if self._should_update('print_elapsed', elapsed_str):
                        self.serial.write_string(
                            DataAddress.STATUS_PRINT_ELAPSED,
                            elapsed_str,
                            max_length=15
                        )
                        self._last_update['print_elapsed'] = elapsed_str
        
        except Exception as e:
            logger.error(f"Error updating print progress: {e}", exc_info=True)
    
    def update_position(self, state: Dict[str, Any]):
        """
        Update display with current toolhead position.
        
        Args:
            state: Klipper state dictionary from Moonraker
        """
        try:
            if 'gcode_move' in state:
                move = state['gcode_move']
                
                if 'gcode_position' in move:
                    pos = move['gcode_position']
                    
                    # Z position (in 0.1mm units for display)
                    if 'z' in pos:
                        z_mm = float(pos['z'])
                        z_display = int(round(z_mm * 10))  # Convert to 0.1mm units
                        
                        if self._should_update('z_position', z_display, threshold=0):
                            self.serial.write_register(
                                DataAddress.STATUS_PRINT_Z_POS,
                                z_display,
                                'int16'
                            )
                            self._last_update['z_position'] = z_display
        
        except Exception as e:
            logger.error(f"Error updating position: {e}", exc_info=True)
    
    def update_speed_factors(self, state: Dict[str, Any]):
        """
        Update display with speed and extrusion factor.
        
        Args:
            state: Klipper state dictionary from Moonraker
        """
        try:
            if 'gcode_move' in state:
                move = state['gcode_move']
                
                # Speed factor (M220 S%)
                if 'speed_factor' in move:
                    speed = int(round(float(move['speed_factor']) * 100))
                    if self._should_update('speed_factor', speed, threshold=0):
                        self.serial.write_register(
                            DataAddress.ADJUST_FEEDRATE,
                            speed,
                            'int16'
                        )
                        self._last_update['speed_factor'] = speed
                
                # Extrusion factor (M221 S%)
                if 'extrude_factor' in move:
                    extrude = int(round(float(move['extrude_factor']) * 100))
                    if self._should_update('extrude_factor', extrude, threshold=0):
                        self.serial.write_register(
                            DataAddress.ADJUST_FLOWRATE,
                            extrude,
                            'int16'
                        )
                        self._last_update['extrude_factor'] = extrude
        
        except Exception as e:
            logger.error(f"Error updating speed factors: {e}", exc_info=True)
    
    def update_status_message(self, message: str):
        """
        Update display status message line.
        
        Args:
            message: Status message text
        """
        try:
            if self._should_update('status_message', message):
                self.serial.write_string(
                    DataAddress.STATUS_MESSAGE,
                    message[:32],
                    max_length=32
                )
                self._last_update['status_message'] = message
        except Exception as e:
            logger.error(f"Error updating status message: {e}", exc_info=True)
    
    def _on_printer_state_changed(self, state: PrinterState, message: str):
        """
        Callback when Moonraker printer state changes.
        
        Args:
            state: New PrinterState
            message: State description string
        """
        try:
            state_text = str(state.name).replace('_', ' ')
            self.update_status_message(f"{state_text}: {message}")
        except Exception as e:
            logger.error(f"Error handling state change: {e}")
    
    def update_from_state(self, state: Dict[str, Any]):
        """
        Update all display values from full printer state.
        
        Args:
            state: Full Klipper state dictionary from Moonraker
        """
        self.update_temperatures(state)
        self.update_print_progress(state)
        self.update_position(state)
        self.update_speed_factors(state)
    
    def _should_update(self, key: str, value: Any, threshold: float = 0) -> bool:
        """
        Check if a value has changed enough to warrant an update.
        
        Args:
            key: State key identifier
            value: New value
            threshold: Minimum change magnitude to trigger update
        
        Returns:
            True if update should be sent
        """
        if key not in self._last_update:
            return True
        
        last_value = self._last_update[key]
        
        if isinstance(value, (int, float)) and isinstance(last_value, (int, float)):
            change = abs(value - last_value)
            return change >= threshold
        else:
            return value != last_value
    
    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format seconds into human-readable duration."""
        if seconds < 0:
            seconds = 0
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
