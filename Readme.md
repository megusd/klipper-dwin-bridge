klipper_dgus
============
A python project that connects a DGUS display to [Klipper](https://www.klipper3d.org/)

The display i'm using here is a *DMG80480C043_02WTRZ07* (Stock Display of Anycubic Vyper 3D-Printer) which has a resolution 480x800. For this Display you can find the DGUS Project in the *dgus_project* folder.

For Displays with other resolution, the Project must be recreated.

**WARNING: 
This project is still under development and needs to be tested properly by a larger user base.
It has been tested by a few people, so most should be stable, but may happen for you that some 
errors or problems occur.

Please keep that in mind when you this project.
**


Documentation
-------------
See [documentation](https://klipper-dgus.rtfd.io)


License
-------
The whole project is licensed under GPLv3.

See [license](./License)

References
----------
This projects uses Graphics from:

* [Klipper](https://github.com/Klipper3d/klipper)
* [KlipperScreen](https://github.com/jordanruthe/KlipperScreen)

Getting Started (T5UID1 / DMT48270C043_06WT)
----------------------------------------

Prerequisites
 - Raspberry Pi (Raspbian / Raspberry Pi OS) with Python 3.8+
 - Klipper, Moonraker and a web UI (Mainsail/Fluidd) running on the Pi or networked host
 - DWIN T5UID1 touchscreen (DMT48270C043_06WT) flashed with a compatible DWIN_SET firmware (see below)

Clone and prepare virtualenv

```bash
git clone <repo-url> klipper-dwin-bridge
cd klipper-dwin-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Hardware wiring
 - Connect the touchscreen UART TX/RX to the Raspberry Pi UART (use the Pi's primary UART: `ttyAMA0`).
 - Typical wiring (verify for your panel):
	 - Display TX -> Raspberry Pi RX (GPIO pin 15 / UART RX)
	 - Display RX -> Raspberry Pi TX (GPIO pin 14 / UART TX)
	 - GND -> GND
 - Disable serial console and configure `/boot/config.txt` / `raspi-config` to enable the UART for the serial port.

Configuration
 - `config/serial_config.json`: set `com_interface.serial_port` (e.g., `/dev/ttyAMA0`) and optional `baudrate`.
 - `config/websocket.json`: set Moonraker `ip` and `port`.

Flashing the DWIN_SET firmware
 - The display firmware (DWIN_SET) must be written to the panel's microSD card using the vendor tools or the firmware archive included with the UI project.
 - Steps (high level):
	 1. Copy the `DWIN_SET` folder contents to the SD card root.
	 2. Insert the SD card into the display, power-cycle the display and wait for the firmware to load.
	 3. Remove the SD card and reboot the panel if necessary.
 - See `_reference/cr10spro-dwin/Readme.md` for project-specific resources.

Systemd service (example)
 - Create `/etc/systemd/system/klipper-dwin-bridge.service` with content similar to:

```ini
[Unit]
Description=Klipper DWIN T5UID1 Bridge
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/klipper-dwin-bridge/src
ExecStart=/home/pi/klipper-dwin-bridge/.venv/bin/python3 main.py -c ../config
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable klipper-dwin-bridge.service
sudo systemctl start klipper-dwin-bridge.service
sudo journalctl -u klipper-dwin-bridge -f
```

Running tests
 - Install test dependencies:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

 - Run the test runner (activates venv if available):

```bash
./scripts/run_tests.sh .venv
```

 - Or run pytest directly:

```bash
source .venv/bin/activate
python3 -m pytest src/ -v
```

Notes
 - This project replaces the serial protocol layer with T5UID1; do not modify Klipper or Moonraker.
 - Configuration files in `config/` control serial and websocket settings.

