 # 
 # Klipper DWIN Bridge - Main Entry Point
 #
 # Python service for T5UID1 DWIN touchscreen communication with Klipper/Moonraker.
 # Manages printer state display and touch input handling.
 #

import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config_dir', type=str, help="Path to config directory")
parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode: do not open serial port; print DRY-RUN messages instead of sending')
args = parser.parse_args()

config_dir = os.path.join(os.getcwd(), "..", "config")

if args.config_dir:
    config_dir = args.config_dir

import json
import sys
import logging
import logging.config

logger_json_file = os.path.join(config_dir, "logging.json")
with open(logger_json_file) as json_file:
    json_data = json.load(json_file)
    logging.config.dictConfig(json_data)


from signal import signal, SIGINT
from time import sleep

from t5uid1_serial import T5UID1Serial
from display_bridge import DisplayBridge
from moonraker_display_mapper import MoonrakerDisplayMapper
from touch_event_handler import TouchEventHandler
from dgus.display.display import Display
from dgus.display.mask import Mask


from overview_display_mask import OverviewDisplayMask
from axes_display_mask import AxesDisplayMask
from homeing_mask import HomeingDisplayMask
from tuning_mask import TuningMask
from extruder_mask import ExtruderMask
from extruder_temp_to_low_mask import ExtruderTemperatureToLowMask
from fan_display_mask import FanMask
from startup_mask import StartupMask

from moonraker.websocket_interface import WebsocketInterface
from moonraker.klippy_state import KlippyState


logger = logging.getLogger(__name__)


def handle_display_touch_event(response: bytes):
    """Handle display touch events from spontaneous transmission."""
    try:
        if len(response) < 5:
            return
        
        # Parse response frame
        # Format: 0x5A 0xA5 [length] [command] [address_hi] [address_lo] [data...]
        address = int.from_bytes(response[4:6], byteorder='big')
        
        logger.debug(f"Display touch event from address 0x{address:04x}")
        
        # TODO: Map touch events to actions based on address
        # This will be implemented in task 5
    except Exception as e:
        logger.error(f"Error handling touch event: {e}", exc_info=True)


