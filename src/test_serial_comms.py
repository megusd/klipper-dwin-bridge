#!/usr/bin/env python3
"""Hardware test: validate T5UID1 serial communication with the DMT48270C043_06WT screen.

Run: python3 test_serial_comms.py [--port /dev/ttyAMA0] [--timeout 1000]

Performs write then read for several safe registers and prints hex frames.
"""
import argparse
import sys
import time

from t5uid1_serial import T5UID1Frame

import serial


def hexb(b: bytes) -> str:
    return b.hex().upper()


def probe_register(ser: serial.Serial, address: int, timeout_ms: int) -> bool:
    # Write test data 0x0000
    write_data = bytes([0x00, 0x00])
    write_frame = T5UID1Frame.build_write_frame(address, write_data)

    try:
        ser.reset_input_buffer()
    except Exception:
        pass

    try:
        ser.write(write_frame)
    except Exception as e:
        print(f"WRITE ERROR: failed to send to 0x{address:04X}: {e}")
        return False

    print(f"WRITE: {hexb(write_frame)} → 0x{address:04X}")

    # Short delay then request read back
    time.sleep(0.100)

    # Request 2 bytes back (safe for these registers)
    read_frame = T5UID1Frame.build_read_frame(address, 2)
    try:
        ser.write(read_frame)
    except Exception as e:
        print(f"READ CMD ERROR: failed to send read for 0x{address:04X}: {e}")
        return False

    print(f"READ CMD SENT: {hexb(read_frame)} ← 0x{address:04X}")

    deadline = time.time() + (timeout_ms / 1000.0)
    buf = bytearray()
    while time.time() < deadline:
        try:
            n = ser.in_waiting
        except Exception:
            n = 0
        if n:
            data = ser.read(n)
            buf.extend(data)
            # Try parsing a read response
            parsed = T5UID1Frame.parse_read_response(bytes(buf))
            if parsed is not None:
                raddr, rdata = parsed
                print(f"READ: {hexb(bytes(buf))} ← {hexb(rdata)} (addr 0x{raddr:04X})")
                return True
        time.sleep(0.01)

    # Timeout
    print(f"FAILED: no response for read 0x{address:04X} within {timeout_ms}ms")
    if buf:
        print(f"RAW_RECEIVED: {hexb(bytes(buf))}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="T5UID1 serial communications hardware test")
    parser.add_argument("--port", default="/dev/ttyAMA0", help="Serial port to use (default /dev/ttyAMA0)")
    parser.add_argument("--timeout", type=int, default=1000, help="Read timeout in milliseconds (default 1000)")
    args = parser.parse_args()

    registers = [0x1000, 0x1050, 0x3000, 0x30FF, 0x30F6]

    try:
        ser = serial.Serial(args.port, 115200, timeout=0.1)
    except Exception as e:
        print(f"ERROR: unable to open port {args.port}: {e}")
        return 1

    print(f"Opened {args.port} at 115200")

    all_ok = True
    for addr in registers:
        ok = probe_register(ser, addr, args.timeout)
        status = "OK" if ok else "FAILED"
        print(f"Status for 0x{addr:04X}: {status}\n")
        if not ok:
            all_ok = False
            break

    try:
        ser.close()
    except Exception:
        pass

    if all_ok:
        print("SERIAL COMMS OK")
        return 0
    else:
        print("SERIAL COMMS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
