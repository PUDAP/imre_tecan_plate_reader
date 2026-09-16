# Tecan Infinite 200 PRO PUDA edge

PUDA edge service for the Tecan Infinite 200 PRO **M series** (for example,
Infinite 200 PRO M Plex). It uses PyLabRobot's experimental USB backend and
supports absorbance, top fluorescence, luminescence, selected-well reads, and
tray control. The backend does not cover Infinite F-series readers.

## Hardware prerequisites

- Connect the reader directly to the edge host over USB.
- Stop Tecan/i-control or any other process that owns the reader.
- Linux/Docker: ensure the service account can access the USB device. Compose
  passes `/dev/bus/usb` into the container; a host udev rule may still be needed.
- Windows bare metal: replace the Tecan driver for USB device `0C47:8007`
  with a libwdi/WinUSB (or libusbK) driver using
  [Zadig](https://zadig.akeo.ie/), as described in the
  [PyLabRobot USB guide](https://docs.pylabrobot.org/stable/user_guide/_getting-started/installation.html#using-the-usb-interface).
  On the commissioned PC, the working binding is the libwdi-generated
  `oem136.inf`; the original Tecan package is `oem98.inf`.

The backend identifies USB vendor `0x0C47`, product `0x8007`.

## Configure and run

Copy `.env.example` to `.env`, then edit the NATS endpoints:

```powershell
Copy-Item .env.example .env
uv sync
uv run python main.py
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `MACHINE_ID` | `imre-tecan-infinite-200-pro` | PUDA machine identifier |
| `NATS_SERVERS` | template cluster | Comma-separated broker URLs |
| `PLATE_MODEL` | `cor_96_wellplate_360uL_Fb` | PyLabRobot plate factory name |
| `COUNTS_PER_MM_X/Y/Z` | `1000` | Stage calibration values |
| `COMMAND_TIMEOUT` | `600` | Maximum seconds a command may wait |

The plate model supplies well geometry and must match the physical plate.

### Verify the Windows USB connection

The reader should appear under **Universal Serial Bus devices**, not **Tecan
controlled devices**, after the driver is replaced. Verify PyUSB discovery:

```powershell
uv run python -c "import usb.core, libusb_package; d=usb.core.find(backend=libusb_package.get_libusb1_backend(), idVendor=0x0C47, idProduct=0x8007); print('PyUSB device found:', d is not None)"
```

Expected output is `PyUSB device found: True`.

For a complete connection-only diagnostic with explicit progress and traceback,
run:

```powershell
uv run python -u diagnose_connection.py
```

This does not move the tray or perform a measurement. It verifies USB discovery
and the PyLabRobot initialization handshake, then releases the connection.

To perform a connection-only check without starting NATS:

```powershell
uv run python -c "from driver import Tecan_Infinite_200_pro; d=Tecan_Infinite_200_pro('cor_96_wellplate_360uL_Fb',1000,1000,1000,90); print(d.get_state()); d.shutdown()"
```

A successful check reports `connected: True` and `state: idle`.

Docker on Linux:

```bash
docker compose up -d --build
docker compose logs -f
```

## PUDA commands

```bash
puda machine call imre-tecan-infinite-200-pro open_tray '{}'
puda machine call imre-tecan-infinite-200-pro close_tray '{}'
puda machine call imre-tecan-infinite-200-pro read_absorbance \
  '{"wavelength":450,"wells":["A1","A2","B1","B2"]}'
puda machine call imre-tecan-infinite-200-pro read_fluorescence \
  '{"excitation_wavelength":485,"emission_wavelength":528,"focal_height":20.0}'
puda machine call imre-tecan-infinite-200-pro read_luminescence \
  '{"focal_height":20.0}'
puda machine call imre-tecan-infinite-200-pro get_state '{}'
```

Omit `wells` to measure the full plate. Absorbance accepts 230-1000 nm;
excitation and emission accept 230-850 nm. Focal height is in millimetres.

## Commissioning

Confirm setup completes and the PUDA machine registry is fresh before invoking
tray motion. Keep the tray workspace clear, then test tray motion without
labware before a measurement. A PUDA heartbeat alone does not prove the USB
controller initialized; check logs for the initialization message.

The PyLabRobot backend is marked experimental. Validate readings against known
controls before relying on experimental results.

On the commissioned reader, `open_tray` completed successfully. A subsequent
`close_tray` physically issued the command but timed out while waiting for the
reader's terminal USB acknowledgement. If this occurs, inspect the tray before
retrying so that repeated motion is not commanded blindly.

During initial setup and reset, the driver temporarily defers PyLabRobot's USB
recovery handler. This allows an unanswered optional startup `QQ` command to
time out without recursively closing, reopening, and reinitializing the reader.
Normal USB recovery is restored as soon as each setup attempt finishes. Startup
logs include explicit guarded-initialization start, completion, timeout, and
failure messages. A lone `Closing connection to USB device.` after diagnostic
success or service shutdown is normal resource cleanup, not an initialization
error.