if __name__ == "__main__":
    
    logger.info("Using config directory: %s", config_dir)

    # Initialize Moonraker WebSocket connection
    PRINTER_IP = "127.0.0.1"
    PORT = 7125
    websock = WebsocketInterface(PRINTER_IP, PORT)

    # Read serial configuration
    serial_config_file = os.path.join(config_dir, "serial_config.json")
    if not os.path.exists(serial_config_file):
        logger.error(f"Serial config not found: {serial_config_file}")
        sys.exit(1)
    
    try:
        with open(serial_config_file) as f:
            serial_config = json.load(f)
            serial_port = serial_config.get("com_interface", {}).get("serial_port", "/dev/ttyAMA0")
            baudrate = serial_config.get("com_interface", {}).get("baudrate", 115200)
    except Exception as e:
        logger.error(f"Failed to read serial config: {e}")
        sys.exit(1)
    
    logger.info(f"Using serial port: {serial_port} at {baudrate} baud")
    
    # Initialize T5UID1 serial interface (or dummy in dry-run)
    if args.dry_run:
        class DummySerial:
            def __init__(self, port, baud):
                self.port = port
                self.baudrate = baud
                self._com_opened = True
                self._spontaneous = {}
                self._port_state_callback = None

            def register_spontaneous_callback(self, address, callback):
                # store but won't be called since no real serial
                self._spontaneous.setdefault(address, []).append(callback)

            def set_port_state_callback(self, callback):
                self._port_state_callback = callback

            def start_com_thread(self):
                # pretend we opened the port
                self._com_opened = True
                if self._port_state_callback:
                    try:
                        self._port_state_callback(True)
                    except Exception:
                        pass

            def stop(self):
                self._com_opened = False
                if self._port_state_callback:
                    try:
                        self._port_state_callback(False)
                    except Exception:
                        pass

            def queue_write_request(self, address, data):
                print(f"DRY-RUN: addr=0x{address:04X} data={data.hex().upper()}")
                return True

            def queue_read_request(self, address, length):
                # No real read — simulate empty response
                print(f"DRY-RUN: read_request addr=0x{address:04X} len={length}")
                # Optionally invoke spontaneous callbacks with zero data
                callbacks = self._spontaneous.get(address, [])
                for cb in callbacks:
                    try:
                        cb(bytes([0]*length))
                    except Exception:
                        pass
                return True

            def write_register(self, address, value, data_type='uint16'):
                # Convert value to bytes for display
                print(f"DRY-RUN: addr=0x{address:04X} data=0x{value:04X}")
                return True

            def write_string(self, address, value, max_length=32):
                print(f"DRY-RUN: write_string addr=0x{address:04X} value='{value}'")
                return True

        t5uid1_serial = DummySerial(serial_port, baudrate)
        logger.info("Running in DRY-RUN mode: serial port will not be opened")
    else:
        t5uid1_serial = T5UID1Serial(serial_port, baudrate)
    
    # Create display bridge adapter
    display_bridge = DisplayBridge(t5uid1_serial)
    
    # Create Moonraker display mapper
    display_mapper = MoonrakerDisplayMapper(t5uid1_serial, websock)
    
    # Create touch event handler
    touch_handler = TouchEventHandler(websock)
    
    # Read websocket configuration
    websocket_config_file = os.path.join(config_dir, "websocket.json")
    if os.path.exists(websocket_config_file):
        try:
            with open(websocket_config_file) as f:
                websocket_config = json.load(f)
                ws_ip = websocket_config.get("websocket", {}).get("ip", PRINTER_IP)
                ws_port = websocket_config.get("websocket", {}).get("port", PORT)
                websock = WebsocketInterface(ws_ip, ws_port)
        except Exception as e:
            logger.warning(f"Failed to read websocket config: {e}, using defaults")
    else:
        logger.info(f"Websocket config not found, using defaults: {PRINTER_IP}:{PORT}")

    # Register global display touch event handler
    display_bridge.register_spontaneous_callback(0x0000, handle_display_touch_event)

    # Register touch event callbacks from display to handler
    from data_addresses import DataAddress
    
    def touch_event_router(address: int):
        """Create a callback function for touch events at a specific address."""
        def callback(data: bytes):
            touch_handler.handle_touch_event(address, data)
        return callback
    
    # Register all touch input addresses
    touch_addresses = [
        DataAddress.PAUSE_PRINT,
        DataAddress.RESUME_PRINT,
        DataAddress.ABORT_PRINT,
        DataAddress.SET_FEEDRATE,
        DataAddress.SET_FLOWRATE,
        DataAddress.SET_Z_OFFSET,
        DataAddress.ADJUST_Z_OFFSET,
        DataAddress.TEMP_PRESET_SELECT,
    ]
    
    for addr in touch_addresses:
        display_bridge.register_spontaneous_callback(addr, touch_event_router(addr))

    # Handle serial port state changes
    def serial_port_state_changed(opened):
        """Callback when serial port opens/closes."""
        if opened:
            logger.info("Serial port opened")
            act_mask = display.get_active_mask()
            
            mask_idx = 0
            if act_mask is not None:
                mask_idx = act_mask.mask_no
            
            display.switch_to_mask(mask_idx, False)
        else:
            logger.warning("Serial port closed")
    
    display_bridge.set_port_state_callback(serial_port_state_changed)

    run_main_thread = True

    # Initialize display manager
    display = Display(display_bridge)

    def handleSIGINT(signum, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("Shutting down...")
        
        if display._active_mask is not None:
            display._active_mask.mask_suppressed()

        websock.stop()
        display_bridge.stop()
        
        global run_main_thread
        run_main_thread = False

    signal(SIGINT, handleSIGINT)

    # Start Moonraker connection
    websock.start()

    # Add display masks
    startupMask = StartupMask(display_bridge, websock)
    display.add_mask(startupMask)
      
    overviewMask = OverviewDisplayMask(display_bridge, websock)
    display.add_mask(overviewMask)
    
    mainMenuMask = Mask(30, display_bridge)
    display.add_mask(mainMenuMask)

    axesMask = AxesDisplayMask(display_bridge, websock, display)
    display.add_mask(axesMask)

    tuningMask = TuningMask(display_bridge, websock)
    display.add_mask(tuningMask)

    extruderMask = ExtruderMask(display_bridge, websock, display)
    display.add_mask(extruderMask)

    fanMask = FanMask(display_bridge, websock)
    display.add_mask(fanMask)

    homeingInProgress = HomeingDisplayMask(51, display_bridge, websock)
    display.add_mask(homeingInProgress)

    extruder_temp_to_low_mask = ExtruderTemperatureToLowMask(display_bridge, websock)
    display.add_mask(extruder_temp_to_low_mask)

    # Start communication thread
    if display_bridge.start_com_thread():
        logger.info("Serial communication thread started successfully")
        
        # Start display mapper (listens to Moonraker state changes)
        display_mapper.start()
        
        # TODO: Initialize display state (read/write initial values)
        # display.read_config_data_for_all_controls()

        # Switch to startup screen
        display.switch_to_mask(50)
    else:
        logger.error("Failed to start serial communication thread")
        sys.exit(1)

    # Handle Klipper state changes
    def klippy_state_changed(state: KlippyState, state_message: str):
        """Callback when Klipper state changes."""
        logger.info(f"Klipper state: {state} - {state_message}")
        
        if state == KlippyState.READY:
            logger.info("Klipper ready, switching to main menu")
            display.switch_to_mask(30, False)
            display.switch_to_mask(0)
        else:
            logger.info("Klipper not ready, showing startup screen")
            display.switch_to_mask(50, False)

    websock.register_klippy_state_event_receiver(klippy_state_changed)

    # Main event loop
    logger.info("Starting main event loop")
    try:
        while run_main_thread:
            display.update_current_mask()
            sleep(0.2)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Main loop error: {e}", exc_info=True)
    finally:
        logger.info("Main loop ended")
        display_bridge.stop()
        websock.stop()

