 #
# T5UID1 Register Addresses
#
# Register map for DMT48270C043_06WT DWIN display using T5UID1 protocol
# Based on desuuuu's Klipper-DGUS-reloaded project
# Reference: _reference/desuuuu-klipper/klippy/extras/t5uid1/dgus_reloaded/
#

from enum import IntEnum


class DataAddress(IntEnum):
    """
    T5UID1 Register Addresses for touchscreen display communication.
    
    These addresses correspond to the DGUS variable map in the desuuuu
    DGUS-reloaded firmware for T5UID1 displays.
    """
    
    # ===== OUTPUT VARIABLES (Display <- Host) =====
    
    # Status Text Lines (32 bytes each)
    STATUS_LINE1 = 0x1100
    STATUS_LINE2 = 0x1120
    STATUS_LINE3 = 0x1140
    STATUS_LINE4 = 0x1160
    
    # Main Status Message (32 bytes)
    STATUS_MESSAGE = 0x3000
    
    # Print Status
    STATUS_PRINT_PROGRESS = 0x30f6  # uint16, 0-100%
    STATUS_PRINT_ELAPSED = 0x30e7   # str (15 bytes), formatted duration
    STATUS_PRINT_Z_POS = 0x30e6     # int16, Z position × 10
    
    # Temperature Readings (int16, in °C)
    TEMP_HOTEND_CURRENT = 0x30ff    # Current extruder temperature
    TEMP_HOTEND_TARGET = 0x3100     # Target extruder temperature
    TEMP_HOTEND_MAX = 0x3101        # Max extruder temperature
    
    TEMP_BED_CURRENT = 0x30fc       # Current bed temperature
    TEMP_BED_TARGET = 0x30fd        # Target bed temperature
    TEMP_BED_MAX = 0x30fe           # Max bed temperature
    
    # Second extruder (if available)
    TEMP_HOTEND1_CURRENT = 0x3102
    TEMP_HOTEND1_TARGET = 0x3103
    
    # Speed/Flow Adjustments (int16, in %)
    ADJUST_FEEDRATE = 0x30f8        # Speed factor percentage
    ADJUST_FLOWRATE = 0x30f9        # Extrusion factor percentage
    
    # ===== INPUT VARIABLES (Display -> Host) =====
    
    # Page Navigation
    SWITCH_PAGE = 0x2000            # Switch to page (uint16)
    SWITCH_PAGE_IF_IDLE = 0x2002    # Switch page only if idle
    SWITCH_PAGE_IF_PRINTING = 0x2003  # Switch page only if printing
    
    # Print Control
    ABORT_PRINT = 0x2007            # Cancel/abort print
    PAUSE_PRINT = 0x2008            # Pause print
    RESUME_PRINT = 0x2009           # Resume print
    
    # Speed/Flow Adjustment (int16)
    SET_FEEDRATE = 0x200a           # Set speed factor (M220 S{value})
    SET_FLOWRATE = 0x200b           # Set flow factor (M221 S{value})
    
    # Z-Offset Adjustment (int16)
    SET_Z_OFFSET = 0x200e           # Set Z-offset (in 0.01mm units)
    ADJUST_Z_OFFSET = 0x200f        # Increment/decrement Z-offset
    
    # Temperature Presets
    TEMP_PRESET_SELECT = 0x2010     # Select temp preset (PLA/ABS/PETG)
    
    # ===== LEGACY/COMPATIBILITY =====
    # (Kept for potential backward compatibility)
    
    UNDEFINED = 0xFFFF


